"""
ThyroTrack MongoDB Storage Service (Optimized for Serverless & Vercel)
High-performance singleton connection pooling for patient screenings,
sensor telemetry, Q&A results, Cloudinary voice links, and distributed audio chunk sessions.
No local file writes to codebase.
"""

import os
import time
import logging
import threading
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

# Ensure .env is loaded
load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger("thyrotrack_mongo")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = os.getenv("MONGODB_DB_NAME", "thyrotrack_db")
RECORDS_COLLECTION = "records"
SENSOR_COLLECTION = "sensor_readings"
AUDIO_SESSIONS_COLLECTION = "audio_sessions"

_client = None
_client_lock = threading.Lock()
_indices_created = False


def get_mongo_client():
    """
    Returns a singleton MongoClient with connection pooling.
    Thread-safe lazy initialization.
    """
    global _client
    if _client is not None:
        return _client

    with _client_lock:
        if _client is None:
            try:
                from pymongo import MongoClient
                _client = MongoClient(
                    MONGODB_URI,
                    maxPoolSize=50,
                    minPoolSize=5,
                    maxIdleTimeMS=30000,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=7000,
                )
                logger.info("Connected to MongoDB with connection pooling.")
            except Exception as e:
                logger.error(f"Failed to initialize MongoClient: {e}")
                return None
    return _client


def get_mongo_collection(collection_name: str = RECORDS_COLLECTION):
    """
    Returns pymongo collection instance from pooled client, or None if unavailable.
    Ensures essential indices are created once.
    """
    global _indices_created
    client = get_mongo_client()
    if client is None:
        return None

    try:
        db = client[DB_NAME]
        col = db[collection_name]

        if not _indices_created:
            try:
                db[RECORDS_COLLECTION].create_index("recording_id", unique=True, sparse=True)
                db[RECORDS_COLLECTION].create_index([("created_at", -1)])
                db[SENSOR_COLLECTION].create_index([("received_at", -1)])
                db[SENSOR_COLLECTION].create_index("recording_id", sparse=True)
                # TTL index to auto-delete incomplete audio sessions after 30 minutes
                db[AUDIO_SESSIONS_COLLECTION].create_index("updated_at", expireAfterSeconds=1800)
                db[AUDIO_SESSIONS_COLLECTION].create_index("recording_id", unique=True)
                _indices_created = True
            except Exception as idx_err:
                logger.debug(f"Index creation note: {idx_err}")
                _indices_created = True  # Avoid re-attempting on every request

        return col
    except Exception as e:
        logger.error(f"MongoDB collection access error ({collection_name}): {e}")
        return None


# ------------------------------------------------------------------
# Distributed Audio Session Streaming (Enables Vercel Serverless Audio Streaming)
# ------------------------------------------------------------------
def create_audio_session(recording_id: str, subject_id: str = "subject_001") -> bool:
    """
    Creates an audio session in MongoDB so multiple serverless lambdas can stream chunks.
    """
    col = get_mongo_collection(AUDIO_SESSIONS_COLLECTION)
    if col is None:
        return False
    try:
        col.update_one(
            {"recording_id": recording_id},
            {
                "$set": {
                    "recording_id": recording_id,
                    "subject_id": subject_id,
                    "next_chunk": 0,
                    "bytes_received": 0,
                    "last_chunk_bytes": 0,
                    "dropped_samples": 0,
                    "chunks": [],
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "updated_at": datetime.now(),
                }
            },
            upsert=True,
        )
        return True
    except Exception as e:
        logger.error(f"create_audio_session error: {e}")
        return False


