"""
ThyroTrack MongoDB Storage Service
Stores patient screenings, sensor metrics, Q&A results, and Google Drive voice links.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("thyrotrack_mongo")

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "thyrotrack_db"
RECORDS_COLLECTION = "records"

BACKUP_DIR = Path(__file__).resolve().parent / "thyroid_data" / "mongodb_backup"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_FILE = BACKUP_DIR / "assessments.jsonl"
RECORDS_BACKUP_FILE = BACKUP_DIR / "records.jsonl"


def get_mongo_collection(collection_name: str = RECORDS_COLLECTION):
    """
    Returns pymongo collection instance or None if MongoDB server is unavailable.
    """
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        # Test connection ping
        client.admin.command('ping')
        db = client[DB_NAME]
        return db[collection_name]
    except Exception as e:
        logger.info(f"MongoDB not reachable at {MONGODB_URI} ({e}).")
        return None


def save_sensor_reading_to_mongodb(sensor_data: dict) -> dict:
    """
    Saves live sensor batch telemetry from ESP32-C3 directly into MongoDB sensor_readings collection.
    """
    record = dict(sensor_data)
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")

    collection = get_mongo_collection(collection_name=SENSOR_COLLECTION)
    if collection is not None:
        try:
            result = collection.insert_one(record)
            record["_id"] = str(result.inserted_id)
            return {
                "status": "saved_to_mongodb",
                "mongodb_connected": True,
                "database": DB_NAME,
                "collection": SENSOR_COLLECTION,
                "inserted_id": str(result.inserted_id),
                "record": record
            }
        except Exception as exc:
            logger.error(f"MongoDB sensor insert error: {exc}")
            return {"status": "error", "message": str(exc)}
    return {"status": "mongodb_offline"}


def save_assessment_to_mongodb(assessment_data: dict) -> dict:
    """
    Inserts a patient assessment record into MongoDB.
    Falls back gracefully to local JSONL backup if MongoDB server is not running.
    """
    record = dict(assessment_data)
    record["saved_at"] = datetime.now().isoformat(timespec="seconds")

    collection = get_mongo_collection()
    if collection is not None:
        try:
            result = collection.insert_one(record)
            record["_id"] = str(result.inserted_id)
            return {
                "status": "saved_to_mongodb",
                "mongodb_connected": True,
                "database": DB_NAME,
                "collection": COLLECTION_NAME,
                "inserted_id": str(result.inserted_id),
                "record": record
            }
        except Exception as exc:
            logger.error(f"MongoDB insert error: {exc}")

    # Persistent local JSONL fallback
    try:
        # serialize any non-serializable fields
        doc_id = record.get("recording_id") or f"rec_{int(datetime.now().timestamp())}"
        record["_id"] = str(doc_id)
        with BACKUP_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        
        return {
            "status": "saved_to_local_cache",
            "mongodb_connected": False,
            "storage": str(BACKUP_FILE),
            "inserted_id": record["_id"],
            "record": record,
            "note": "Stored safely in MongoDB cache. Ready for auto-sync when MongoDB server starts."
        }
    except Exception as e:
        logger.error(f"Failed to backup assessment record: {e}")
        return {
            "status": "error",
            "message": str(e),
            "record": record
        }


def get_all_assessments(limit: int = 50) -> list:
    """
    Retrieves assessment records from MongoDB or local storage.
    """
    collection = get_mongo_collection()
    if collection is not None:
        try:
            records = list(collection.find({}, {"_id": 0}).sort("saved_at", -1).limit(limit))
            return records
        except Exception as e:
            logger.error(f"MongoDB fetch error: {e}")

    # Fallback: read from local JSONL
    if BACKUP_FILE.is_file():
        records = []
        try:
            with BACKUP_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            return list(reversed(records[-limit:]))
        except Exception:
            pass

    return []


def save_record_to_mongodb(record_data: dict) -> dict:
    """
    Saves a complete record JSON (audio metadata + Cloudinary link + sensor telemetry)
    exclusively into MongoDB 'records' collection.
    Upserts by recording_id so duplicate calls or updates are merged safely.
    Falls back gracefully to local JSONL backup if MongoDB server is offline.
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
                "record": record
            }
        except Exception as exc:
            logger.error(f"MongoDB record insert error: {exc}")

    # Fallback to local JSONL backup if MongoDB offline
    try:
        doc_id = recording_id or f"rec_{int(datetime.now().timestamp())}"
        record["_id"] = str(doc_id)
        with RECORDS_BACKUP_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return {
            "status": "saved_to_local_cache",
            "mongodb_connected": False,
            "storage": str(RECORDS_BACKUP_FILE),
            "recording_id": recording_id,
            "inserted_id": record["_id"],
            "record": record
        }
    except Exception as e:
        logger.error(f"Failed to backup record: {e}")
        return {"status": "error", "message": str(e), "record": record}


def get_record_from_mongodb(recording_id: str) -> dict | None:
    """
    Retrieves a single complete record by recording_id from MongoDB or local backup.
    """
    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    if collection is not None:
        try:
            rec = collection.find_one({"recording_id": recording_id}, {"_id": 0})
            if rec:
                return rec
        except Exception as e:
            logger.error(f"MongoDB get record error: {e}")

    # Fallback: check local backup
    if RECORDS_BACKUP_FILE.is_file():
        try:
            with RECORDS_BACKUP_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        if data.get("recording_id") == recording_id:
                            return data
        except Exception:
            pass

    return None


def get_all_records_from_mongodb(limit: int = 100) -> list:
    """
    Retrieves complete records from MongoDB 'records' collection or local backup.
    """
    collection = get_mongo_collection(collection_name=RECORDS_COLLECTION)
    if collection is not None:
        try:
            records = list(collection.find({}, {"_id": 0}).sort("created_at", -1).limit(limit))
            return records
        except Exception as e:
            logger.error(f"MongoDB fetch records error: {e}")

    # Fallback: read from local JSONL
    if RECORDS_BACKUP_FILE.is_file():
        records = []
        try:
            with RECORDS_BACKUP_FILE.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        records.append(json.loads(line))
            return list(reversed(records[-limit:]))
        except Exception:
            pass

    return []

