from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models import Memory, Task, ToolExecution, User
from app.services.llm import ProviderRequestFailed, ProviderUnavailable
from app.api.research import search_provider

router = APIRouter(tags=["tools and automation"])
TOOL_DEFINITIONS = [
    {"id": "tasks.list", "name": "List tasks", "description": "Read the signed-in user's tasks.", "permission": "tasks:read", "write": False, "input_schema": {"type": "object", "properties": {"status": {"type": "string", "enum": ["open", "in_progress", "completed", "cancelled"]}}, "additionalProperties": False}},
    {"id": "tasks.create", "name": "Create a task", "description": "Create a task for the signed-in user.", "permission": "tasks:write", "write": True, "input_schema": {"type": "object", "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 250}, "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]}}, "required": ["title"], "additionalProperties": False}},
    {"id": "memory.search", "name": "Search saved memory", "description": "Search the signed-in user's saved memories.", "permission": "memory:read", "write": False, "input_schema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 160}}, "required": ["query"], "additionalProperties": False}},
    {"id": "research.search", "name": "Search configured research provider", "description": "Read from the configured API Hub search provider. Source details are returned as provided; no other websites are implied.", "permission": "research:read", "write": False, "input_schema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 3, "maxLength": 800}}, "required": ["query"], "additionalProperties": False}},
]
ALLOWED_ARGUMENTS = {"tasks.list": {"status"}, "tasks.create": {"title", "priority"}, "memory.search": {"query"}, "research.search": {"query"}}


class ExecuteRequest(BaseModel):
    tool_id: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)
    confirmed: bool = False


@router.get("/api/tools")
def list_tools(_user: User = Depends(get_current_user)):
    return {"tools": TOOL_DEFINITIONS, "notice": "Only listed, permission-checked tools can execute. No shell or personal-desktop control is exposed by this hosted application."}


@router.post("/api/automation/execute")
async def execute_tool(body: ExecuteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    definition = next((item for item in TOOL_DEFINITIONS if item["id"] == body.tool_id), None)
    if definition is None:
        raise HTTPException(status_code=404, detail="Tool is not registered.")
    if definition["write"] and not body.confirmed:
        raise HTTPException(status_code=409, detail="Confirm this change before it is executed.")
        if not isinstance(body.arguments, dict) or set(body.arguments) - ALLOWED_ARGUMENTS[body.tool_id]:
            raise HTTPException(status_code=422, detail="Tool arguments include unsupported fields.")
        if body.tool_id == "tasks.list" and body.arguments.get("status") not in {None, "open", "in_progress", "completed", "cancelled"}:
            raise HTTPException(status_code=422, detail="Task status is invalid.")
    execution = ToolExecution(id=str(uuid4()), user_id=user.open_id, tool_id=body.tool_id, status="running", started_at=datetime.now(timezone.utc))
    db.add(execution)
    db.commit()
    try:
        args = body.arguments
        if body.tool_id == "tasks.list":
            query = select(Task).where(Task.owner_id == user.open_id)
            if args.get("status"):
                query = query.where(Task.status == args["status"])
            result = [{"id": row.id, "title": row.title, "status": row.status, "priority": row.priority, "due_at": row.due_at} for row in db.scalars(query.order_by(Task.created_at.desc()).limit(100)).all()]
        elif body.tool_id == "tasks.create":
            title = args.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > 250:
                raise HTTPException(status_code=422, detail="A task title of 1–250 characters is required.")
            priority = args.get("priority", "normal")
            if priority not in {"low", "normal", "high", "urgent"}:
                raise HTTPException(status_code=422, detail="Task priority is invalid.")
            task = Task(id=str(uuid4()), owner_id=user.open_id, title=title.strip(), priority=priority)
            db.add(task); db.commit(); db.refresh(task)
            result = {"id": task.id, "title": task.title, "status": task.status}
        elif body.tool_id == "memory.search":
            query_text = args.get("query")
            if not isinstance(query_text, str) or not 1 <= len(query_text) <= 160:
                raise HTTPException(status_code=422, detail="A search query of 1–160 characters is required.")
            records = db.scalars(select(Memory).where(Memory.owner_id == user.open_id, Memory.content.ilike(f"%{query_text}%")).limit(20)).all()
            result = [{"id": row.id, "category": row.category, "content": row.content} for row in records]
        else:
            query_text = args.get("query")
            if not isinstance(query_text, str) or not 3 <= len(query_text) <= 800:
                raise HTTPException(status_code=422, detail="A research query of 3–800 characters is required.")
            try:
                result = await search_provider(query_text)
            except ProviderUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ProviderRequestFailed as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        execution.status = "completed"
        execution.finished_at = datetime.now(timezone.utc)
        execution.result_summary = f"Returned {len(result) if isinstance(result, list) else 1} result(s)."
        db.commit()
        return {"execution_id": execution.id, "status": "completed", "tool_id": body.tool_id, "result": result}
    except HTTPException as exc:
        db.rollback()
        audit = db.get(ToolExecution, execution.id)
        if audit:
            audit.status = "failed"; audit.error_code = f"http_{exc.status_code}"; audit.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        audit = db.get(ToolExecution, execution.id)
        if audit:
            audit.status = "failed"; audit.error_code = type(exc).__name__; audit.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise HTTPException(status_code=503, detail="Tool execution failed; no successful result was verified.") from exc
