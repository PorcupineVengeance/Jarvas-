from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
import httpx
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.models import User

router = APIRouter(prefix="/api/voice", tags=["voice"])
ALLOWED_AUDIO = {"audio/webm", "audio/mpeg", "audio/wav", "audio/x-wav", "audio/ogg", "audio/mp4", "audio/x-m4a"}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language_hint: str = Form(default=""), _user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.transcription_ready or not settings.api_base:
        raise HTTPException(status_code=503, detail="Speech transcription is not configured in this runtime.")
    content_type = (file.content_type or "").split(";")[0].lower()
    if content_type not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Use a supported audio format: WebM, MP3, WAV, OGG or M4A.")
    maximum = settings.jarvis_max_upload_mb * 1024 * 1024
    audio = await file.read(maximum + 1)
    if len(audio) > maximum:
        raise HTTPException(status_code=413, detail=f"Recording is larger than the {settings.jarvis_max_upload_mb} MB limit.")
    prompt = "Transcribe the user's voice to text."
    if language_hint.strip():
        prompt += " Working language: " + language_hint.strip()[:80] + "."
    url = f"{settings.api_base}/v1/audio/transcriptions"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=8.0)) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {settings.manus_api_key}"}, data={"model": "whisper-1", "prompt": prompt}, files={"file": (file.filename or "recording.webm", audio, content_type)})
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Transcription timed out. You can retry the recording.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The transcription service could not be reached.") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail=f"Transcription service returned HTTP {response.status_code}.")
    data = response.json()
    if data.get("error"):
        raise HTTPException(status_code=502, detail="The transcription provider reported an error.")
    if not isinstance(data.get("text"), str):
        raise HTTPException(status_code=502, detail="The transcription provider returned no transcript.")
    return {"text": data["text"], "language": data.get("language"), "duration": data.get("duration"), "segments": data.get("segments", [])}


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5_000)
    voice: str | None = Field(default=None, max_length=80)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@router.post("/speak")
async def speak(body: SpeakRequest, _user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.tts_ready:
        raise HTTPException(status_code=503, detail="Text-to-speech is not configured. Add a supported provider endpoint, model and protected API key.")
    tts_url = (settings.jarvis_tts_api_url or "").rstrip("/")
    payload = {"model": settings.jarvis_tts_model, "voice": body.voice or settings.jarvis_tts_voice, "input": body.text, "speed": body.speed, "response_format": "mp3"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0)) as client:
            response = await client.post(tts_url + "/v1/audio/speech", headers={"Authorization": f"Bearer {settings.jarvis_tts_api_key}"}, json=payload)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Speech generation timed out.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="The speech provider could not be reached.") from exc
    if response.is_error:
        raise HTTPException(status_code=502, detail=f"Speech provider returned HTTP {response.status_code}.")
    return Response(content=response.content, media_type=response.headers.get("content-type", "audio/mpeg"), headers={"Cache-Control": "no-store"})
