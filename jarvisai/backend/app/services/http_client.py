"""Shared HTTP client — keep-alive reuse cuts LLM/TTS connect latency."""

from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(45.0, connect=4.0),
            limits=httpx.Limits(max_keepalive_connections=24, max_connections=48, keepalive_expiry=30.0),
            http2=False,
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