def append_audio_chunk(recording_id: str, chunk_index: int, chunk_bytes: bytes, dropped: int = 0) -> dict:
    """
    Appends raw PCM chunk directly to MongoDB session across serverless lambdas.
    """
    from bson.binary import Binary
    col = get_mongo_collection(AUDIO_SESSIONS_COLLECTION)
    if col is None:
        return {"status": "error", "error": "Database offline"}

    try:
        session = col.find_one({"recording_id": recording_id})
        if not session:
            return {"status": "not_found", "error": "Recording session not found or expired"}

        expected = int(session.get("next_chunk", 0))

        # ESP32 retry handling: If duplicate chunk, acknowledge success
        if chunk_index == expected - 1 and len(chunk_bytes) == session.get("last_chunk_bytes"):
            return {
                "status": "duplicate_ignored",
                "chunk_index": chunk_index,
                "total_bytes": session.get("bytes_received", 0),
            }

        if chunk_index != expected:
            return {
                "status": "mismatch",
                "error": "Unexpected chunk index",
                "expected": expected,
                "received": chunk_index,
            }

        new_total = session.get("bytes_received", 0) + len(chunk_bytes)
        max_dropped = max(session.get("dropped_samples", 0), dropped)

        col.update_one(
            {"recording_id": recording_id},
            {
                "$push": {"chunks": Binary(chunk_bytes)},
                "$set": {
                    "next_chunk": expected + 1,
                    "bytes_received": new_total,
                    "last_chunk_bytes": len(chunk_bytes),
                    "dropped_samples": max_dropped,
                    "updated_at": datetime.now(),
                },
            },
        )

        return {
            "status": "chunk_received",
            "chunk_index": chunk_index,
            "chunk_bytes": len(chunk_bytes),
            "total_bytes": new_total,
        }
    except Exception as e:
        logger.error(f"append_audio_chunk error: {e}")
        return {"status": "error", "error": str(e)}


def finish_audio_session(recording_id: str) -> dict | None:
    """
    Retrieves all binary audio chunks for the session, concatenates them, and deletes the temp session.
    """
    col = get_mongo_collection(AUDIO_SESSIONS_COLLECTION)
    if col is None:
        return None

    try:
        session = col.find_one({"recording_id": recording_id})
        if not session:
            return None

        # Clean up temporary session document from MongoDB
        col.delete_one({"recording_id": recording_id})
        return session
    except Exception as e:
        logger.error(f"finish_audio_session error: {e}")
        return None


def cancel_audio_session(recording_id: str):
    """
    Deletes an active audio session.
    """
    col = get_mongo_collection(AUDIO_SESSIONS_COLLECTION)
    if col is not None:
        try:
            col.delete_one({"recording_id": recording_id})
        except Exception:
            pass


# ------------------------------------------------------------------
# Sensor Telemetry
# ------------------------------------------------------------------
def save_sensor_reading_to_mongodb(sensor_data: dict) -> dict:
    """
    Saves sensor reading directly into MongoDB sensor_readings collection.
    No local files saved to codebase.
    """
    record = dict(sensor_data)
    if "received_at" not in record:
        record["received_at"] = datetime.now().isoformat(timespec="seconds")
    record["epoch"] = time.time()

    collection = get_mongo_collection(collection_name=SENSOR_COLLECTION)
    if collection is not None:
        try:
            rec_id = record.get("recording_id")
            if rec_id:
                res = collection.update_one(
                    {"recording_id": rec_id},
                    {"$set": record},
                    upsert=True,
                )
                inserted_id = str(res.upserted_id) if res.upserted_id else rec_id
            else:
                res = collection.insert_one(record)
                inserted_id = str(res.inserted_id)

            record["_id"] = inserted_id
            return {
                "status": "saved_to_mongodb",
                "mongodb_connected": True,
                "database": DB_NAME,
                "collection": SENSOR_COLLECTION,
                "inserted_id": inserted_id,
                "record": record,
            }
        except Exception as exc:
            logger.error(f"MongoDB sensor insert error: {exc}")
            return {"status": "error", "message": str(exc), "record": record}

    return {"status": "mongodb_offline", "record": record}


def get_sensor_history_from_mongodb(limit: int = 100) -> list:
    """
    Retrieves sensor history directly from MongoDB sensor_readings collection.
    """
    collection = get_mongo_collection(collection_name=SENSOR_COLLECTION)
    if collection is not None:
        try:
            records = list(collection.find({}, {"_id": 0}).sort([("epoch", -1), ("_id", -1)]).limit(limit))
            return list(reversed(records))
        except Exception as e:
            logger.error(f"MongoDB sensor history fetch error: {e}")
    return []


