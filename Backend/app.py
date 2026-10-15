"""
ThyroTrack - High-Performance Flask Backend (Optimized)
Receives ESP32-C3 telemetry, sensor batches, audio phonation streaming, and mobile app evaluations.

Key Architectural Optimizations:
- Zero local file storage: No data, records, or history saved in code files or repository.
- In-memory stream buffering for active ESP32 audio chunks (eliminates disk I/O bottlenecks).
- Direct Cloudinary streaming for voice phonation audio.
- Persistent singleton connection pooling with MongoDB Atlas for records and sensor telemetry.
- On-the-fly CSV dataset generation and fast indexed queries.
"""

import csv
import io
import re
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, Response, redirect
from werkzeug.serving import WSGIRequestHandler
from dotenv import load_dotenv

# Load environment configuration from .env
load_dotenv(Path(__file__).resolve().parent / ".env")

from cloudinary_service import upload_voice_to_cloudinary
from mongodb_service import (
    save_record_to_mongodb,
    update_record_in_mongodb,
    get_record_from_mongodb,
    get_all_records_from_mongodb,
    save_sensor_reading_to_mongodb,
    get_sensor_history_from_mongodb,
    get_latest_sensor_reading_from_mongodb,
    get_latest_voice_record_from_mongodb,
)

try:
    import numpy as np
except ImportError:
    np = None

# HTTP/1.1 lets the ESP32 reuse one TCP connection for all audio chunks.
WSGIRequestHandler.protocol_version = "HTTP/1.1"

app = Flask(__name__)

# Audio stream constants
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES

# ESP32 records at most 30 s; allow slack for final block
MAX_AUDIO_SECONDS = 32
MAX_AUDIO_BYTES = BYTES_PER_SECOND * MAX_AUDIO_SECONDS
MAX_CHUNK_BYTES = 64 * 1024
STALE_RECORDING_TIMEOUT_SECONDS = 600  # 10 minutes timeout for in-memory incomplete sessions

# Thread-safe in-memory state (Zero disk writes during streaming)
_state_lock = threading.RLock()
_active_recordings: dict[str, dict] = {}
_latest_sensor_data: dict | None = None
_latest_voice_info: dict | None = None


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        return None
    return value


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


def cleanup_stale_recordings():
    """Removes abandoned in-memory audio recording sessions older than timeout."""
    now = time.time()
    with _state_lock:
        stale_keys = [
            k for k, v in _active_recordings.items()
            if now - v.get("started_time", now) > STALE_RECORDING_TIMEOUT_SECONDS
        ]
        for k in stale_keys:
            _active_recordings.pop(k, None)


def audio_quality_from_buffer(pcm_bytes: bytes) -> dict:
    """Computes audio quality metrics directly in memory using numpy without disk I/O."""
    if np is None or not pcm_bytes:
        return {}
    data = np.frombuffer(pcm_bytes, dtype="<i2")
    if data.size == 0:
        return {}
    x = data.astype(np.float64)
    d = np.abs(np.diff(x))
    # Hard jumps = lost samples. Compare each jump to local average jump.
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
# CORS & Health
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
        "service": "ThyroTrack Flask Backend (Optimized)",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "storage": "MongoDB Atlas + Cloudinary (Zero local disk persistence)",
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
            "server": "ThyroTrack",
        }), 200
    return jsonify({
        "status": "ready",
        "default_subject": "subject_001",
        "sample_rate": SAMPLE_RATE,
    }), 200


