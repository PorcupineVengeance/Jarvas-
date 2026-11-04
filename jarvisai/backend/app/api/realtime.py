import asyncio
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.api.chat import Mode, _get_conversation, _messages_for_turn, resolve_mode
from app.core.security import SESSION_COOKIE, decode_session, is_allowed_origin
from app.database.session import get_session_factory
from app.models import Message, Task, User
from app.services.llm import ProviderRequestFailed, ProviderUnavailable
from app.services.orchestrator import orchestrated_stream

router = APIRouter()
VOICE_STATES = {"idle", "recording", "transcribing", "completed", "error"}
VALID_MODES = {"auto", "normal", "research", "assistant", "developer", "automation", "focus"}


@router.websocket("/api/ws")
async def assistant_socket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and not is_allowed_origin(origin.rstrip("/")):
        await websocket.close(code=4403, reason="Untrusted origin")
        return
    try:
        claims = decode_session(websocket.cookies.get(SESSION_COOKIE, ""))
    except Exception:
        await websocket.close(code=4401, reason="Sign-in required")
        return
    db = get_session_factory()()
    user = db.get(User, str(claims["openId"]))
    if user is None:
        user = User(open_id=str(claims["openId"]), display_name=str(claims.get("name") or "JARVIS user"), email=claims.get("email"))
        db.add(user)
        db.commit()
    await websocket.accept()
    send_lock = asyncio.Lock()

    async def send(payload: dict):
        async with send_lock:
            await websocket.send_json(payload)

    async def run_chat(event: dict):
        text = event.get("message")
        requested_mode = event.get("mode", "auto")
        if not isinstance(text, str) or not text.strip() or len(text) > 12_000:
            await send({"type": "error", "message": "Message must contain 1–12,000 characters."})
            return
        if requested_mode not in VALID_MODES:
            await send({"type": "error", "message": "Assistant mode is not supported."})
            return
        mode = resolve_mode(text, requested_mode)
        await send({"type": "assistant.status", "status": "thinking", "mode": mode})
        try:
            conversation = _get_conversation(db, user, event.get("conversation_id"), text)
            client_id = str(event.get("client_message_id") or uuid4())[:64]
            saved = db.scalar(select(Message).where(Message.client_id == client_id, Message.user_id == user.open_id))
            if saved is None:
                db.add(Message(conversation_id=conversation.id, user_id=user.open_id, role="user", content=text, client_id=client_id))
                db.commit()
            prompt = _messages_for_turn(db, user, conversation, text, mode)
            answer: list[str] = []
            searched = False
            async for kind, chunk in orchestrated_stream(prompt, mode):
                if kind == "status":
                    searched = True
                    await send({"type": "automation.status", "status": "running", "detail": chunk})
                    continue
                answer.append(chunk)
                await send({"type": "assistant.delta", "text": chunk, "conversation_id": conversation.id})
            full_answer = "".join(answer).strip()
            if full_answer:
                db.add(Message(conversation_id=conversation.id, user_id=user.open_id, role="assistant", content=full_answer))
                conversation.updated_at = datetime.now(timezone.utc)
                db.commit()
            if searched:
                await send({"type": "automation.status", "status": "completed", "detail": "Research result was summarized using returned provider data."})
            await send({"type": "assistant.done", "conversation_id": conversation.id, "mode": mode, "saved": bool(full_answer)})
        except (ProviderRequestFailed, ProviderUnavailable) as exc:
            db.rollback()
            await send({"type": "error", "message": str(exc)})
        except asyncio.CancelledError:
            db.rollback()
            await send({"type": "assistant.status", "status": "cancelled", "detail": "The active response was interrupted; its provider stream was closed."})
            raise
        except Exception:
            db.rollback()
            await send({"type": "error", "message": "The response could not be completed. Your prompt remains available to retry."})

    await send({"type": "assistant.status", "status": "ready"})
    active_turn: asyncio.Task | None = None
    try:
        while True:
            if active_turn is None:
                event = await websocket.receive_json()
            else:
                receiver = asyncio.create_task(websocket.receive_json())
                done, _ = await asyncio.wait({receiver, active_turn}, return_when=asyncio.FIRST_COMPLETED)
                if active_turn in done:
                    try:
                        await active_turn
                    except asyncio.CancelledError:
                        pass
                    active_turn = None
                if receiver not in done:
                    receiver.cancel()
                    try:
                        await receiver
                    except asyncio.CancelledError:
                        pass
                    continue
                event = receiver.result()
            if not isinstance(event, dict):
                await send({"type": "error", "message": "Events must be JSON objects."})
            elif event.get("type") == "chat.message":
                if active_turn is not None:
                    await send({"type": "error", "message": "A response is already running. Cancel it before starting another."})
                else:
                    active_turn = asyncio.create_task(run_chat(event))
            elif event.get("type") == "task.cancel":
                if active_turn is not None:
                    active_turn.cancel()
                    try:
                        await active_turn
                    except asyncio.CancelledError:
                        pass
                    active_turn = None
                    await send({"type": "task.status", "status": "cancelled", "detail": "Active assistant response cancelled."})
                else:
                    await send({"type": "task.status", "status": "idle", "detail": "No active assistant response to cancel."})
            elif event.get("type") == "task.list":
                if active_turn is not None:
                    await send({"type": "error", "message": "Wait for or cancel the current response before requesting a task snapshot."})
                    continue
                tasks = db.scalars(select(Task).where(Task.owner_id == user.open_id).order_by(Task.created_at.desc()).limit(100)).all()
                await send({"type": "task.status", "status": "snapshot", "items": [{"id": row.id, "title": row.title, "status": row.status, "priority": row.priority, "due_at": row.due_at.isoformat() if row.due_at else None} for row in tasks]})
            elif event.get("type") == "voice.status":
                voice_status = event.get("status")
                if voice_status not in VOICE_STATES:
                    await send({"type": "error", "message": "Voice status is not supported."})
                else:
                    await send({"type": "voice.status", "status": voice_status, "reported_by": "client", "detail": "Voice capture and provider processing use the authenticated REST routes."})
            else:
                await send({"type": "error", "message": "Unsupported event type."})
    except WebSocketDisconnect:
        pass
    finally:
        if active_turn is not None and not active_turn.done():
            active_turn.cancel()
            try:
                await active_turn
            except (asyncio.CancelledError, WebSocketDisconnect):
                pass
        db.close()
