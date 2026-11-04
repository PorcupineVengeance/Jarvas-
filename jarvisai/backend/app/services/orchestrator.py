import json
from collections.abc import AsyncIterator
from typing import Any
from app.core.config import get_settings
from app.services.llm import ProviderRequestFailed, complete_with_tools, stream_completion
from app.services.web_research import search_web

MODE_TOOL_CATEGORIES = {
    "research": {"research"},
    "assistant": {"productivity", "memory"},
    "automation": {"computer", "browser", "files", "system"},
    "developer": {"system", "files"},
}


def _research_guidance(messages: list[dict[str, Any]], configured: bool) -> list[dict[str, Any]]:
    result = list(messages)
    if configured:
        instruction = (
            "For current research, use the registered research_search tool when it can help. "
            "Cite only source names/URLs returned by that tool; do not imply you checked other sources. "
            "If no search tool call occurs, state clearly that live sources were not accessed."
        )
    else:
        instruction = (
            "Live research is unavailable because no real research provider is configured. "
            "Do not fabricate search results, citations, URLs or current facts."
        )
    result.append({"role": "system", "content": instruction})
    return result


def _tool_schemas_for_mode(mode: str) -> list[dict[str, Any]]:
    categories = MODE_TOOL_CATEGORIES.get(mode)
    if not categories:
        return []
    # Keep schemas lean for providers that support tools.
    tools = [{
        "type": "function",
        "function": {
            "name": "research_search",
            "description": "Search the configured research provider for current information. Never invent results.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "minLength": 3, "maxLength": 800}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }]
    if mode == "research":
        return tools
    return []


async def orchestrated_stream(messages: list[dict[str, Any]], mode: str) -> AsyncIterator[tuple[str, str]]:
    if mode not in {"research"}:
        # Voice calls need low latency: hard-cap tokens and keep temperature steady.
        if mode == "voice":
            # Plenty of headroom so reasoning models still leave tokens for spoken text.
            async for text in stream_completion(messages, max_tokens=350, temperature=0.4):
                yield "delta", text
            return
        async for text in stream_completion(messages, max_tokens=800, temperature=0.5):
            yield "delta", text
        return

    settings = get_settings()
    ready = settings.research_ready
    research_messages = _research_guidance(messages, ready)
    if not ready:
        async for text in stream_completion(research_messages):
            yield "delta", text
        return

    tools = _tool_schemas_for_mode(mode)
    try:
        decision = await complete_with_tools(research_messages, tools)
    except ProviderRequestFailed:
        # Some models reject tools; fall back to plain streaming with guidance.
        async for text in stream_completion(research_messages):
            yield "delta", text
        return

    calls = decision.get("tool_calls")
    if not calls:
        content = decision.get("content")
        if isinstance(content, str) and content.strip():
            yield "delta", content.strip()
            return
        async for text in stream_completion(research_messages):
            yield "delta", text
        return
    if not isinstance(calls, list) or len(calls) > 3:
        raise ProviderRequestFailed("The assistant returned an unsupported number of research tool requests; no search was run.")

    validated: list[tuple[str, str]] = []
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if name != "research_search":
            raise ProviderRequestFailed("The model requested an unsupported tool. No tool was executed.")
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderRequestFailed("The assistant produced invalid research-tool arguments; no search was run.") from exc
        if not isinstance(arguments, dict) or "query" not in arguments:
            raise ProviderRequestFailed("The assistant's research arguments were invalid; no search was run.")
        query = arguments.get("query")
        if not isinstance(query, str) or not 3 <= len(query.strip()) <= 800:
            raise ProviderRequestFailed("The assistant's research query was invalid; no search was run.")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id or len(call_id) > 160:
            raise ProviderRequestFailed("The assistant returned an invalid research call identifier; no search was run.")
        validated.append((call_id, query.strip()))

    safe_messages = list(research_messages)
    safe_messages.append({"role": "assistant", "content": decision.get("content"), "tool_calls": calls})
    for call_id, query in validated:
        yield "status", "Searching the configured research provider…"
        result = await search_web(query)
        safe_messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result, ensure_ascii=False, default=str)[:18_000]})
    safe_messages.append({
        "role": "system",
        "content": "Summarize only the actual tool results above. Include source names and URLs only when present in those results; distinguish missing fields and uncertainty. Do not claim that other sites were accessed.",
    })
    async for text in stream_completion(safe_messages):
        yield "delta", text