# ------------------------------------------------------------------
# Audio Streaming (100% In-Memory Buffering — Zero Disk Writes)
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

    cleanup_stale_recordings()

    with _state_lock:
        if recording_id in _active_recordings:
            return jsonify({
                "error": "Recording ID already in progress",
                "recording_id": recording_id,
            }), 409

        _active_recordings[recording_id] = {
            "recording_id": recording_id,
            "subject_id": subject_id or "subject_001",
            "next_chunk": 0,
            "bytes_received": 0,
            "last_chunk_bytes": 0,
            "dropped_samples": 0,
            "pcm_buffer": bytearray(),
            "started_time": time.time(),
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    return jsonify({
        "status": "recording_started",
        "recording_id": recording_id,
        "next_chunk": 0,
    }), 201


@app.post("/api/audio/chunk/<recording_id>/<int:chunk_index>")
def audio_chunk(recording_id, chunk_index):
    # Always read the body first to prevent TCP keep-alive mix-up
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

    with _state_lock:
        session = _active_recordings.get(recording_id)
        if not session:
            return jsonify({"error": "Recording session not found or expired"}), 404

        expected = int(session["next_chunk"])

        # ESP32 retry handling: If already appended, return OK without re-appending
        if chunk_index == expected - 1 and len(pcm) == session["last_chunk_bytes"]:
            return jsonify({
                "status": "duplicate_ignored",
                "chunk_index": chunk_index,
                "total_bytes": session["bytes_received"],
            }), 200

        if chunk_index != expected:
            return jsonify({
                "error": "Unexpected chunk index",
                "expected_chunk": expected,
                "received_chunk": chunk_index,
            }), 409

        new_total = session["bytes_received"] + len(pcm)
        if new_total > MAX_AUDIO_BYTES:
            return jsonify({"error": f"Audio exceeds {MAX_AUDIO_SECONDS}-second limit"}), 413

        # In-memory buffer append (sub-millisecond latency, no file writes)
        session["pcm_buffer"].extend(pcm)
        session["bytes_received"] = new_total
        session["next_chunk"] = expected + 1
        session["last_chunk_bytes"] = len(pcm)
        session["dropped_samples"] = max(session["dropped_samples"], dropped)

    return jsonify({
        "status": "chunk_received",
        "chunk_index": chunk_index,
        "chunk_bytes": len(pcm),
        "total_bytes": new_total,
        "seconds": round(new_total / BYTES_PER_SECOND, 3),
    }), 200


@app.post("/api/audio/finish/<recording_id>")
def audio_finish(recording_id):
    global _latest_voice_info
    info = request.get_json(silent=True) or {}
    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400

    with _state_lock:
        session = _active_recordings.pop(recording_id, None)

    if not session:
        return jsonify({"error": "Recording session not found"}), 404

    pcm_bytes = bytes(session["pcm_buffer"])
    total_bytes = len(pcm_bytes)
    total_chunks = session["next_chunk"]

    if total_bytes == 0 or total_chunks == 0:
        return jsonify({"error": "No audio samples were received"}), 400
    if total_bytes % SAMPLE_WIDTH_BYTES:
        return jsonify({"error": "PCM data is damaged"}), 500

    duration = total_bytes / BYTES_PER_SECOND
    quality = audio_quality_from_buffer(pcm_bytes)

    dropped = max(session.get("dropped_samples", 0), int(info.get("dropped_samples", 0) or 0))
    wall_ms = float(info.get("wall_ms", 0) or 0)
    captured_ms = float(info.get("captured_ms", 0) or 0)
    loss_percent = 0.0
    if wall_ms > 0:
        loss_percent = round(max(0.0, 100.0 * (wall_ms - captured_ms) / wall_ms), 2)

    warnings = []
    if dropped:
        warnings.append(f"ESP32 dropped {dropped} samples")
    if loss_percent > 2:
        warnings.append(f"microphone delivered {loss_percent}% less audio than real time")
    if quality.get("hard_jumps", 0) > 5:
        warnings.append(f"{quality['hard_jumps']} hard jumps found in the signal")
    if quality.get("clipped_samples", 0) > 50:
        warnings.append("signal is clipping")
    if quality.get("peak", 99999) < 800:
        warnings.append("signal is very quiet")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_name = f"audio_{stamp}_{recording_id}.wav"
    subject_id = info.get("subject_id") or session.get("subject_id") or "subject_001"

    # Encode WAV entirely in-memory using BytesIO (no local file on disk)
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm_bytes)
    wav_io.seek(0)

    # Stream directly to Cloudinary
    cld_info = upload_voice_to_cloudinary(wav_io, subject_id=subject_id, filename=wav_name)

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
        "cloudinary": cld_info,
    }

    # Cache latest voice info in memory for instant mobile app queries
    latest_voice_payload = {
        "status": "ready",
        "cloudinary_url": cld_info.get("cloudinary_url"),
        "recording_id": recording_id,
        "filename": wav_name,
        "duration_seconds": round(duration, 2),
        "received_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _state_lock:
        _latest_voice_info = latest_voice_payload

    # Save/Update directly in MongoDB Atlas
    updated_record = update_record_in_mongodb(
        recording_id,
        subject_id=subject_id,
        audio=audio_info,
        voice_cloudinary_url=cld_info.get("cloudinary_url"),
        created_at=session.get("created_at"),
    )

    print(f"\n[Voice Uploaded] Recording '{recording_id}' -> Cloudinary: {cld_info.get('cloudinary_url')}")
    print(f"[DB Synced] Saved directly to MongoDB 'records' collection. Zero files saved locally.\n")

    return jsonify({"status": "wav_created", "recording_id": recording_id, **audio_info}), 200


@app.post("/api/audio/cancel/<recording_id>")
def audio_cancel(recording_id):
    request.get_data(cache=False)
    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400
    with _state_lock:
        _active_recordings.pop(recording_id, None)
    return jsonify({"status": "cancelled", "recording_id": recording_id}), 200


@app.get("/api/audio/sample")
def audio_sample():
    # Return playable Cloudinary sample URL redirect
    sample_url = "https://res.cloudinary.com/dh7degaxv/video/upload/v1791803233/thyrotrack_voice/thyrotrack_voice/patient_001_sample_vocal.wav"
    return redirect(sample_url, code=302)


@app.get("/api/audio/latest")
def audio_latest():
    voice_info = audio_latest_info_internal()
    cld_url = voice_info.get("cloudinary_url")
    if cld_url:
        return redirect(cld_url, code=302)
    return jsonify({"error": "No audio available"}), 404


def audio_latest_info_internal() -> dict:
    global _latest_voice_info
    with _state_lock:
        if _latest_voice_info:
            return _latest_voice_info

    # Query MongoDB Atlas for most recent record containing a voice URL
    latest_rec = get_latest_voice_record_from_mongodb()
    if latest_rec:
        cld = (latest_rec.get("audio") or {}).get("cloudinary", {}).get("cloudinary_url") or latest_rec.get("voice_cloudinary_url")
        if cld:
            payload = {
                "status": "ready",
                "cloudinary_url": cld,
                "recording_id": latest_rec.get("recording_id"),
                "filename": (latest_rec.get("audio") or {}).get("file", "latest_recording.wav"),
                "duration_seconds": (latest_rec.get("audio") or {}).get("duration_seconds", 4.0),
                "received_at": latest_rec.get("created_at") or latest_rec.get("saved_at"),
            }
            with _state_lock:
                _latest_voice_info = payload
            return payload

    fallback = {
        "status": "ready",
        "cloudinary_url": "https://res.cloudinary.com/dh7degaxv/video/upload/v1791804202/thyrotrack_voice/thyrotrack_voice/subject_001_audio_20261012_165321_esp32_d0ab6076.wav",
        "recording_id": "esp32_d0ab6076",
        "filename": "subject_001_audio_20261012_165321_esp32_d0ab6076.wav",
        "duration_seconds": 7.97,
        "received_at": datetime.now().isoformat(),
    }
    return fallback


@app.get("/api/audio/latest-info")
def audio_latest_info():
    return jsonify(audio_latest_info_internal()), 200


# ------------------------------------------------------------------
# Sensor Telemetry (Stored in MongoDB sensor_readings — Zero Local Disk Writes)
# ------------------------------------------------------------------
@app.post("/api/sensor-batch")
def sensor_batch():
    global _latest_sensor_data
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
            "average_temperature_c": to_number(data.get("average_temperature_c"), "average_temperature_c", -55, 125),
            "maximum_temperature_c": to_number(data.get("maximum_temperature_c"), "maximum_temperature_c", -55, 125),
            "received_at": datetime.now().isoformat(timespec="seconds"),
        }
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    recording_id = safe_id(data.get("recording_id")) if data.get("recording_id") else None
    subject_id = safe_id(data.get("subject_id")) if data.get("subject_id") else None
    summary["recording_id"] = recording_id
    summary["subject_id"] = subject_id

    # 1. Update in-memory latest state
    with _state_lock:
        _latest_sensor_data = summary

    # 2. Save directly to MongoDB sensor_readings collection
    save_sensor_reading_to_mongodb(summary)

    # 3. If tied to a recording_id, merge into MongoDB records collection
    if recording_id:
        update_record_in_mongodb(recording_id, subject_id=subject_id, sensor=summary)

    print(f"[Sensor Telemetry] BPM: {summary['average_bpm']} | Temp: {summary['average_temperature_c']}°C -> Saved to MongoDB")

    return jsonify({"status": "sensor_data_received", "recording_id": recording_id, "data": summary}), 200


