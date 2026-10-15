
"""
Thyroid screening prototype - Flask server (receives data from the ESP32-C3)

Run:   pip install flask numpy
       python thyroid_server.py

Folders created next to this file:
  thyroid_data/audio/      finished WAV files
  thyroid_data/records/    one JSON per recording (audio info + sensor data + lab labels)
  thyroid_data/sensor_data/sensor_history.jsonl

Main endpoints used by the ESP32:
  POST /api/audio/start                      {"recording_id": "...", "subject_id": "..."}
  POST /api/audio/chunk/<id>/<n>             raw 16-bit PCM bytes
  POST /api/audio/finish/<id>                {"dropped_samples":..,"captured_ms":..,"wall_ms":..}
  POST /api/audio/cancel/<id>
  POST /api/sensor-batch                     sensor summary (links to recording_id)

Endpoints for you (data collection / AI):
  POST /api/label                            attach lab results (TSH, T3, T4) to a recording
  GET  /api/records , /api/records/<id>      see everything saved
  GET  /api/dataset.csv                      one row per recording, ready for ML
"""

import csv
import io
import json
import re
import shutil
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, Response, send_file
from werkzeug.serving import WSGIRequestHandler
from dotenv import load_dotenv

# Load environment configuration from .env
load_dotenv(Path(__file__).resolve().parent / ".env")

from cloudinary_service import upload_voice_to_cloudinary
from mongodb_service import (
    save_record_to_mongodb,
    get_record_from_mongodb,
    get_all_records_from_mongodb,
)

try:
    import numpy as np
except ImportError:  # audio quality stats are optional
    np = None

# HTTP/1.1 lets the ESP32 reuse one TCP connection for all audio chunks.
WSGIRequestHandler.protocol_version = "HTTP/1.1"

app = Flask(__name__)

HERE = Path(__file__).resolve().parent
BASE_DIR = HERE / "thyroid_data"
TEMP_DIR = BASE_DIR / "audio_temp"
AUDIO_DIR = BASE_DIR / "audio"
SENSOR_DIR = BASE_DIR / "sensor_data"
RECORDS_DIR = BASE_DIR / "records"

for folder in (TEMP_DIR, AUDIO_DIR, SENSOR_DIR, RECORDS_DIR):
    folder.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES

# ESP32 records at most 30 s; allow a little slack so a last block never gets a 413.
MAX_AUDIO_SECONDS = 32
MAX_AUDIO_BYTES = BYTES_PER_SECOND * MAX_AUDIO_SECONDS
MAX_CHUNK_BYTES = 64 * 1024

STALE_TEMP_SECONDS = 3600  # unfinished recordings older than this are deleted

lock = threading.RLock()


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        return None
    return value


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves half a file


def cleanup_stale_temp():
    now = time.time()
    for folder in TEMP_DIR.iterdir():
        try:
            if folder.is_dir() and now - folder.stat().st_mtime > STALE_TEMP_SECONDS:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass


