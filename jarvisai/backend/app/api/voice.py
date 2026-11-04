from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.models import User
from app.services.llm import ProviderRequestFailed, ProviderUnavailable
from app.services.speech_to_text import transcribe_audio
from app.services.text_to_speech import synthesize_speech

router = APIRouter(prefix="/api/voice", tags=["voice"])
ALLOWED_AUDIO = {"audio/webm", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mp4", "audio/x-m4a", "audio/flac"}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language_hint: str = Form(default=""), _user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.transcription_ready:
        raise HTTPException(status_code=503, detail="Speech transcription is not configured. Set JARVIS_STT_API_URL, JARVIS_STT_API_KEY and JARVIS_STT_MODEL.")
    content_type = (file.content_type or "").split(";")[0].lower()
    if content_type not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Use a supported audio format: WebM, MP3, WAV, OGG, FLAC or M4A.")
    maximum = settings.jarvis_max_upload_mb * 1024 * 1024
    audio = await file.read(maximum + 1)
    if len(audio) > maximum:
        raise HTTPException(status_code=413, detail=f"Recording is larger than the {settings.jarvis_max_upload_mb} MB limit.")
    try:
        return await transcribe_audio(file.filename or "recording.webm", audio, content_type, language_hint)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    voice: str | None = Field(default=None, max_length=80)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@router.post("/speak")
async def speak(body: SpeakRequest, _user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.tts_ready:
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured. Add JARVIS_TTS_PROVIDER, endpoint, model and protected API key.")
    try:
        audio, content_type = await synthesize_speech(body.text, body.voice, body.speed)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=audio, media_type=content_type, headers={"Cache-Control": "no-store"})


@router.get("/settings")
def voice_settings(_user: User = Depends(get_current_user)):
    settings = get_settings()
    return {
        "transcription_ready": settings.transcription_ready,
        "tts_ready": settings.tts_ready,
        "tts_provider": settings.jarvis_tts_provider if settings.tts_ready else None,
        "wake_word_enabled": settings.jarvis_wake_word_enabled,
        "continuous_listening": settings.jarvis_continuous_listening,
        "wake_word": "Hey JARVIS",
        "privacy_note": "Continuous listening and wake-word detection stay off unless explicitly enabled. Browser microphone permission is still required.",
    }
