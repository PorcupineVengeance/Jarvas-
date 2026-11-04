from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.models import User
from app.services import calendar as calendar_service
from app.services import email as email_service

router = APIRouter(prefix="/api", tags=["integrations"])


@router.get("/integrations")
def integrations(_user: User = Depends(get_current_user)):
    settings = get_settings()
    items = [
        {"id": "llm", "name": settings.llm_provider_name, "configured": settings.llm_ready, "status": "connected" if settings.llm_ready else "unavailable", "detail": "Server-side configurable chat-completion adapter" if settings.llm_ready else "Configure JARVIS_LLM_API_URL, JARVIS_LLM_API_KEY and JARVIS_LLM_MODEL."},
        {"id": "speech_to_text", "name": "Speech transcription", "configured": settings.transcription_ready, "status": "connected" if settings.transcription_ready else "unavailable", "detail": "Whisper-compatible transcription endpoint" if settings.transcription_ready else "Configure JARVIS_STT_* settings."},
        {"id": "text_to_speech", "name": "Text to speech", "configured": settings.tts_ready, "status": "connected" if settings.tts_ready else "unconfigured", "detail": f"Configured {settings.jarvis_tts_provider} TTS provider" if settings.tts_ready else "Requires JARVIS_TTS_PROVIDER, endpoint, model and API key."},
        {"id": "research", "name": "Web research", "configured": settings.research_ready, "status": "connected" if settings.research_ready else "unconfigured", "detail": f"Provider: {settings.jarvis_research_provider}" if settings.research_ready else "Set JARVIS_RESEARCH_PROVIDER=duckduckgo or configure Tavily/Manus."},
        {"id": "calendar", "name": "Calendar", "configured": calendar_service.is_ready(), "status": "connected" if calendar_service.is_ready() else "unconfigured", "detail": calendar_service.provider_status()["detail"]},
        {"id": "email", "name": "Email", "configured": email_service.is_ready(), "status": "connected" if email_service.is_ready() else "unconfigured", "detail": email_service.provider_status()["detail"]},
        {"id": "computer_control", "name": "Personal computer control", "configured": settings.jarvis_enable_computer_control, "status": "connected" if settings.jarvis_enable_computer_control else "permission_required", "detail": "Local automation enabled for authorized paths/apps." if settings.jarvis_enable_computer_control else "Set JARVIS_ENABLE_COMPUTER_CONTROL=true on a trusted local machine."},
        {"id": "wake_word", "name": "Wake word / continuous listening", "configured": settings.jarvis_wake_word_enabled, "status": "connected" if settings.jarvis_wake_word_enabled else "unconfigured", "detail": "Wake word 'Hey JARVIS' enabled." if settings.jarvis_wake_word_enabled else "Disabled for privacy. Set JARVIS_WAKE_WORD_ENABLED=true when a wake-word service is available."},
        {"id": "persistent_scheduler", "name": "Persistent reminders", "configured": True, "status": "connected", "detail": "Reminders are stored in the database and polled via /api/reminders/due."},
        {"id": "local_storage", "name": "Local file storage", "configured": True, "status": "connected", "detail": f"Uploads and reports store under {settings.jarvis_storage_dir} when Manus object storage is unavailable."},
    ]
    return {"items": items, "checked_at": datetime.now(timezone.utc)}
