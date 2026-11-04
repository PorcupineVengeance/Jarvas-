import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any
import httpx
from app.core.config import get_settings
from app.services.http_client import get_http_client


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRequestFailed(RuntimeError):
    pass


def _request_payload(
    messages: list[dict[str, Any]],
    stream: bool,
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    payload: dict[str, Any] = {"messages": messages, "stream": stream}
    if settings.llm_model:
        payload["model"] = settings.llm_model
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def _endpoint() -> tuple[str, str]:
    settings = get_settings()
    if not settings.llm_ready or not settings.llm_completion_url or not settings.llm_api_key:
        raise ProviderUnavailable("No complete LLM provider configuration is available.")
    return settings.llm_completion_url, settings.llm_api_key


async def _post_json(url: str, api_key: str, payload: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        client = get_http_client()
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=httpx.Timeout(45.0, connect=4.0),
        )
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed(f"The AI {label} timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed(f"The AI {label} could not reach its provider.") from exc
    if response.is_error:
        raise ProviderRequestFailed(f"The selected AI provider returned HTTP {response.status_code}.")
    try:
        data = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ProviderRequestFailed(f"The AI {label} returned invalid JSON.") from exc
    if not isinstance(data, dict) or data.get("error"):
        raise ProviderRequestFailed(f"The AI {label} returned an invalid or error response.")
    return data


async def complete(messages: list[dict[str, Any]]) -> str:
    url, api_key = _endpoint()
    data = await _post_json(url, api_key, _request_payload(messages, stream=False), "request")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderRequestFailed("The AI service returned no completion text.") from exc
    if not isinstance(content, str) or not content.strip():
        raise ProviderRequestFailed("The AI service returned an empty response.")
    return content.strip()


async def complete_with_tools(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
    url, api_key = _endpoint()
    payload = _request_payload(messages, stream=False)
    payload.update({"tools": tools, "tool_choice": "auto"})
    data = await _post_json(url, api_key, payload, "tool-selection request")
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderRequestFailed("The AI provider returned no tool-selection response.") from exc
    if not isinstance(message, dict):
        raise ProviderRequestFailed("The AI provider returned a malformed tool-selection response.")
    return message


async def stream_completion(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> AsyncIterator[str]:
    url, api_key = _endpoint()
    timeout = httpx.Timeout(35.0 if max_tokens and max_tokens <= 220 else 90.0, connect=4.0)
    payload = _request_payload(messages, stream=True, max_tokens=max_tokens, temperature=temperature)
    # Fresh client per stream avoids keep-alive stalls after cancelled voice turns.
    last_error: Exception | None = None
    for attempt in range(2):
        produced = False
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                ) as response:
                    if response.is_error:
                        body = await response.aread()
                        detail = ""
                        try:
                            err = json.loads(body.decode("utf-8", errors="ignore"))
                            if isinstance(err, dict):
                                detail = str((err.get("error") or {}).get("message") or err.get("message") or "")
                        except Exception:
                            detail = body[:180].decode("utf-8", errors="ignore") if body else ""
                        status = response.status_code
                        message = f"AI service returned HTTP {status}" + (f": {detail}" if detail else ".")
                        if status in {429, 503} and attempt == 0:
                            last_error = ProviderRequestFailed(message)
                            await asyncio.sleep(0.45)
                            continue
                        raise ProviderRequestFailed(message)
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(event, dict):
                            continue
                        if event.get("error"):
                            raise ProviderRequestFailed("The AI service returned a streaming error.")
                        choices = event.get("choices") or []
                        if not choices or not isinstance(choices[0], dict):
                            continue
                        delta = (choices[0].get("delta") or {}).get("content")
                        if isinstance(delta, str) and delta:
                            produced = True
                            yield delta
            if produced or attempt == 1:
                return
            # 200 with no text — retry once (capacity / reasoning-only quirks).
            await asyncio.sleep(0.35)
        except httpx.TimeoutException as exc:
            last_error = ProviderRequestFailed("The AI request timed out. Your prompt is retained; retry when ready.")
            if attempt == 0:
                await asyncio.sleep(0.35)
                continue
            raise last_error from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestFailed("The AI service could not be reached. Your prompt is retained; retry when ready.") from exc
    if last_error:
        raise last_error
    raise ProviderRequestFailed("The AI service returned an empty reply. Please try again.")
