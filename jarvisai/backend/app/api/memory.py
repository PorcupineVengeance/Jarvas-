import re
from uuid import uuid4
from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models import Memory, User

router = APIRouter(prefix="/api/memory", tags=["memory"])
SENSITIVE_PATTERNS = [re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,})"), re.compile(r"(?i)(password|api[_ -]?key|secret)\s*[:=]\s*\S+")]


class MemoryCreate(BaseModel):
    category: Literal["preference", "instruction", "project", "contact", "task", "note", "other"] = "note"
    content: str = Field(min_length=1, max_length=4_000)


class MemoryPatch(BaseModel):
    category: Literal["preference", "instruction", "project", "contact", "task", "note", "other"] | None = None
    content: str | None = Field(default=None, min_length=1, max_length=4_000)


class MemoryView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    category: str
    content: str
    created_at: datetime
    updated_at: datetime


def _reject_sensitive(content: str) -> None:
    if any(pattern.search(content) for pattern in SENSITIVE_PATTERNS):
        raise HTTPException(status_code=422, detail="This text appears to contain a credential. Sensitive authentication data cannot be stored in memory.")


@router.post("", response_model=MemoryView, status_code=201)
def create_memory(body: MemoryCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _reject_sensitive(body.content)
    item = Memory(id=str(uuid4()), owner_id=user.open_id, category=body.category, content=body.content.strip())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("", response_model=list[MemoryView])
def list_memory(query: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    statement = select(Memory).where(Memory.owner_id == user.open_id)
    if query:
        if len(query) > 160:
            raise HTTPException(status_code=422, detail="Search text is too long.")
        statement = statement.where(Memory.content.ilike(f"%{query}%"))
    return db.scalars(statement.order_by(Memory.updated_at.desc()).limit(200)).all()


@router.patch("/{memory_id}", response_model=MemoryView)
def update_memory(memory_id: str, body: MemoryPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.owner_id == user.open_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    changes = body.model_dump(exclude_unset=True)
    if "content" in changes and changes["content"] is not None:
        _reject_sensitive(changes["content"])
    for key, value in changes.items():
        setattr(item, key, value)
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.owner_id == user.open_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    db.delete(item)
    db.commit()
    return {"ok": True}
