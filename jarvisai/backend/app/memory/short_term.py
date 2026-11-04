"""In-process short-term conversational context (per session id)."""

from collections import defaultdict, deque
from threading import Lock

_lock = Lock()
_buffers: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=24))


def push(session_id: str, role: str, content: str) -> None:
    with _lock:
        _buffers[session_id].append({"role": role, "content": content})


def history(session_id: str) -> list[dict]:
    with _lock:
        return list(_buffers[session_id])


def clear(session_id: str) -> None:
    with _lock:
        _buffers.pop(session_id, None)
