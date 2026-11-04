from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Reminder


def create_reminder(db: Session, owner_id: str, title: str, remind_at: datetime, recurring: str | None = None) -> Reminder:
    item = Reminder(
        id=str(uuid4()),
        owner_id=owner_id,
        title=title.strip()[:250],
        remind_at=remind_at,
        recurring=recurring,
        status="scheduled",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_reminders(db: Session, owner_id: str, include_fired: bool = False) -> list[Reminder]:
    query = select(Reminder).where(Reminder.owner_id == owner_id)
    if not include_fired:
        query = query.where(Reminder.status == "scheduled")
    return list(db.scalars(query.order_by(Reminder.remind_at.asc()).limit(200)).all())


def due_reminders(db: Session, owner_id: str | None = None) -> list[Reminder]:
    now = datetime.now(timezone.utc)
    query = select(Reminder).where(Reminder.status == "scheduled", Reminder.remind_at <= now)
    if owner_id:
        query = query.where(Reminder.owner_id == owner_id)
    return list(db.scalars(query.order_by(Reminder.remind_at.asc()).limit(100)).all())


def mark_fired(db: Session, reminder: Reminder) -> Reminder:
    reminder.status = "fired"
    reminder.fired_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(reminder)
    return reminder


def cancel_reminder(db: Session, owner_id: str, reminder_id: str) -> bool:
    item = db.scalar(select(Reminder).where(Reminder.id == reminder_id, Reminder.owner_id == owner_id))
    if item is None:
        return False
    item.status = "cancelled"
    db.commit()
    return True
