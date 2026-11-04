import json
from collections.abc import AsyncIterator
from typing import Any
import httpx
from app.core.config import get_settings


class ProviderUnavailable(RuntimeError):
    pass


class ProviderRequestFailed(RuntimeError):
    pass


def _request_payload(messages: list[dict[str, Any]], stream: bool) -> dict[str, Any]:
    settings = get_settings()
    payload: dict[str, Any] = {"messages": messages, "stream": stream}
    if settings.llm_model:
        payload["model"] = settings.llm_model
    return payload


def _endpoint() -> tuple[str, str]:
    settings = get_settings()
    if not settings.llm_ready or not settings.llm_completion_url or not settings.llm_api_key:
        raise ProviderUnavailable("No complete LLM provider configuration is available.")
    return settings.llm_completion_url, settings.llm_api_key


async def _post_json(url: str, api_key: str, payload: dict[str, Any], label: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=8.0)) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {api_key}"}, json=payload)
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


async def stream_completion(messages: list[dict[str, Any]]) -> AsyncIterator[str]:
    url, api_key = _endpoint()
    timeout = httpx.Timeout(90.0, connect=8.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers={"Authorization": f"Bearer {api_key}"}, json=_request_payload(messages, stream=True)) as response:
                if response.is_error:
                    await response.aread()
                    raise ProviderRequestFailed(f"AI service returned HTTP {response.status_code}.")
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
                        yield delta
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed("The AI request timed out. Your prompt is retained; retry when ready.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed("The AI service could not be reached. Your prompt is retained; retry when ready.") from exc
