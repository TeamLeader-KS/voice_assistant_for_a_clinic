# from fastapi import APIRouter, HTTPException
# from fastapi.responses import FileResponse
# import tempfile
# import logging
#
# logger = logging.getLogger(__name__)
#
# router = APIRouter()
#
# _tts = None
#
#
# def get_tts():
#     global _tts
#     if _tts is None:
#         from app.voice.tts import SileroTTSWrapper
#         logger.info("Инициализация Silero TTS...")
#         _tts = SileroTTSWrapper(language="ru", speaker="xenia", sample_rate=8000)
#     return _tts
#
#
# @router.post("/synthesize")
# async def synthesize_speech(data: dict):
#     text = data.get("text", "")
#     if not text:
#         raise HTTPException(status_code=400, detail="Missing 'text'")
#
#     tts = get_tts()
#     with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
#         tts.synthesize(text, tmp.name)
#         return FileResponse(
#             tmp.name,
#             media_type="audio/wav",
#             filename="speech.wav",
#         )

"""HTTP-эндпоинт синтеза речи для AGI-моста Asterisk."""

from __future__ import annotations

import logging
import tempfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])

_tts = None


def _get_tts():
    global _tts
    if _tts is None:
        from app.voice.tts import SileroTTSWrapper

        _tts = SileroTTSWrapper()
    return _tts


@router.post("/synthesize")
async def synthesize_speech(data: dict):
    """Принимает {"text": "..."}, возвращает audio/wav 8 кГц mono PCM16."""
    text = (data or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text'")

    tts = _get_tts()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tts.synthesize(text, tmp.name)
        return FileResponse(
            tmp.name,
            media_type="audio/wav",
            filename="speech.wav",
        )