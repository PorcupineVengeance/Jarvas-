from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user
from app.database.session import get_db
from app.models import User
from app.tools.registry import get_registry, run_tool

router = APIRouter(tags=["tools and automation"])


class ExecuteRequest(BaseModel):
    tool_id: str = Field(min_length=1, max_length=80)
    arguments: dict = Field(default_factory=dict)
    confirmed: bool = False


@router.get("/api/tools")
def list_tools(_user: User = Depends(get_current_user)):
    tools = get_registry().definitions()
    return {
        "tools": tools,
        "notice": "Only listed, permission-checked tools can execute. Destructive tools require confirmed=true. Computer tools need JARVIS_ENABLE_COMPUTER_CONTROL=true.",
    }


@router.post("/api/automation/execute")
async def execute_tool(body: ExecuteRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registry = get_registry()
    tool = registry.get(body.tool_id)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool is not registered.")
    if not isinstance(body.arguments, dict):
        raise HTTPException(status_code=422, detail="Tool arguments must be an object.")
    try:
        return await run_tool(body.tool_id, body.arguments, db, user, confirmed=body.confirmed)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="Tool is not registered.")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Tool execution failed: {exc}") from exc