def get_latest_sensor_reading_from_mongodb() -> dict | None:
    """
    Retrieves the most recent sensor reading from MongoDB.
    """
    collection = get_mongo_collection(collection_name=SENSOR_COLLECTION)
    if collection is not None:
        try:
            return collection.find_one({}, {"_id": 0}, sort=[("epoch", -1), ("_id", -1)])
        except Exception as e:
            logger.error(f"MongoDB latest sensor fetch error: {e}")
    return None


# ------------------------------------------------------------------
# Screenings & Assessments Records
# ------------------------------------------------------------------
def save_record_to_mongodb(record_data: dict) -> dict:
    """
    Saves or updates a complete record JSON (audio metadata + Cloudinary link + sensor telemetry + Q&A)
    exclusively in MongoDB 'records' collection.
    Upserts by recording_id so duplicate calls or updates are merged safely.
    Zero local disk writes.
    """
    record = dict(record_data)
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")
    record["epoch"] = time.time()
    recording_id = record.get("recording_id")

    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    inserted_id = None
    if collection is not None:
        try:
            update_data = {k: v for k, v in record.items() if k != "_id"}
            if recording_id:
                res = collection.update_one(
                    {"recording_id": recording_id},
                    {"$set": update_data},
                    upsert=True,
                )
                inserted_id = str(res.upserted_id) if res.upserted_id else recording_id
            else:
                res = collection.insert_one(update_data)
                inserted_id = str(res.inserted_id)

            record["_id"] = inserted_id
            return {
                "status": "saved_to_mongodb",
                "mongodb_connected": True,
                "database": DB_NAME,
                "collection": RECORDS_COLLECTION,
                "recording_id": recording_id,
                "inserted_id": inserted_id,
                "record": record,
            }
        except Exception as exc:
            logger.error(f"MongoDB record insert error: {exc}")
            return {"status": "error", "message": str(exc), "record": record}

    return {"status": "mongodb_offline", "record": record}


def update_record_in_mongodb(recording_id: str, **sections) -> dict:
    """
    Merges updated sections (e.g., audio, sensor, labels) into a record in MongoDB.
    Returns the merged record dictionary.
    """
    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    existing = get_record_from_mongodb(recording_id) or {
        "recording_id": recording_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }

    for key, value in sections.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            existing[key].update(value)
        else:
            existing[key] = value

    existing["epoch"] = time.time()

    if collection is not None:
        try:
            update_data = {k: v for k, v in existing.items() if k != "_id"}
            collection.update_one(
                {"recording_id": recording_id},
                {"$set": update_data},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"MongoDB update_record error: {e}")

    return existing


def get_record_from_mongodb(recording_id: str) -> dict | None:
    """
    Retrieves a single complete record by recording_id from MongoDB.
    """
    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    if collection is not None:
        try:
            return collection.find_one({"recording_id": recording_id}, {"_id": 0})
        except Exception as e:
            logger.error(f"MongoDB get record error: {e}")
    return None


def get_all_records_from_mongodb(limit: int = 100) -> list:
    """
    Retrieves complete records from MongoDB 'records' collection.
    """
    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    if collection is not None:
        try:
            return list(collection.find({}, {"_id": 0}).sort([("epoch", -1), ("_id", -1)]).limit(limit))
        except Exception as e:
            logger.error(f"MongoDB fetch records error: {e}")
    return []


def get_latest_voice_record_from_mongodb() -> dict | None:
    """
    Finds the latest record in MongoDB that has a Cloudinary voice URL.
    """
    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    if collection is not None:
        try:
            rec = collection.find_one(
                {
                    "$or": [
                        {"audio.cloudinary.cloudinary_url": {"$exists": True, "$ne": None}},
                        {"voice_cloudinary_url": {"$exists": True, "$ne": None}},
                    ]
                },
                {"_id": 0},
                sort=[("epoch", -1), ("_id", -1)],
            )
            return rec
        except Exception as e:
            logger.error(f"MongoDB get_latest_voice_record error: {e}")
    return None