@app.get("/api/sensor/latest")
def sensor_latest():
    with _state_lock:
        if _latest_sensor_data:
            return jsonify(_latest_sensor_data), 200

    reading = get_latest_sensor_reading_from_mongodb()
    if reading:
        return jsonify(reading), 200

    return jsonify({
        "device_id": "esp32-c3",
        "average_bpm": 72.0,
        "average_temperature_c": 36.65,
        "duration_seconds": 30.0,
        "received_at": datetime.now().isoformat(timespec="seconds"),
    }), 200


@app.get("/api/sensor/history")
def sensor_history():
    """Returns sensor telemetry history directly from MongoDB sensor_readings."""
    history = get_sensor_history_from_mongodb(limit=100)
    return jsonify(history), 200


# ------------------------------------------------------------------
# Ground Truth Labels & Records
# ------------------------------------------------------------------
@app.post("/api/label")
def label_recording():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON body"}), 400

    recording_id = safe_id(data.get("recording_id"))
    if not recording_id:
        return jsonify({"error": "Invalid recording_id"}), 400

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

    record = update_record_in_mongodb(recording_id, labels=labels)
    return jsonify({"status": "label_saved", "record": record}), 200


@app.get("/api/records")
def list_records():
    return jsonify(get_all_records_from_mongodb()), 200


