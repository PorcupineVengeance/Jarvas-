from __future__ import annotations
from datetime import datetime
from typing import Any
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Memory, Reminder, Task, User
from app.tools.registry import Tool, ToolRegistry


def register_all(registry: ToolRegistry) -> None:
    registry.register(Tool(
        id="tasks.list",
        name="List tasks",
        description="Read the signed-in user's tasks.",
        permission="tasks:read",
        write=False,
        category="productivity",
        input_schema={"type": "object", "properties": {"status": {"type": "string", "enum": ["open", "in_progress", "completed", "cancelled"]}}, "additionalProperties": False},
        execute=_tasks_list,
    ))
    registry.register(Tool(
        id="tasks.create",
        name="Create a task",
        description="Create a task for the signed-in user.",
        permission="tasks:write",
        write=True,
        category="productivity",
        input_schema={"type": "object", "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 250}, "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]}}, "required": ["title"], "additionalProperties": False},
        execute=_tasks_create,
    ))
    registry.register(Tool(
        id="memory.search",
        name="Search saved memory",
        description="Search the signed-in user's saved memories.",
        permission="memory:read",
        write=False,
        category="memory",
        input_schema={"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 160}}, "required": ["query"], "additionalProperties": False},
        execute=_memory_search,
    ))
    registry.register(Tool(
        id="memory.save",
        name="Save memory",
        description="Persist a user preference or note when explicitly requested.",
        permission="memory:write",
        write=True,
        category="memory",
        input_schema={"type": "object", "properties": {"category": {"type": "string"}, "content": {"type": "string", "minLength": 1, "maxLength": 4000}}, "required": ["content"], "additionalProperties": False},
        execute=_memory_save,
    ))
    registry.register(Tool(
        id="research.search",
        name="Search the web",
        description="Search the configured research provider for current information. Never invent results.",
        permission="research:read",
        write=False,
        category="research",
        input_schema={"type": "object", "properties": {"query": {"type": "string", "minLength": 3, "maxLength": 800}}, "required": ["query"], "additionalProperties": False},
        execute=_research_search,
    ))
    registry.register(Tool(
        id="system.info",
        name="System information",
        description="Report host CPU, memory and disk usage for the JARVIS backend process.",
        permission="system:read",
        write=False,
        category="system",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        execute=_system_info,
    ))
    registry.register(Tool(
        id="files.list",
        name="List directory",
        description="List files in an authorized directory.",
        permission="files:read",
        write=False,
        category="files",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        execute=_files_list,
    ))
    registry.register(Tool(
        id="files.find",
        name="Find files",
        description="Find files by glob pattern under an authorized directory.",
        permission="files:read",
        write=False,
        category="files",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"directory": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["directory", "pattern"], "additionalProperties": False},
        execute=_files_find,
    ))
    registry.register(Tool(
        id="files.create_folder",
        name="Create folder",
        description="Create a folder inside authorized directories.",
        permission="files:write",
        write=True,
        category="files",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        execute=_files_create_folder,
    ))
    registry.register(Tool(
        id="files.write_text",
        name="Write text file",
        description="Create a new text/markdown report in an authorized path.",
        permission="files:write",
        write=True,
        category="files",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False},
        execute=_files_write_text,
    ))
    registry.register(Tool(
        id="files.delete",
        name="Delete file or folder",
        description="Delete a path inside authorized directories. Requires confirmation.",
        permission="files:delete",
        write=True,
        category="files",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        execute=_files_delete,
    ))
    registry.register(Tool(
        id="computer.open_app",
        name="Open application",
        description="Open a desktop application by name on the local machine.",
        permission="computer:control",
        write=True,
        category="computer",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False},
        execute=_open_app,
    ))
    registry.register(Tool(
        id="computer.open_url",
        name="Open URL",
        description="Open a website in the default browser.",
        permission="computer:control",
        write=True,
        category="computer",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"], "additionalProperties": False},
        execute=_open_url,
    ))
    registry.register(Tool(
        id="computer.open_path",
        name="Open path",
        description="Open an authorized file or folder in the OS file manager.",
        permission="computer:control",
        write=True,
        category="computer",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False},
        execute=_open_path,
    ))
    registry.register(Tool(
        id="computer.screenshot",
        name="Take screenshot",
        description="Capture a screenshot of the local desktop.",
        permission="computer:control",
        write=True,
        category="computer",
        requires_computer=True,
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        execute=_screenshot,
    ))
    registry.register(Tool(
        id="browser.search",
        name="Browser search",
        description="Open a browser search results page (YouTube by default).",
        permission="browser:control",
        write=True,
        category="browser",
        requires_computer=True,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}, "site": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
        execute=_browser_search,
    ))
    registry.register(Tool(
        id="reminders.create",
        name="Create reminder",
        description="Schedule a persistent one-time reminder.",
        permission="reminders:write",
        write=True,
        category="productivity",
        input_schema={"type": "object", "properties": {"title": {"type": "string"}, "remind_at": {"type": "string", "description": "ISO-8601 datetime"}}, "required": ["title", "remind_at"], "additionalProperties": False},
        execute=_reminder_create,
    ))
    registry.register(Tool(
        id="reminders.list",
        name="List reminders",
        description="List scheduled reminders for the user.",
        permission="reminders:read",
        write=False,
        category="productivity",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        execute=_reminder_list,
    ))


