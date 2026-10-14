from fastapi.responses import FileResponse
from app.voice.tts import SileroTTSWrapper
import tempfile

tts = SileroTTSWrapper(language="ru", speaker="xenia", sample_rate=8000)

@app.post("/synthesize")
async def synthesize_speech(data: dict):
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text'")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tts.synthesize(text, tmp.name)
        return FileResponse(tmp.name, media_type="audio/wav")