"""
ThyroTrack Cloudinary Voice Storage Service
Uploads patient vocal phonation WAV recordings to Cloudinary and returns direct playable HTTPS URLs.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger("thyrotrack_cloudinary")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")

_is_configured = False


def init_cloudinary():
    global _is_configured
    try:
        import cloudinary
        if CLOUDINARY_URL:
            cloudinary.config_from_url(CLOUDINARY_URL)
            _is_configured = True
        elif CLOUDINARY_CLOUD_NAME and CLOUDINARY_CLOUD_NAME != "your_cloud_name" and CLOUDINARY_API_KEY != "your_api_key":
            cloudinary.config(
                cloud_name=CLOUDINARY_CLOUD_NAME,
                api_key=CLOUDINARY_API_KEY,
                api_secret=CLOUDINARY_API_SECRET,
                secure=True,
            )
            _is_configured = True
        else:
            _is_configured = False
    except Exception as e:
        logger.warning(f"Cloudinary configuration warning: {e}")
        _is_configured = False
    return _is_configured


# Initialize on load
init_cloudinary()


def upload_voice_to_cloudinary(wav_path: Path, subject_id: str = "patient_001") -> dict:
    """
    Uploads a WAV audio recording to Cloudinary.
    Audio files in Cloudinary are uploaded under resource_type='video' (or 'auto').
    """
    if not wav_path or not wav_path.is_file():
        return {
            "status": "error",
            "message": f"Audio file not found: {wav_path}",
            "cloudinary_url": None,
            "filename": wav_path.name if wav_path else None,
        }

    filename = wav_path.name
    configured = init_cloudinary()

    if configured:
        try:
            import cloudinary.uploader

            public_id = f"thyrotrack_voice/{subject_id}_{wav_path.stem}"
            response = cloudinary.uploader.upload(
                str(wav_path),
                resource_type="video",  # Cloudinary classifies audio as video resource
                public_id=public_id,
                folder="thyrotrack_voice",
                overwrite=True,
            )

            secure_url = response.get("secure_url") or response.get("url")
            logger.info(f"Audio successfully uploaded to Cloudinary: {secure_url}")
            return {
                "status": "uploaded",
                "cloudinary_url": secure_url,
                "public_id": response.get("public_id"),
                "format": response.get("format", "wav"),
                "duration": response.get("duration"),
                "filename": filename,
            }
        except Exception as exc:
            logger.error(f"Cloudinary upload error: {exc}")

    # Graceful fallback URL if API keys are pending in .env
    fallback_url = f"https://res.cloudinary.com/thyrotrack/video/upload/v1/thyrotrack_voice/{filename}"
    return {
        "status": "staged_pending_keys" if not configured else "error",
        "cloudinary_url": fallback_url,
        "filename": filename,
        "local_path": str(wav_path),
        "note": "Audio file ready. Add your CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET in Backend/.env to complete live cloud upload.",
    }
