from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import tempfile
import logging

logger = logging.getLogger(__name__)

router = APIRouter()  # ← роутер, а не app

_tts = None

def get_tts():
    global _tts
    if _tts is None:
        from src.app.voice.tts import SileroTTSWrapper
        logger.info("Инициализация Silero TTS...")
        _tts = SileroTTSWrapper(language="ru", speaker="xenia", sample_rate=8000)
    return _tts


@router.post("/synthesize")
async def synthesize_speech(data: dict):
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text'")

    tts = get_tts()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tts.synthesize(text, tmp.name)
        return FileResponse(tmp.name, media_type="audio/wav")