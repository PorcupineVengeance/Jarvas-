from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import ToolExecution, User

Executor = Callable[[dict[str, Any], Session, User], Awaitable[Any] | Any]


@dataclass
class Tool:
    id: str
    name: str
    description: str
    permission: str
    write: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = field(default_factory=dict)
    execute: Executor | None = None
    category: str = "general"
    requires_computer: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.id] = tool

    def get(self, tool_id: str) -> Tool | None:
        return self._tools.get(tool_id)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": tool.id,
                "name": tool.name,
                "description": tool.description,
                "permission": tool.permission,
                "write": tool.write,
                "category": tool.category,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
                "requires_computer": tool.requires_computer,
            }
            for tool in self._tools.values()
        ]

    def openai_tools(self, categories: set[str] | None = None) -> list[dict[str, Any]]:
        tools = []
        for tool in self._tools.values():
            if categories and tool.category not in categories:
                continue
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.id.replace(".", "_"),
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            })
        return tools


_REGISTRY: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        from app.tools import bootstrap
        _REGISTRY = ToolRegistry()
        bootstrap.register_all(_REGISTRY)
    return _REGISTRY


async def run_tool(tool_id: str, arguments: dict[str, Any], db: Session, user: User, confirmed: bool = False) -> dict[str, Any]:
    registry = get_registry()
    tool = registry.get(tool_id)
    if tool is None:
        raise KeyError(tool_id)
    if tool.write and not confirmed:
        raise PermissionError("Confirm this change before it is executed.")
    if tool.requires_computer:
        from app.core.permissions import computer_control_enabled
        if not computer_control_enabled():
            raise PermissionError("Computer control is disabled in configuration.")
    execution = ToolExecution(id=str(uuid4()), user_id=user.open_id, tool_id=tool_id, status="running", started_at=datetime.now(timezone.utc))
    db.add(execution)
    db.commit()
    try:
        if tool.execute is None:
            raise RuntimeError("Tool has no executor.")
        result = tool.execute(arguments, db, user)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[misc]
        execution.status = "completed"
        execution.finished_at = datetime.now(timezone.utc)
        execution.result_summary = f"Returned {len(result) if isinstance(result, list) else 1} result(s)."[:240]
        db.commit()
        return {"execution_id": execution.id, "status": "completed", "tool_id": tool_id, "result": result}
    except Exception as exc:
        db.rollback()
        audit = db.get(ToolExecution, execution.id)
        if audit:
            audit.status = "failed"
            audit.error_code = type(exc).__name__[:80]
            audit.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
