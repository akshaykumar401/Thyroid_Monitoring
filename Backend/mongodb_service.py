"""
ThyroTrack MongoDB Storage Service (Optimized)
High-performance singleton connection pooling for patient screenings,
sensor telemetry, Q&A results, and Cloudinary voice links.
No local file writes to codebase.
"""

import os
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
                    serverSelectionTimeoutMS=4000,
                    connectTimeoutMS=4000,
                    socketTimeoutMS=5000,
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
                _indices_created = True
            except Exception as idx_err:
                logger.debug(f"Index creation note: {idx_err}")
                _indices_created = True  # Avoid re-attempting on every request

        return col
    except Exception as e:
        logger.error(f"MongoDB collection access error ({collection_name}): {e}")
        return None


def save_sensor_reading_to_mongodb(sensor_data: dict) -> dict:
    """
    Saves sensor reading directly into MongoDB sensor_readings collection.
    No local files saved to codebase.
    """
    record = dict(sensor_data)
    if "received_at" not in record:
        record["received_at"] = datetime.now().isoformat(timespec="seconds")

    collection = get_mongo_collection(collection_name=SENSOR_COLLECTION)
    if collection is not None:
        try:
            # Upsert by recording_id or received_at to prevent duplicate inserts
            rec_id = record.get("recording_id")
            if rec_id:
                res = collection.update_one(
                    {"recording_id": rec_id},
                    {"$set": record},
                    upsert=True
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
            records = list(collection.find({}, {"_id": 0}).sort("received_at", -1).limit(limit))
            # Return in chronological order
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
            return collection.find_one({}, {"_id": 0}, sort=[("received_at", -1)])
        except Exception as e:
            logger.error(f"MongoDB latest sensor fetch error: {e}")
    return None


def save_record_to_mongodb(record_data: dict) -> dict:
    """
    Saves or updates a complete record JSON (audio metadata + Cloudinary link + sensor telemetry + Q&A)
    exclusively in MongoDB 'records' collection.
    Upserts by recording_id so duplicate calls or updates are merged safely.
    Zero local disk writes.
    """
    record = dict(record_data)
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")
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
                    upsert=True
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

    if collection is not None:
        try:
            update_data = {k: v for k, v in existing.items() if k != "_id"}
            collection.update_one(
                {"recording_id": recording_id},
                {"$set": update_data},
                upsert=True
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
            return list(collection.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
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
            # Query for records having audio.cloudinary.cloudinary_url or voice_cloudinary_url
            rec = collection.find_one(
                {
                    "$or": [
                        {"audio.cloudinary.cloudinary_url": {"$exists": True, "$ne": None}},
                        {"voice_cloudinary_url": {"$exists": True, "$ne": None}},
                    ]
                },
                {"_id": 0},
                sort=[("created_at", -1), ("saved_at", -1)]
            )
            return rec
        except Exception as e:
            logger.error(f"MongoDB get_latest_voice_record error: {e}")
    return None