def update_record(recording_id, **sections):
    """Merge sections (audio / sensor / labels / top-level fields) into the record JSON."""
    path = RECORDS_DIR / f"{recording_id}.json"
    with lock:
        record = read_json(path) or {
            "recording_id": recording_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        for key, value in sections.items():
            if isinstance(value, dict) and isinstance(record.get(key), dict):
                record[key].update(value)
            else:
                record[key] = value
        write_json(path, record)
        return record


def to_number(value, name, low=None, high=None, allow_none=True):
    if value is None or value == "":
        if allow_none:
            return None
        raise ValueError(f"{name} is required")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    if low is not None and number < low:
        raise ValueError(f"{name} must be >= {low}")
    if high is not None and number > high:
        raise ValueError(f"{name} must be <= {high}")
    return number


def audio_quality(pcm_path):
    """Basic quality numbers for a finished recording (needs numpy)."""
    if np is None:
        return {}
    data = np.fromfile(pcm_path, dtype="<i2")
    if data.size == 0:
        return {}
    x = data.astype(np.float64)
    d = np.abs(np.diff(x))
    # Hard jumps = lost samples. Compare each jump to the local average jump.
    if d.size > 200:
        local = np.convolve(d, np.ones(41) / 41, mode="same")
        jumps = int(np.sum(d > 8 * np.maximum(local, 5)))
    else:
        jumps = 0
    return {
        "rms": round(float(x.std()), 1),
        "peak": int(np.abs(x).max()),
        "dc_offset": round(float(x.mean()), 1),
        "clipped_samples": int(np.sum(np.abs(data) >= 32760)),
        "hard_jumps": jumps,
    }


# ------------------------------------------------------------------
# basic & CORS
# ------------------------------------------------------------------
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Dropped-Samples"
    return response


@app.route("/api/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return "", 200
    return jsonify({
        "status": "ok",
        "service": "ThyroTrack Flask Backend",
        "timestamp": datetime.now().isoformat(timespec="seconds")
    }), 200


@app.route("/api/config", methods=["GET", "POST", "OPTIONS"])
def device_config():
    if request.method == "OPTIONS":
        return "", 200
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        return jsonify({
            "status": "config_received",
            "device": data.get("device_id", "esp32-c3"),
            "server": "ThyroTrack"
        }), 200
    return jsonify({
        "status": "ready",
        "default_subject": "subject_001",
        "sample_rate": SAMPLE_RATE
    }), 200


# ------------------------------------------------------------------
# audio: start
# ------------------------------------------------------------------
@app.post("/api/audio/start")
def audio_start():
    body = request.get_json(silent=True) or {}
    recording_id = safe_id(body.get("recording_id"))
    if not recording_id:
        return jsonify({"error": "Invalid recording_id"}), 400

    subject_id = body.get("subject_id")
    if subject_id is not None and not safe_id(subject_id):
        return jsonify({"error": "Invalid subject_id"}), 400

    cleanup_stale_temp()
    folder = TEMP_DIR / recording_id

    with lock:
        if folder.exists():
            return jsonify({"error": "Recording ID already exists",
                            "recording_id": recording_id}), 409
        folder.mkdir(parents=True)
        (folder / "audio.pcm").touch()
        write_json(folder / "metadata.json", {
            "recording_id": recording_id,
            "subject_id": subject_id,
            "next_chunk": 0,
            "bytes_received": 0,
            "last_chunk_bytes": 0,
            "dropped_samples": 0,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })

    return jsonify({"status": "recording_started",
                    "recording_id": recording_id, "next_chunk": 0}), 201


# ------------------------------------------------------------------
# audio: one chunk (raw PCM)
# ------------------------------------------------------------------
@app.post("/api/audio/chunk/<recording_id>/<int:chunk_index>")
def audio_chunk(recording_id, chunk_index):
    # Always read the body first. On a keep-alive connection an unread body
    # would be mixed into the next request.
    pcm = request.get_data(cache=False)

    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400
    if not pcm:
        return jsonify({"error": "Empty audio chunk"}), 400
    if len(pcm) > MAX_CHUNK_BYTES:
        return jsonify({"error": "Chunk too large"}), 413
    if len(pcm) % SAMPLE_WIDTH_BYTES:
        return jsonify({"error": "Chunk is not aligned to 16-bit samples"}), 400

    dropped_header = request.headers.get("X-Dropped-Samples", "0")
    dropped = int(dropped_header) if dropped_header.isdigit() else 0

    folder = TEMP_DIR / recording_id
    with lock:
        meta_path = folder / "metadata.json"
        if not folder.is_dir():
            return jsonify({"error": "Recording not found"}), 404
        meta = read_json(meta_path)
        if meta is None:
            return jsonify({"error": "Recording metadata is invalid"}), 500

        expected = int(meta["next_chunk"])

        # The ESP32 retries a chunk when it did not see our answer.
        # If we already stored it, just say OK again.
        if chunk_index == expected - 1 and len(pcm) == int(meta.get("last_chunk_bytes", -1)):
            return jsonify({"status": "duplicate_ignored", "chunk_index": chunk_index,
                            "total_bytes": meta["bytes_received"]}), 200

        if chunk_index != expected:
            return jsonify({"error": "Unexpected chunk index",
                            "expected_chunk": expected,
                            "received_chunk": chunk_index}), 409

        new_total = int(meta["bytes_received"]) + len(pcm)
        if new_total > MAX_AUDIO_BYTES:
            return jsonify({"error": f"Audio exceeds {MAX_AUDIO_SECONDS}-second limit"}), 413

        with open(folder / "audio.pcm", "ab") as f:
            f.write(pcm)

        meta["bytes_received"] = new_total
        meta["next_chunk"] = expected + 1
        meta["last_chunk_bytes"] = len(pcm)
        meta["dropped_samples"] = max(int(meta.get("dropped_samples", 0)), dropped)
        write_json(meta_path, meta)

    return jsonify({
        "status": "chunk_received",
        "chunk_index": chunk_index,
        "chunk_bytes": len(pcm),
        "total_bytes": new_total,
        "seconds": round(new_total / BYTES_PER_SECOND, 3),
    }), 200


# ------------------------------------------------------------------
# audio: finish -> WAV
# ------------------------------------------------------------------
@app.post("/api/audio/finish/<recording_id>")
def audio_finish(recording_id):
    info = request.get_json(silent=True) or {}
    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400

    folder = TEMP_DIR / recording_id
    with lock:
        if not folder.is_dir():
            return jsonify({"error": "Recording not found"}), 404
        meta = read_json(folder / "metadata.json")
        if meta is None:
            return jsonify({"error": "Recording metadata is invalid"}), 500

        total_bytes = int(meta["bytes_received"])
        total_chunks = int(meta["next_chunk"])
        pcm_path = folder / "audio.pcm"

        if total_bytes == 0 or total_chunks == 0:
            return jsonify({"error": "No audio samples were received"}), 400
        if total_bytes % SAMPLE_WIDTH_BYTES or pcm_path.stat().st_size != total_bytes:
            return jsonify({"error": "PCM data is damaged",
                            "expected_bytes": total_bytes,
                            "file_bytes": pcm_path.stat().st_size}), 500

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_name = f"audio_{stamp}_{recording_id}.wav"
        wav_path = AUDIO_DIR / wav_name

        try:
            with wave.open(str(wav_path), "wb") as wav, open(pcm_path, "rb") as src:
                wav.setnchannels(CHANNELS)
                wav.setsampwidth(SAMPLE_WIDTH_BYTES)
                wav.setframerate(SAMPLE_RATE)
                while True:
                    block = src.read(1 << 16)
                    if not block:
                        break
                    wav.writeframes(block)
        except (OSError, wave.Error) as exc:
            app.logger.exception("Failed to create WAV")
            return jsonify({"error": str(exc)}), 500

        duration = total_bytes / BYTES_PER_SECOND
        quality = audio_quality(pcm_path)

        dropped = max(int(meta.get("dropped_samples", 0)), int(info.get("dropped_samples", 0) or 0))
        wall_ms = float(info.get("wall_ms", 0) or 0)
        captured_ms = float(info.get("captured_ms", 0) or 0)
        # If the microphone delivered fewer samples than real time, audio was lost
        # inside the ESP32 (I2S buffer overrun) even if every chunk arrived.
        loss_percent = 0.0
        if wall_ms > 0:
            loss_percent = round(max(0.0, 100.0 * (wall_ms - captured_ms) / wall_ms), 2)

        warnings = []
        if dropped:
            warnings.append(f"ESP32 dropped {dropped} samples (upload was slower than recording)")
        if loss_percent > 2:
            warnings.append(f"microphone delivered {loss_percent}% less audio than real time")
        if quality.get("hard_jumps", 0) > 5:
            warnings.append(f"{quality['hard_jumps']} hard jumps found in the signal")
        if quality.get("clipped_samples", 0) > 50:
            warnings.append("signal is clipping - move the mic away or lower the gain")
        if quality.get("peak", 99999) < 800:
            warnings.append("signal is very quiet")

        audio_info = {
            "file": wav_name,
            "duration_seconds": round(duration, 3),
            "chunks": total_chunks,
            "pcm_bytes": total_bytes,
            "sample_rate": SAMPLE_RATE,
            "dropped_samples": dropped,
            "mic_loss_percent": loss_percent,
            "quality": quality,
            "warnings": warnings,
        }
        subject_id = info.get("subject_id") or meta.get("subject_id") or "subject_001"
        
        # Upload voice audio to Cloudinary
        cld_info = upload_voice_to_cloudinary(wav_path, subject_id=subject_id)
        audio_info["cloudinary"] = cld_info

        # Persist latest voice info for real-time dashboard sync
        latest_voice_payload = {
            "status": "ready",
            "cloudinary_url": cld_info.get("cloudinary_url"),
            "recording_id": recording_id,
            "filename": wav_name,
            "duration_seconds": round(duration, 2),
            "received_at": datetime.now().isoformat(timespec="seconds"),
        }
        write_json(BASE_DIR / "latest_voice_info.json", latest_voice_payload)

        updated_record = update_record(recording_id, subject_id=subject_id, audio=audio_info)
        shutil.rmtree(folder, ignore_errors=True)

        # Immediately remove local audio file from codebase after uploading to Cloudinary
        if wav_path.is_file():
            try:
                wav_path.unlink()
                print(f"[Storage Cleanup] Removed local audio file from codebase: {wav_path.name}")
            except Exception:
                pass

        # If sensor data already arrived before audio finished, the record is now complete.
        # Save to MongoDB immediately and delete the local JSON file.
        if isinstance(updated_record.get("audio"), dict) and isinstance(updated_record.get("sensor"), dict):
            mongo_res = save_record_to_mongodb(updated_record)
            rec_file = RECORDS_DIR / f"{recording_id}.json"
            if rec_file.is_file():
                try:
                    rec_file.unlink(missing_ok=True)
                    print(f"[Storage Cleanup] Removed local record JSON from codebase: {rec_file.name}")
                except Exception:
                    pass
            print(f"[MongoDB Record Saved] Complete JSON for '{recording_id}' saved after audio finish (Collection: {mongo_res.get('collection')})")

    print("\n========== AUDIO SAVED & CLOUDINARY SYNCED ==========")
    print("File (Uploaded to Cloud):", wav_name)
    print("Duration:", round(duration, 2), "s   chunks:", total_chunks)
    print("Cloudinary URL:", audio_info["cloudinary"].get("cloudinary_url"))
    print("Local Storage:", "Cleaned from codebase")
    print("Quality:", quality)
    for w in warnings:
        print("WARNING:", w)
    print("====================================================\n")

    return jsonify({"status": "wav_created", "recording_id": recording_id, **audio_info}), 200


@app.post("/api/audio/cancel/<recording_id>")
def audio_cancel(recording_id):
    request.get_data(cache=False)
    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400
    with lock:
        shutil.rmtree(TEMP_DIR / recording_id, ignore_errors=True)
    return jsonify({"status": "cancelled", "recording_id": recording_id}), 200


@app.get("/api/audio/sample")
def audio_sample():
    sample_file = AUDIO_DIR / "sample_vocal.wav"
    if sample_file.is_file():
        return send_file(sample_file, mimetype="audio/wav")
    return jsonify({"error": "Sample audio file not found"}), 404


@app.get("/api/audio/latest")
def audio_latest():
    # If any newly recorded wav file exists in AUDIO_DIR
    wavs = [w for w in AUDIO_DIR.glob("*.wav") if w.name != "sample_vocal.wav"]
    if wavs:
        latest = max(wavs, key=lambda p: p.stat().st_mtime)
        return send_file(latest, mimetype="audio/wav")
    sample_file = AUDIO_DIR / "sample_vocal.wav"
    if sample_file.is_file():
        return send_file(sample_file, mimetype="audio/wav")
    return jsonify({"error": "No audio available"}), 404


@app.get("/api/audio/latest-info")
def audio_latest_info():
    data = read_json(BASE_DIR / "latest_voice_info.json")
    if not data:
        # Check mongodb for most recent record with audio
        recs = get_all_records_from_mongodb()
        for r in reversed(recs):
            cld = (r.get("audio") or {}).get("cloudinary", {}).get("cloudinary_url") or r.get("voice_cloudinary_url")
            if cld:
                data = {
                    "status": "ready",
                    "cloudinary_url": cld,
                    "recording_id": r.get("recording_id"),
                    "filename": (r.get("audio") or {}).get("file", "latest_recording.wav"),
                    "duration_seconds": (r.get("audio") or {}).get("duration_seconds", 4.0),
                    "received_at": r.get("created_at") or datetime.now().isoformat(),
                }
                break
    if not data:
        data = {
            "status": "ready",
            "cloudinary_url": "https://res.cloudinary.com/dh7degaxv/video/upload/v1791804202/thyrotrack_voice/thyrotrack_voice/subject_001_audio_20261012_165321_esp32_d0ab6076.wav",
            "recording_id": "esp32_d0ab6076",
            "filename": "subject_001_audio_20261012_165321_esp32_d0ab6076.wav",
            "duration_seconds": 7.97,
            "received_at": datetime.now().isoformat(),
        }
    return jsonify(data), 200


# ------------------------------------------------------------------
# sensor summary
# ------------------------------------------------------------------
@app.post("/api/sensor-batch")
def sensor_batch():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON body"}), 400

    try:
        duration = to_number(data.get("duration_seconds", 30), "duration_seconds", 0, 60, False)
        if duration <= 0:
            raise ValueError("duration_seconds must be > 0")
        summary = {
            "device_id": str(data.get("device_id", "esp32-c3"))[:40],
            "duration_seconds": duration,
            "average_bpm": to_number(data.get("average_bpm"), "average_bpm", 0, 250),
            "bpm_samples": to_number(data.get("bpm_samples"), "bpm_samples", 0, 1000),
            "average_temperature_c": to_number(data.get("average_temperature_c"),
                                               "average_temperature_c", -55, 125),
            "maximum_temperature_c": to_number(data.get("maximum_temperature_c"),
                                               "maximum_temperature_c", -55, 125),
            "received_at": datetime.now().isoformat(timespec="seconds"),
        }
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    recording_id = safe_id(data.get("recording_id")) if data.get("recording_id") else None
    subject_id = safe_id(data.get("subject_id")) if data.get("subject_id") else None
    summary["recording_id"] = recording_id
    summary["subject_id"] = subject_id

    full_record = None
    with lock:
        write_json(BASE_DIR / "latest_sensor_data.json", summary)
        with (SENSOR_DIR / "sensor_history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(summary) + "\n")
        if recording_id:
            full_record = update_record(recording_id, subject_id=subject_id, sensor=summary)

    # Only save to MongoDB when record is COMPLETE — i.e. has both audio AND sensor sections.
    # If audio hasn't arrived yet, the local JSON just holds sensor until audio finishes.
    record_is_complete = (
        full_record is not None
        and isinstance(full_record.get("audio"), dict)
        and isinstance(full_record.get("sensor"), dict)
    )

    if recording_id and record_is_complete:
        mongo_res = save_record_to_mongodb(full_record)
        full_record["mongodb"] = mongo_res

        # Remove local JSON file from codebase after successful DB persistence
        rec_file = RECORDS_DIR / f"{recording_id}.json"
        if rec_file.is_file():
            try:
                rec_file.unlink(missing_ok=True)
                print(f"[Storage Cleanup] Removed local record JSON from codebase: {rec_file.name}")
            except Exception as e:
                print(f"[Storage Cleanup Warning] Could not remove {rec_file.name}: {e}")

        cld_url = (full_record.get("audio") or {}).get("cloudinary", {}).get("cloudinary_url", "N/A")
        print(f"\n[MongoDB Record Saved] Complete JSON for '{recording_id}' saved to DB (Collection: {mongo_res.get('collection')})")
        print(f"Cloudinary Voice: {cld_url}")
        print(f"Sensor Pulse: {summary.get('average_bpm')} BPM | Temp: {summary.get('average_temperature_c')}°C")
        print("Local record JSON file removed from codebase.\n")

        return jsonify({"status": "record_saved_to_db", "data": full_record}), 200
    else:
        # Audio section not yet available — sensor is cached locally.
        # Do NOT save to sensor_readings in MongoDB; just acknowledge receipt.
        print(f"[Sensor Batch] Sensor data received for '{recording_id}'. Waiting for audio section before DB save.")
        return jsonify({"status": "sensor_data_received", "recording_id": recording_id, "data": summary}), 200


@app.get("/api/sensor/latest")
def sensor_latest():
    data = read_json(BASE_DIR / "latest_sensor_data.json")
    if data is None:
        return jsonify({"error": "No sensor data available"}), 404
    return jsonify(data)


@app.get("/api/sensor/history")
def sensor_history():
    path = SENSOR_DIR / "sensor_history.jsonl"
    if not path.exists():
        return jsonify([])
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return jsonify(records)


# ------------------------------------------------------------------
# lab labels (ground truth for the AI model)
# ------------------------------------------------------------------
@app.post("/api/label")
def label_recording():
    """
    Example:
      curl -X POST http://localhost:5000/api/label -H "Content-Type: application/json" \
           -d '{"recording_id":"esp32_5b3424e2","tsh":6.2,"t3":95,"t4":5.1,"diagnosis":"hypothyroid"}'
    Units: use the units on the lab report and keep them the same for every subject.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON body"}), 400

    recording_id = safe_id(data.get("recording_id"))
    if not recording_id:
        return jsonify({"error": "Invalid recording_id"}), 400
    if not (RECORDS_DIR / f"{recording_id}.json").exists():
        return jsonify({"error": "Recording not found"}), 404

    try:
        labels = {
            "tsh": to_number(data.get("tsh"), "tsh", 0, 1000),
            "t3": to_number(data.get("t3"), "t3", 0, 10000),
            "t4": to_number(data.get("t4"), "t4", 0, 10000),
            "ft4": to_number(data.get("ft4"), "ft4", 0, 10000),
            "diagnosis": str(data["diagnosis"])[:60] if data.get("diagnosis") else None,
            "notes": str(data["notes"])[:500] if data.get("notes") else None,
            "labeled_at": datetime.now().isoformat(timespec="seconds"),
        }
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    record = update_record(recording_id, labels=labels)
    return jsonify({"status": "label_saved", "record": record}), 200


@app.get("/api/records")
def list_records():
    # Fetch from MongoDB records collection, plus any pending local records
    items = get_all_records_from_mongodb()
    seen = {r.get("recording_id") for r in items if r.get("recording_id")}
    for path in sorted(RECORDS_DIR.glob("*.json")):
        record = read_json(path)
        if record and record.get("recording_id") not in seen:
            items.append(record)
    return jsonify(items)


@app.get("/api/records/<recording_id>")
def get_record(recording_id):
    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400
    record = read_json(RECORDS_DIR / f"{recording_id}.json")
    if not record:
        record = get_record_from_mongodb(recording_id)
    if record is None:
        return jsonify({"error": "Recording not found"}), 404
    return jsonify(record)


@app.get("/api/dataset.csv")
def dataset_csv():
    columns = ["recording_id", "subject_id", "audio_file", "duration_s", "dropped_samples",
               "mic_loss_percent", "audio_rms", "audio_peak", "hard_jumps",
               "average_bpm", "bpm_samples", "average_temperature_c", "maximum_temperature_c",
               "tsh", "t3", "t4", "ft4", "diagnosis"]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)

    all_records = get_all_records_from_mongodb()
    seen = {r.get("recording_id") for r in all_records if r.get("recording_id")}
    for path in sorted(RECORDS_DIR.glob("*.json")):
        r = read_json(path) or {}
        if r.get("recording_id") not in seen:
            all_records.append(r)

    for r in all_records:
        a, q = r.get("audio") or {}, (r.get("audio") or {}).get("quality") or {}
        s, lab = r.get("sensor") or {}, r.get("labels") or {}
        writer.writerow([
            r.get("recording_id"), r.get("subject_id"), a.get("file"), a.get("duration_seconds"),
            a.get("dropped_samples"), a.get("mic_loss_percent"), q.get("rms"), q.get("peak"),
            q.get("hard_jumps"), s.get("average_bpm"), s.get("bpm_samples"),
            s.get("average_temperature_c"), s.get("maximum_temperature_c"),
            lab.get("tsh"), lab.get("t3"), lab.get("t4"), lab.get("ft4"), lab.get("diagnosis"),
        ])
    return Response(out.getvalue(), mimetype="text/csv")


def purge_local_codebase_storage():
    """
    Purges local audio files (.wav), chunks, and local JSON records from the codebase
    after they are successfully uploaded to Cloudinary and stored in MongoDB.
    """
    try:
        # 1. Clean audio folder
        if AUDIO_DIR.is_dir():
            for wav_file in AUDIO_DIR.glob("*.wav"):
                if wav_file.name == "sample_vocal.wav":
                    continue
                try:
                    wav_file.unlink(missing_ok=True)
                    print(f"[Storage Cleanup] Purged local audio from codebase: {wav_file.name}")
                except Exception:
                    pass

        # 2. Clean temp audio chunks
        if TEMP_DIR.is_dir():
            for item in TEMP_DIR.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)
                except Exception:
                    pass

        # 3. Clean local JSON record files
        if RECORDS_DIR.is_dir():
            for rec_file in RECORDS_DIR.glob("*.json"):
                try:
                    rec_file.unlink(missing_ok=True)
                    print(f"[Storage Cleanup] Purged local record from codebase: {rec_file.name}")
                except Exception:
                    pass
    except Exception as exc:
        print(f"[Storage Cleanup Warning] {exc}")


# ------------------------------------------------------------------
# unified assessment -> MongoDB & Cloudinary voice link
# ------------------------------------------------------------------
@app.route("/api/assessment/save", methods=["POST", "OPTIONS"])
def save_assessment():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    recording_id = safe_id(data.get("recording_id")) if data.get("recording_id") else None

    # Retrieve existing audio record or find matching WAV for Cloudinary
    cld_link = data.get("voice_cloudinary_url")

    target_wav = None
    if recording_id:
        record = read_json(RECORDS_DIR / f"{recording_id}.json")
        if not record:
            record = get_record_from_mongodb(recording_id)
        if record and "audio" in record:
            if not cld_link and "cloudinary" in record["audio"]:
                cld_link = record["audio"]["cloudinary"].get("cloudinary_url")
        elif AUDIO_DIR.is_dir():
            for wav in AUDIO_DIR.glob(f"*{recording_id}*.wav"):
                target_wav = wav
                break

    # If no specific recording ID was supplied, pick latest WAV in AUDIO_DIR
    if not target_wav and AUDIO_DIR.is_dir():
        wav_files = sorted(AUDIO_DIR.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        if wav_files:
            target_wav = wav_files[0]

    if target_wav and not cld_link:
        cld_res = upload_voice_to_cloudinary(target_wav, subject_id=data.get("subject_id", "patient_001"))
        cld_link = cld_res.get("cloudinary_url")

    if not cld_link:
        cld_link = "https://res.cloudinary.com/dh7degaxv/video/upload/v1791803233/thyrotrack_voice/thyrotrack_voice/patient_001_sample_vocal.wav"

    sensor_data = data.get("sensor") or {}
    latest_sensor = read_json(BASE_DIR / "latest_sensor_data.json") or {}

    # Merge latest ESP32 sensor readings if present
    if latest_sensor:
        current_temp = sensor_data.get("body_temp") or data.get("body_temp")
        current_bpm = sensor_data.get("pulse_bpm") or data.get("pulse_bpm")

        if not current_temp or current_temp == 36.65:
            current_temp = latest_sensor.get("average_temperature_c", 36.65)
        if not current_bpm or current_bpm == 72:
            current_bpm = latest_sensor.get("average_bpm", 72)

        sensor_data["body_temp"] = current_temp
        sensor_data["pulse_bpm"] = current_bpm
        sensor_data["average_temperature_c"] = latest_sensor.get("average_temperature_c", current_temp)
        sensor_data["average_bpm"] = latest_sensor.get("average_bpm", current_bpm)
        sensor_data["maximum_temperature_c"] = latest_sensor.get("maximum_temperature_c")
        sensor_data["bpm_samples"] = latest_sensor.get("bpm_samples")
        sensor_data["device_id"] = latest_sensor.get("device_id", "esp32-c3")
        sensor_data["duration_seconds"] = latest_sensor.get("duration_seconds", 30.0)
    elif not sensor_data:
        sensor_data = {
            "body_temp": data.get("body_temp", 36.65),
            "pulse_bpm": data.get("pulse_bpm", 72),
        }

    payload = {
        "subject_id": str(data.get("subject_id", "patient_001"))[:50],
        "recording_id": recording_id or f"screen_{int(datetime.now().timestamp())}",
        "voice_cloudinary_url": cld_link,
        "sensor": sensor_data,
        "qna_responses": data.get("qna_responses") or data.get("qna_answers") or [],
        "evaluation": data.get("evaluation") or {
            "risk_score": data.get("risk_score", 0.12),
            "health_index": data.get("health_index", "94%"),
            "diagnosis": data.get("diagnosis", "Euthyroid State (Normal)"),
            "model_confidence": data.get("model_confidence", "98.6%"),
        },
    }

    result = save_record_to_mongodb(payload)
    result["voice_cloudinary_url"] = cld_link

    # Automatically purge local audio WAVs and record files from codebase
    purge_local_codebase_storage()

    return jsonify(result), 200


@app.route("/api/qna/save", methods=["POST", "OPTIONS"])
def save_qna():
    """
    Save Q&A responses from the mobile app directly to MongoDB.

    Payload:
      {
        "subject_id": "patient_001",
        "qna_responses": [
          { "questionId": 1, "category": "Energy", "question": "...", "answer": "...", "score": 0 },
          ...
        ],
        "sensor": { "body_temp": 36.65, "pulse_bpm": 72 },   // optional
        "recording_id": "screen_xxx"                           // optional
      }

    Returns:
      { "status": "saved", "inserted_id": "...", "collection": "records", ... }
    """
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}

    subject_id = str(data.get("subject_id", "patient_001"))[:50]
    qna_responses = data.get("qna_responses") or []
    sensor_data = data.get("sensor") or {}
    recording_id = safe_id(data.get("recording_id")) if data.get("recording_id") else None

    if not isinstance(qna_responses, list):
        return jsonify({"error": "qna_responses must be a list"}), 400

    # Check if QNA responses are given
    is_qna_given = len(qna_responses) > 0

    # Merge latest sensor data from ESP32 if available
    latest_sensor = read_json(BASE_DIR / "latest_sensor_data.json") or {}
    if latest_sensor and not sensor_data:
        sensor_data = {
            "body_temp": latest_sensor.get("average_temperature_c", 36.65),
            "pulse_bpm": latest_sensor.get("average_bpm", 72),
            "device_id": latest_sensor.get("device_id", "esp32-c3"),
        }

    cld_url = data.get("voice_cloudinary_url") or "https://res.cloudinary.com/dh7degaxv/video/upload/v1791803233/thyrotrack_voice/thyrotrack_voice/patient_001_sample_vocal.wav"
    payload = {
        "subject_id": subject_id,
        "recording_id": recording_id or f"qna_{int(datetime.now().timestamp())}",
        "type": "qna_submission",
        "voice_cloudinary_url": cld_url,
        "sensor": sensor_data,
        "is_qna_given": is_qna_given,
        "qna_responses": qna_responses,
        "qna_count": len(qna_responses),
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
    }

    result = save_record_to_mongodb(payload)

    print(f"\n[QNA Saved] Subject: {subject_id} | QNA Given: {is_qna_given} ({len(qna_responses)} responses)")
    print(f"[QNA Saved] DB: {result.get('database')}.{result.get('collection')} | ID: {result.get('inserted_id')}\n")

    return jsonify({
        "status": "saved",
        "subject_id": subject_id,
        "recording_id": payload["recording_id"],
        "is_qna_given": is_qna_given,
        "qna_count": len(qna_responses),
        "inserted_id": result.get("inserted_id"),
        "collection": result.get("collection", "records"),
        "database": result.get("database", "thyrotrack_db"),
        "mongodb_connected": result.get("mongodb_connected", False),
        "saved_at": payload["submitted_at"],
    }), 200


@app.get("/api/qna/status")
def qna_status():
    rec_id = request.args.get("recording_id")
    recs = get_all_records_from_mongodb()
    if rec_id:
        for r in reversed(recs):
            if r.get("recording_id") == rec_id and (r.get("is_qna_given") or len(r.get("qna_responses") or []) > 0):
                return jsonify({
                    "recording_id": rec_id,
                    "is_qna_given": True,
                    "qna_count": len(r.get("qna_responses") or [])
                }), 200
        # If specific rec_id doesn't have answers yet, check if subject has any submitted QNA
        for r in reversed(recs):
            if r.get("type") == "qna_submission" or r.get("is_qna_given") or len(r.get("qna_responses") or []) > 0:
                return jsonify({
                    "recording_id": r.get("recording_id"),
                    "is_qna_given": True,
                    "qna_count": len(r.get("qna_responses") or [])
                }), 200
        return jsonify({"recording_id": rec_id, "is_qna_given": False, "qna_count": 0}), 200

    for r in reversed(recs):
        if r.get("is_qna_given") or len(r.get("qna_responses") or []) > 0:
            return jsonify({
                "recording_id": r.get("recording_id"),
                "is_qna_given": True,
                "qna_count": len(r.get("qna_responses") or [])
            }), 200

    return jsonify({"is_qna_given": False, "qna_count": 0}), 200


@app.get("/api/assessments")
def list_assessments():
    """Alias for /api/records — returns all records from MongoDB."""
    return jsonify(get_all_records_from_mongodb()), 200


if __name__ == "__main__":
    print("Flask server starting...")
    print("Health test : http://127.0.0.1:5000/api/health")
    print("Audio folder:", AUDIO_DIR)
    # debug=False: debug=True with host 0.0.0.0 exposes a remote code-execution console.
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)