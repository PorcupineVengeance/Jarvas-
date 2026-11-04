from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.models import User

router = APIRouter(prefix="/api", tags=["integrations"])


@router.get("/integrations")
def integrations(_user: User = Depends(get_current_user)):
    settings = get_settings()
    items = [
        {"id": "llm", "name": settings.llm_provider_name, "configured": settings.llm_ready, "status": "connected" if settings.llm_ready else "unavailable", "detail": "Server-side configurable chat-completion adapter" if settings.llm_ready else "Configure a provider endpoint, model and protected API key."},
        {"id": "manus_platform", "name": "Manus platform services", "configured": settings.manus_service_ready, "status": "connected" if settings.manus_service_ready else "unavailable", "detail": "Speech, object storage and API Hub service credentials" if settings.manus_service_ready else "Required for managed speech, project storage and API Hub research."},
        {"id": "speech_to_text", "name": "Speech transcription", "configured": settings.transcription_ready, "status": "connected" if settings.transcription_ready else "unavailable", "detail": "Whisper-compatible transcription endpoint" if settings.transcription_ready else "Configure the managed speech service before use."},
        {"id": "text_to_speech", "name": "Text to speech", "configured": settings.tts_ready, "status": "connected" if settings.tts_ready else "unconfigured", "detail": "Configured OpenAI-compatible TTS provider" if settings.tts_ready else "Requires a supported TTS endpoint, model and protected provider key."},
        {"id": "research", "name": "Web research", "configured": bool(settings.jarvis_research_api_id and settings.manus_service_ready), "status": "connected" if settings.jarvis_research_api_id and settings.manus_service_ready else "unconfigured", "detail": "Configured Manus API Hub research API" if settings.jarvis_research_api_id and settings.manus_service_ready else "Requires Manus platform service credentials and a registered API Hub search identifier."},
        {"id": "calendar", "name": "Calendar", "configured": False, "status": "unconfigured", "detail": "No calendar provider has been connected."},
        {"id": "email", "name": "Email", "configured": False, "status": "unconfigured", "detail": "No email provider has been connected."},
        {"id": "computer_control", "name": "Personal computer control", "configured": False, "status": "permission_required", "detail": "A separately authorized local companion is required; this hosted web application cannot control your desktop."},
        {"id": "wake_word", "name": "Wake word / continuous listening", "configured": False, "status": "unconfigured", "detail": "Wake-word recognition is not implemented in this hosted build; continuous listening remains off."},
        {"id": "persistent_scheduler", "name": "Persistent reminders", "configured": False, "status": "publication_required", "detail": "Persistent scheduled callbacks require a published endpoint and schedule registration."},
    ]
    return {"items": items, "checked_at": datetime.now(timezone.utc)}
