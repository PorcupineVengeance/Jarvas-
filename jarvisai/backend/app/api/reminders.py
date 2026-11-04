from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models import User
from app.services.notifications import cancel_reminder, create_reminder, due_reminders, list_reminders, mark_fired

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    remind_at: datetime
    recurring: str | None = Field(default=None, max_length=64)


@router.post("", status_code=201)
def create(body: ReminderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = create_reminder(db, user.open_id, body.title, body.remind_at, body.recurring)
    return {"id": item.id, "title": item.title, "remind_at": item.remind_at, "status": item.status, "recurring": item.recurring}


@router.get("")
def list_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [{"id": row.id, "title": row.title, "remind_at": row.remind_at, "status": row.status, "recurring": row.recurring} for row in list_reminders(db, user.open_id, include_fired=True)]


@router.get("/due")
def list_due(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = due_reminders(db, user.open_id)
    for item in items:
        mark_fired(db, item)
    return [{"id": row.id, "title": row.title, "remind_at": row.remind_at, "status": "fired"} for row in items]


@router.delete("/{reminder_id}")
def delete_reminder(reminder_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not cancel_reminder(db, user.open_id, reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return {"ok": True}