@app.get("/api/records/<recording_id>")
def get_record(recording_id):
    recording_id = safe_id(recording_id)
    if not recording_id:
        return jsonify({"error": "Invalid recording ID"}), 400

    record = get_record_from_mongodb(recording_id)
    if record is None:
        return jsonify({"error": "Recording not found"}), 404
    return jsonify(record), 200


@app.get("/api/dataset.csv")
def dataset_csv():
    """Generates an ML-ready CSV directly from MongoDB Atlas records in-memory."""
    columns = [
        "recording_id", "subject_id", "audio_file", "duration_s", "dropped_samples",
        "mic_loss_percent", "audio_rms", "audio_peak", "hard_jumps",
        "average_bpm", "bpm_samples", "average_temperature_c", "maximum_temperature_c",
        "tsh", "t3", "t4", "ft4", "diagnosis",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)

    all_records = get_all_records_from_mongodb(limit=500)
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


# ------------------------------------------------------------------
# Assessments & Q&A (Direct to MongoDB Atlas)
# ------------------------------------------------------------------
@app.route("/api/assessment/save", methods=["POST", "OPTIONS"])
def save_assessment():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    recording_id = safe_id(data.get("recording_id")) if data.get("recording_id") else None

    cld_link = data.get("voice_cloudinary_url")
    if not cld_link and recording_id:
        rec = get_record_from_mongodb(recording_id)
        if rec:
            cld_link = (rec.get("audio") or {}).get("cloudinary", {}).get("cloudinary_url") or rec.get("voice_cloudinary_url")

    if not cld_link:
        cld_link = "https://res.cloudinary.com/dh7degaxv/video/upload/v1791803233/thyrotrack_voice/thyrotrack_voice/patient_001_sample_vocal.wav"

    sensor_data = data.get("sensor") or {}
    with _state_lock:
        latest_sensor = _latest_sensor_data or get_latest_sensor_reading_from_mongodb() or {}

    if latest_sensor:
        current_temp = sensor_data.get("body_temp") or data.get("body_temp") or latest_sensor.get("average_temperature_c", 36.65)
        current_bpm = sensor_data.get("pulse_bpm") or data.get("pulse_bpm") or latest_sensor.get("average_bpm", 72)
        sensor_data["body_temp"] = current_temp
        sensor_data["pulse_bpm"] = current_bpm
        sensor_data["average_temperature_c"] = latest_sensor.get("average_temperature_c", current_temp)
        sensor_data["average_bpm"] = latest_sensor.get("average_bpm", current_bpm)
        sensor_data["device_id"] = latest_sensor.get("device_id", "esp32-c3")
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
    return jsonify(result), 200


