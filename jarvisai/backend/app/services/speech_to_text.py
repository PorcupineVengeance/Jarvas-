import httpx
from app.core.config import get_settings
from app.services.llm import ProviderRequestFailed, ProviderUnavailable


async def transcribe_audio(filename: str, audio: bytes, content_type: str, language_hint: str = "") -> dict:
    settings = get_settings()
    if not settings.transcription_ready or not settings.transcription_api_base or not settings.transcription_api_key:
        raise ProviderUnavailable("Speech transcription is not configured.")
    base = settings.transcription_api_base
    url = f"{base}/audio/transcriptions" if base.endswith("/v1") else f"{base}/v1/audio/transcriptions"
    data = {"model": settings.jarvis_stt_model or "whisper-1"}
    if language_hint.strip():
        data["language"] = language_hint.strip()[:16]
        data["prompt"] = f"Transcribe clearly. Working language hint: {language_hint.strip()[:80]}."
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=8.0)) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.transcription_api_key}"},
                data=data,
                files={"file": (filename or "recording.webm", audio, content_type)},
            )
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed("Transcription timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed("The transcription service could not be reached.") from exc
    if response.is_error:
        raise ProviderRequestFailed(f"Transcription service returned HTTP {response.status_code}.")
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        raise ProviderRequestFailed("The transcription provider returned no transcript.")
    if payload.get("error"):
        raise ProviderRequestFailed("The transcription provider reported an error.")
    return {
        "text": payload["text"],
        "language": payload.get("language"),
        "duration": payload.get("duration"),
        "segments": payload.get("segments", []),
    }
