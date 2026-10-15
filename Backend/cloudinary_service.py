"""
ThyroTrack Cloudinary Voice Storage Service (Optimized)
Uploads patient vocal phonation recordings directly to Cloudinary and returns direct playable HTTPS URLs.
Zero files stored in codebase.
"""

import os
import io
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger("thyrotrack_cloudinary")

CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL", "")

_is_configured = False


def init_cloudinary():
    global _is_configured
    if _is_configured:
        return True

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


def upload_voice_to_cloudinary(wav_source, subject_id: str = "patient_001", filename: str = "vocal_audio.wav") -> dict:
    """
    Uploads a WAV audio recording to Cloudinary.
    wav_source can be a Path, file path string, or file-like binary stream (io.BytesIO).
    Does not save or keep any file in the codebase.
    """
    configured = init_cloudinary()
    stem = Path(filename).stem

    if configured:
        try:
            import cloudinary.uploader

            public_id = f"thyrotrack_voice/{subject_id}_{stem}"
            
            # Cloudinary uploader accepts file paths or file-like objects (e.g. io.BytesIO)
            response = cloudinary.uploader.upload(
                wav_source if isinstance(wav_source, (str, Path)) else wav_source,
                resource_type="video",  # Cloudinary classifies audio under 'video'
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

    # Fallback placeholder URL if upload fails or credentials missing
    fallback_url = f"https://res.cloudinary.com/dh7degaxv/video/upload/v1791803233/thyrotrack_voice/thyrotrack_voice/patient_001_sample_vocal.wav"
    return {
        "status": "fallback" if not configured else "error",
        "cloudinary_url": fallback_url,
        "filename": filename,
    }