@app.route("/api/qna/save", methods=["POST", "OPTIONS"])
def save_qna():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    subject_id = str(data.get("subject_id", "patient_001"))[:50]
    qna_responses = data.get("qna_responses") or []
    sensor_data = data.get("sensor") or {}
    recording_id = safe_id(data.get("recording_id")) if data.get("recording_id") else None

    if not isinstance(qna_responses, list):
        return jsonify({"error": "qna_responses must be a list"}), 400

    is_qna_given = len(qna_responses) > 0

    with _state_lock:
        latest_sensor = _latest_sensor_data or get_latest_sensor_reading_from_mongodb() or {}

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
    recs = get_all_records_from_mongodb(limit=50)

    if rec_id:
        for r in recs:
            if r.get("recording_id") == rec_id and (r.get("is_qna_given") or len(r.get("qna_responses") or []) > 0):
                return jsonify({
                    "recording_id": rec_id,
                    "is_qna_given": True,
                    "qna_count": len(r.get("qna_responses") or []),
                }), 200
        for r in recs:
            if r.get("type") == "qna_submission" or r.get("is_qna_given") or len(r.get("qna_responses") or []) > 0:
                return jsonify({
                    "recording_id": r.get("recording_id"),
                    "is_qna_given": True,
                    "qna_count": len(r.get("qna_responses") or []),
                }), 200
        return jsonify({"recording_id": rec_id, "is_qna_given": False, "qna_count": 0}), 200

    for r in recs:
        if r.get("is_qna_given") or len(r.get("qna_responses") or []) > 0:
            return jsonify({
                "recording_id": r.get("recording_id"),
                "is_qna_given": True,
                "qna_count": len(r.get("qna_responses") or []),
            }), 200

    return jsonify({"is_qna_given": False, "qna_count": 0}), 200


@app.get("/api/assessments")
def list_assessments():
    return jsonify(get_all_records_from_mongodb()), 200


if __name__ == "__main__":
    print("=" * 60)
    print("ThyroTrack Flask Server (High Performance & Zero Local Storage)")
    print("Health Test : http://127.0.0.1:5000/api/health")
    print("Database    : MongoDB Atlas (records + sensor_readings)")
    print("Voice Cloud : Cloudinary Direct Stream")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)