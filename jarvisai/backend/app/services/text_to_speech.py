import httpx
from app.core.config import get_settings
from app.services.http_client import get_http_client
from app.services.llm import ProviderRequestFailed, ProviderUnavailable


async def synthesize_speech(text: str, voice: str | None = None, speed: float = 1.0) -> tuple[bytes, str]:
    settings = get_settings()
    if not settings.tts_ready:
        raise ProviderUnavailable("Text-to-speech is not configured.")
    # Keep full spoken replies; still bound length for provider safety.
    clipped = " ".join(text.split())[:700]
    provider = (settings.jarvis_tts_provider or "fish").lower()
    if provider == "fish":
        return await _fish_tts(clipped, voice, speed)
    return await _openai_compatible_tts(clipped, voice, speed)


async def _fish_tts(text: str, voice: str | None, speed: float) -> tuple[bytes, str]:
    settings = get_settings()
    base = (settings.jarvis_tts_api_url or "").rstrip("/")
    url = f"{base}/v1/tts"
    payload: dict = {
        "text": text,
        "format": "mp3",
        "prosody": {"speed": max(0.5, min(2.0, speed)), "volume": 0, "normalize_loudness": False},
    }
    chosen_voice = voice or settings.jarvis_tts_voice
    if chosen_voice:
        payload["reference_id"] = chosen_voice
    headers = {
        "Authorization": f"Bearer {settings.jarvis_tts_api_key}",
        "Content-Type": "application/json",
        "model": settings.jarvis_tts_model or "s2.1-pro-free",
    }
    try:
        client = get_http_client()
        response = await client.post(url, headers=headers, json=payload, timeout=httpx.Timeout(35.0, connect=4.0))
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed("Speech generation timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed("The speech provider could not be reached.") from exc
    if response.is_error:
        detail = ""
        try:
            detail = response.json().get("message") or ""
        except Exception:
            detail = response.text[:200]
        raise ProviderRequestFailed(f"Speech provider returned HTTP {response.status_code}{': ' + detail if detail else ''}.")
    content_type = response.headers.get("content-type", "audio/mpeg")
    if "application/json" in content_type:
        raise ProviderRequestFailed("Speech provider returned JSON instead of audio.")
    return response.content, content_type.split(";")[0]


async def _openai_compatible_tts(text: str, voice: str | None, speed: float) -> tuple[bytes, str]:
    settings = get_settings()
    tts_url = (settings.jarvis_tts_api_url or "").rstrip("/")
    endpoint = tts_url if tts_url.endswith("/audio/speech") else f"{tts_url}/v1/audio/speech"
    payload = {
        "model": settings.jarvis_tts_model,
        "voice": voice or settings.jarvis_tts_voice or "alloy",
        "input": text,
        "speed": speed,
        "response_format": "mp3",
    }
    try:
        client = get_http_client()
        response = await client.post(
            endpoint,
            headers={"Authorization": f"Bearer {settings.jarvis_tts_api_key}"},
            json=payload,
            timeout=httpx.Timeout(35.0, connect=4.0),
        )
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed("Speech generation timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed("The speech provider could not be reached.") from exc
    if response.is_error:
        raise ProviderRequestFailed(f"Speech provider returned HTTP {response.status_code}.")
    return response.content, response.headers.get("content-type", "audio/mpeg")
