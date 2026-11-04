from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models import Task, User

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=8_000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    due_at: datetime | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    description: str | None = Field(default=None, max_length=8_000)
    status: Literal["open", "in_progress", "completed", "cancelled"] | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    due_at: datetime | None = None


class TaskView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=TaskView, status_code=201)
def create_task(body: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = Task(id=str(uuid4()), owner_id=user.open_id, title=body.title.strip(), description=body.description, priority=body.priority, due_at=body.due_at)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("", response_model=list[TaskView])
def list_tasks(status_filter: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = select(Task).where(Task.owner_id == user.open_id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    return db.scalars(query.order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.created_at.desc()).limit(200)).all()


@router.patch("/{task_id}", response_model=TaskView)
def update_task(task_id: str, body: TaskPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.open_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    task.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


class DeleteConfirmation(BaseModel):
    confirmed: bool = False


@router.delete("/{task_id}")
def delete_task(task_id: str, body: DeleteConfirmation, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not body.confirmed:
        raise HTTPException(status_code=409, detail="Confirm task deletion before retrying.")
    task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.open_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    db.delete(task)
    db.commit()
    return {"ok": True}
