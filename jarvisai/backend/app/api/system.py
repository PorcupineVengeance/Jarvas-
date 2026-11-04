from datetime import datetime, timezone
import os
import psutil
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.database.session import get_db, get_engine
from app.models import Task, User

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "jarvis-api", "time": datetime.now(timezone.utc)}


@router.get("/system/status")
def system_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    settings = get_settings()
    database_connected = False
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        database_connected = True
    except Exception:
        database_connected = False
    active_tasks = db.scalar(select(func.count()).select_from(Task).where(Task.owner_id == user.open_id, Task.status == "in_progress")) if database_connected else 0
    process = psutil.Process(os.getpid())
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        worker_count = min(64, max(1, int(os.getenv("WEB_CONCURRENCY", "1") or "1")))
    except ValueError:
        worker_count = 1
    connected_integrations = []
    if settings.llm_ready:
        connected_integrations.append(settings.llm_provider_name)
    if settings.transcription_ready:
        connected_integrations.append("Speech transcription")
    if settings.tts_ready:
        connected_integrations.append("Text to speech")
    if settings.jarvis_research_api_id and settings.manus_service_ready:
        connected_integrations.append("API Hub research")
    return {
        "status": "online" if database_connected else "degraded",
        "api_connection": True,
        "time": datetime.now(timezone.utc),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": memory.percent,
        "disk_percent": disk.percent,
        "active_tasks": active_tasks or 0,
        "active_processes": [{"name": process.name(), "memory_mb": round(process.memory_info().rss / (1024 * 1024), 1)}],
        "worker_count": worker_count,
        "connected_integrations": connected_integrations,
        "database": {"connected": database_connected},
        "providers": {"llm": settings.llm_ready, "llm_name": settings.llm_provider_name, "transcription": settings.transcription_ready, "text_to_speech": settings.tts_ready},
        "microphone": {"available": None, "detail": "Microphone permissions are checked by the browser."},
        "metrics_scope": "Application host only; these measurements do not describe the user's personal computer.",
    }