def _tasks_list(args: dict[str, Any], db: Session, user: User):
    query = select(Task).where(Task.owner_id == user.open_id)
    if args.get("status"):
        query = query.where(Task.status == args["status"])
    return [{"id": row.id, "title": row.title, "status": row.status, "priority": row.priority, "due_at": row.due_at} for row in db.scalars(query.order_by(Task.created_at.desc()).limit(100)).all()]


def _tasks_create(args: dict[str, Any], db: Session, user: User):
    title = str(args.get("title") or "").strip()
    priority = args.get("priority", "normal")
    task = Task(id=str(uuid4()), owner_id=user.open_id, title=title, priority=priority)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id, "title": task.title, "status": task.status}


def _memory_search(args: dict[str, Any], db: Session, user: User):
    query_text = str(args.get("query") or "")
    records = db.scalars(select(Memory).where(Memory.owner_id == user.open_id, Memory.content.ilike(f"%{query_text}%")).limit(20)).all()
    return [{"id": row.id, "category": row.category, "content": row.content} for row in records]


def _memory_save(args: dict[str, Any], db: Session, user: User):
    from app.api.memory import _reject_sensitive
    content = str(args.get("content") or "").strip()
    _reject_sensitive(content)
    category = str(args.get("category") or "note")[:64]
    item = Memory(id=str(uuid4()), owner_id=user.open_id, category=category, content=content)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "category": item.category, "content": item.content}


async def _research_search(args: dict[str, Any], db: Session, user: User):
    from app.services.web_research import search_web
    return await search_web(str(args["query"]))


def _system_info(args: dict[str, Any], db: Session, user: User):
    import os
    import psutil
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": memory.percent,
        "disk_percent": disk.percent,
        "pid": os.getpid(),
        "scope": "JARVIS backend host only",
    }


def _files_list(args: dict[str, Any], db: Session, user: User):
    from app.services.file_manager import list_directory
    return list_directory(str(args["path"]))


def _files_find(args: dict[str, Any], db: Session, user: User):
    from app.services.file_manager import find_files
    return find_files(str(args["directory"]), str(args["pattern"]))


def _files_create_folder(args: dict[str, Any], db: Session, user: User):
    from app.services.file_manager import create_folder
    return create_folder(str(args["path"]))


def _files_write_text(args: dict[str, Any], db: Session, user: User):
    from app.services.file_manager import create_text_file
    return create_text_file(str(args["path"]), str(args["content"]))


def _files_delete(args: dict[str, Any], db: Session, user: User):
    from app.services.file_manager import delete_path
    return delete_path(str(args["path"]))


def _open_app(args: dict[str, Any], db: Session, user: User):
    from app.services.computer_control import open_application
    return open_application(str(args["name"]))


def _open_url(args: dict[str, Any], db: Session, user: User):
    from app.services.computer_control import open_url
    return open_url(str(args["url"]))


def _open_path(args: dict[str, Any], db: Session, user: User):
    from app.services.computer_control import open_path
    return open_path(str(args["path"]))


def _screenshot(args: dict[str, Any], db: Session, user: User):
    from app.services.computer_control import take_screenshot
    return take_screenshot()


async def _browser_search(args: dict[str, Any], db: Session, user: User):
    from app.services.browser_automation import open_and_search
    site = args.get("site") or "https://www.youtube.com/results?search_query="
    return await open_and_search(str(args["query"]), str(site))


def _reminder_create(args: dict[str, Any], db: Session, user: User):
    from app.services.notifications import create_reminder
    remind_at = datetime.fromisoformat(str(args["remind_at"]).replace("Z", "+00:00"))
    item = create_reminder(db, user.open_id, str(args["title"]), remind_at)
    return {"id": item.id, "title": item.title, "remind_at": item.remind_at.isoformat(), "status": item.status}


def _reminder_list(args: dict[str, Any], db: Session, user: User):
    from app.services.notifications import list_reminders
    return [{"id": row.id, "title": row.title, "remind_at": row.remind_at.isoformat(), "status": row.status} for row in list_reminders(db, user.open_id)]
