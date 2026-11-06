import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.core.permissions import SENSITIVE_ACTIONS, bluetooth_control_enabled, computer_control_enabled, live_web_enabled
from app.services.llm import ProviderRequestFailed, complete_with_tools, stream_completion
from app.services.web_research import search_web

MODE_TOOL_CATEGORIES = {
    "research": {"research"},
    "assistant": {"productivity", "memory"},
    "automation": {"computer", "browser", "files", "bluetooth"},
    "developer": {"system", "files"},
}

# Chat-safe computer tools (non-destructive everyday help).
AUTOMATION_TOOL_IDS = {
    "computer.open_app",
    "computer.open_url",
    "computer.open_path",
    "computer.screenshot",
    "browser.search",
    "bluetooth.list",
    "bluetooth.connect",
    "bluetooth.disconnect",
}

LIVE_TOOL_NAMES = {"research_search", "research_fetch", "weather_lookup"}
WEATHER_HINT = re.compile(r"\b(weather|forecast|temperature|humidity|rain|snow|windy|uv index|how (?:hot|cold|warm))\b", re.I)


def _research_guidance(messages: list[dict[str, Any]], configured: bool, *, spoken: bool = False) -> list[dict[str, Any]]:
    result = list(messages)
    if configured:
        instruction = (
            "You have permissioned live tools: research_search (web search), research_fetch (read a public page), "
            "and weather_lookup (current weather / short forecast). "
            "For weather questions call weather_lookup with a city or place. "
            "For other current facts call research_search first; use research_fetch on a promising URL when snippets are thin. "
            "Cite only source names/URLs returned by tools; do not invent facts. "
            "If no tool call occurs, say clearly that live sources were not accessed."
        )
        if spoken:
            instruction += " Keep the final spoken answer to 1–3 short sentences."
    else:
        instruction = (
            "Live web and weather are unavailable because the user disabled them or no research provider is ready. "
            "Do not fabricate search results, citations, URLs, weather, or other current facts."
        )
    result.append({"role": "system", "content": instruction})
    return result


def _automation_guidance(messages: list[dict[str, Any]], enabled: bool) -> list[dict[str, Any]]:
    result = list(messages)
    if enabled:
        instruction = (
            "You are running inside JARVIS Desktop with permissioned computer control. "
            "When the user asks to open an app, website, folder, search in the browser, or take a screenshot, call the matching tool. "
            "browser_search opens a real web search page in their browser (DuckDuckGo by default). "
            "For Bluetooth headphones/speakers/keyboards: use bluetooth_list, bluetooth_connect, or bluetooth_disconnect when Bluetooth permission is on. "
            "Only use tools for actions the user clearly requested. "
            "After tools run, briefly confirm what happened using the tool results. "
            "Never claim you controlled the computer or Bluetooth unless a tool result confirms it."
        )
    else:
        instruction = (
            "Computer control is disabled. Do not claim you opened apps, folders, or took screenshots. "
            "Tell the user to enable computer control in Settings → Desktop permissions. "
            "You can still answer from live web tools if those are enabled separately."
        )
    result.append({"role": "system", "content": instruction})
    return result


def _live_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "research_search",
                "description": "Search the live web for current information. Never invent results.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "minLength": 3, "maxLength": 800}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "research_fetch",
                "description": "Fetch readable text from a public http(s) page after search. Use when snippets are insufficient.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "minLength": 8, "maxLength": 2000},
                        "max_chars": {"type": "integer", "minimum": 500, "maximum": 12000},
                    },
                    "required": ["url"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "weather_lookup",
                "description": "Get live current weather and a short forecast for a city or place via Open-Meteo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "minLength": 1, "maxLength": 120},
                        "units": {"type": "string", "enum": ["metric", "imperial"]},
                    },
                    "required": ["location"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _automation_tool_schemas() -> list[dict[str, Any]]:
    from app.tools.registry import get_registry

    registry = get_registry()
    schemas: list[dict[str, Any]] = []
    for tool_id in sorted(AUTOMATION_TOOL_IDS):
        tool = registry.get(tool_id)
        if tool is None:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": tool.id.replace(".", "_"),
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        })
    return schemas


def _tool_id_from_function_name(name: str) -> str:
    if name in LIVE_TOOL_NAMES:
        return name
    if name.startswith("computer_") or name.startswith("browser_") or name.startswith("files_") or name.startswith("bluetooth_"):
        return name.replace("_", ".", 1)
    return name.replace("_", ".")


async def _execute_automation_tool(tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_id not in AUTOMATION_TOOL_IDS:
        raise ProviderRequestFailed(f"Tool '{tool_id}' is not available in chat automation.")
    if tool_id in SENSITIVE_ACTIONS:
        raise ProviderRequestFailed(f"Tool '{tool_id}' requires explicit confirmation outside chat.")

    from app.services import bluetooth_control, browser_automation, computer_control

    if tool_id.startswith("bluetooth."):
        if not bluetooth_control_enabled():
            raise ProviderRequestFailed("Bluetooth control is disabled. Enable it in Settings → Desktop permissions.")
        if tool_id == "bluetooth.list":
            return bluetooth_control.list_devices()
        if tool_id == "bluetooth.connect":
            return bluetooth_control.connect_device(str(arguments.get("device", "")))
        if tool_id == "bluetooth.disconnect":
            return bluetooth_control.disconnect_device(str(arguments.get("device", "")))
        raise ProviderRequestFailed(f"No executor for '{tool_id}'.")

    if not computer_control_enabled():
        raise ProviderRequestFailed("Computer control is disabled.")

    if tool_id == "computer.open_app":
        return computer_control.open_application(str(arguments.get("name", "")))
    if tool_id == "computer.open_url":
        return computer_control.open_url(str(arguments.get("url", "")))
    if tool_id == "computer.open_path":
        return computer_control.open_path(str(arguments.get("path", "")))
    if tool_id == "computer.screenshot":
        return computer_control.take_screenshot()
    if tool_id == "browser.search":
        site = arguments.get("site") or "https://duckduckgo.com/?q="
        return await browser_automation.open_and_search(str(arguments.get("query", "")), str(site))
    raise ProviderRequestFailed(f"No executor for '{tool_id}'.")


async def _execute_live_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not live_web_enabled():
        raise ProviderRequestFailed("Live web and weather are disabled in Settings.")
    if name == "research_search":
        query = arguments.get("query")
        if not isinstance(query, str) or not 3 <= len(query.strip()) <= 800:
            raise ProviderRequestFailed("Invalid research query.")
        return await search_web(query.strip())
    if name == "research_fetch":
        from app.services.browser_automation import fetch_page_text

        url = arguments.get("url")
        if not isinstance(url, str):
            raise ProviderRequestFailed("Invalid page URL.")
        max_chars = arguments.get("max_chars", 8000)
        try:
            max_chars_i = int(max_chars)
        except (TypeError, ValueError):
            max_chars_i = 8000
        max_chars_i = max(500, min(max_chars_i, 12_000))
        return await fetch_page_text(url.strip(), max_chars=max_chars_i)
    if name == "weather_lookup":
        from app.services.weather import lookup_weather

        location = arguments.get("location")
        if not isinstance(location, str) or not location.strip():
            raise ProviderRequestFailed("Invalid weather location.")
        units = arguments.get("units") or "metric"
        return await lookup_weather(location.strip(), str(units))
    raise ProviderRequestFailed(f"Unsupported live tool '{name}'.")


async def _stream_with_tool_round(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    execute_calls,
    max_tokens: int | None = None,
    temperature: float = 0.5,
) -> AsyncIterator[tuple[str, str]]:
    try:
        decision = await complete_with_tools(messages, tools)
    except ProviderRequestFailed:
        async for text in stream_completion(messages, max_tokens=max_tokens, temperature=temperature):
            yield "delta", text
        return

    calls = decision.get("tool_calls")
    if not calls:
        content = decision.get("content")
        if isinstance(content, str) and content.strip():
            yield "delta", content.strip()
            return
        async for text in stream_completion(messages, max_tokens=max_tokens, temperature=temperature):
            yield "delta", text
        return
    if not isinstance(calls, list) or len(calls) > 4:
        raise ProviderRequestFailed("The assistant returned an unsupported number of tool requests.")

    safe_messages = list(messages)
    safe_messages.append({"role": "assistant", "content": decision.get("content"), "tool_calls": calls})
    async for event in execute_calls(calls, safe_messages):
        yield event


async def _run_live_tools(
    calls: list[Any],
    safe_messages: list[dict[str, Any]],
    *,
    spoken: bool = False,
) -> AsyncIterator[tuple[str, str]]:
    validated: list[tuple[str, str, dict[str, Any]]] = []
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if name not in LIVE_TOOL_NAMES:
            raise ProviderRequestFailed("The model requested an unsupported tool. No tool was executed.")
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderRequestFailed("The assistant produced invalid live-tool arguments.") from exc
        if not isinstance(arguments, dict):
            raise ProviderRequestFailed("Live tool arguments must be an object.")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id or len(call_id) > 160:
            raise ProviderRequestFailed("Invalid live tool call id.")
        validated.append((call_id, name, arguments))

    for call_id, name, arguments in validated:
        label = {
            "research_search": "Searching the web…",
            "research_fetch": "Reading a web page…",
            "weather_lookup": "Checking live weather…",
        }.get(name, "Using a live tool…")
        yield "status", label
        try:
            result = await _execute_live_tool(name, arguments)
            payload = {"ok": True, "tool": name, "result": result}
        except Exception as exc:
            payload = {"ok": False, "tool": name, "error": str(exc)}
        safe_messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(payload, ensure_ascii=False, default=str)[:18_000],
        })

    summary = (
        "Summarize only the actual tool results above. Include source names and URLs only when present. "
        "For weather, speak the location, conditions, and temperature clearly. "
        "Do not claim that other sites were accessed."
    )
    if spoken:
        summary += " Answer in 1–3 short spoken sentences."
    safe_messages.append({"role": "system", "content": summary})
    async for text in stream_completion(
        safe_messages,
        max_tokens=550 if spoken else 900,
        temperature=0.4 if spoken else 0.45,
    ):
        yield "delta", text


async def _run_automation_tools(calls: list[Any], safe_messages: list[dict[str, Any]]) -> AsyncIterator[tuple[str, str]]:
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name:
            raise ProviderRequestFailed("The assistant returned an invalid tool name.")
        tool_id = _tool_id_from_function_name(name)
        if tool_id not in AUTOMATION_TOOL_IDS:
            candidate = name.replace("_", ".")
            if candidate in AUTOMATION_TOOL_IDS:
                tool_id = candidate
            else:
                raise ProviderRequestFailed(f"Unsupported automation tool '{name}'.")
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderRequestFailed("Invalid automation tool arguments.") from exc
        if not isinstance(arguments, dict):
            raise ProviderRequestFailed("Automation tool arguments must be an object.")
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id or len(call_id) > 160:
            raise ProviderRequestFailed("Invalid automation tool call id.")
        yield "status", f"Running {tool_id}…"
        try:
            result = await _execute_automation_tool(tool_id, arguments)
            payload = {"ok": True, "tool_id": tool_id, "result": result}
        except Exception as exc:
            payload = {"ok": False, "tool_id": tool_id, "error": str(exc)}
        safe_messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(payload, ensure_ascii=False, default=str)[:12_000]})

    safe_messages.append({
        "role": "system",
        "content": "Summarize only the tool results above. If a tool failed, say so clearly. Do not invent additional computer actions.",
    })
    async for text in stream_completion(safe_messages):
        yield "delta", text


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            return item["content"]
    return ""


async def orchestrated_stream(
    messages: list[dict[str, Any]],
    mode: str,
    *,
    spoken: bool = False,
) -> AsyncIterator[tuple[str, str]]:
    settings = get_settings()
    live_ok = live_web_enabled() and settings.research_ready

    # Research mode (including voice questions promoted for live facts).
    if mode == "research":
        research_messages = _research_guidance(messages, live_ok, spoken=spoken)
        if not live_ok:
            async for text in stream_completion(
                research_messages,
                max_tokens=550 if spoken else None,
                temperature=0.4 if spoken else 0.5,
            ):
                yield "delta", text
            return

        # Soft nudge: weather questions should prefer weather_lookup.
        user_text = _last_user_text(messages)
        if WEATHER_HINT.search(user_text):
            research_messages.append({
                "role": "system",
                "content": "This looks like a weather question — call weather_lookup with the best place name you can infer (ask only if none is given).",
            })

        async def _live_exec(calls: list[Any], safe_messages: list[dict[str, Any]]):
            async for event in _run_live_tools(calls, safe_messages, spoken=spoken):
                yield event

        async for event in _stream_with_tool_round(
            research_messages,
            _live_tool_schemas(),
            execute_calls=_live_exec,
            max_tokens=550 if spoken else 900,
            temperature=0.4 if spoken else 0.45,
        ):
            yield event
        return

    if mode == "automation":
        computer_on = computer_control_enabled()
        bluetooth_on = bluetooth_control_enabled()
        enabled = computer_on or bluetooth_on
        automation_messages = _automation_guidance(messages, enabled)
        # Also allow live answer tools when the user asked to research something while controlling the PC.
        tools = _automation_tool_schemas()
        if not computer_on:
            tools = [tool for tool in tools if str(tool.get("function", {}).get("name", "")).startswith("bluetooth_")]
        if not bluetooth_on:
            tools = [tool for tool in tools if not str(tool.get("function", {}).get("name", "")).startswith("bluetooth_")]
        if bluetooth_on:
            automation_messages.append({
                "role": "system",
                "content": (
                    "Bluetooth permission is enabled. For paired accessories use bluetooth_list / "
                    "bluetooth_connect / bluetooth_disconnect with the device name."
                ),
            })
        if live_ok:
            tools = tools + _live_tool_schemas()
            automation_messages.append({
                "role": "system",
                "content": (
                    "If the user wants you to look something up and answer (not just open a page), "
                    "use research_search / weather_lookup / research_fetch. "
                    "If they want the browser opened for them, use browser_search or computer_open_url."
                ),
            })
        if not enabled and not live_ok:
            async for text in stream_completion(automation_messages):
                yield "delta", text
            return
        if not tools:
            async for text in stream_completion(automation_messages):
                yield "delta", text
            return

        # Combined executor: desktop open/browse tools + live web/weather in one round.
        async def _combined_exec(calls: list[Any], safe_messages: list[dict[str, Any]]):
            for call in calls:
                function = call.get("function") if isinstance(call, dict) else None
                name = function.get("name") if isinstance(function, dict) else None
                if not isinstance(name, str) or not name:
                    raise ProviderRequestFailed("The assistant returned an invalid tool name.")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ProviderRequestFailed("Invalid tool arguments.") from exc
                if not isinstance(arguments, dict):
                    raise ProviderRequestFailed("Tool arguments must be an object.")
                call_id = call.get("id")
                if not isinstance(call_id, str) or not call_id or len(call_id) > 160:
                    raise ProviderRequestFailed("Invalid tool call id.")

                if name in LIVE_TOOL_NAMES:
                    yield "status", {
                        "research_search": "Searching the web…",
                        "research_fetch": "Reading a web page…",
                        "weather_lookup": "Checking live weather…",
                    }.get(name, "Using a live tool…")
                    try:
                        result = await _execute_live_tool(name, arguments)
                        payload = {"ok": True, "tool": name, "result": result}
                    except Exception as exc:
                        payload = {"ok": False, "tool": name, "error": str(exc)}
                else:
                    tool_id = _tool_id_from_function_name(name)
                    if tool_id not in AUTOMATION_TOOL_IDS:
                        candidate = name.replace("_", ".")
                        if candidate in AUTOMATION_TOOL_IDS:
                            tool_id = candidate
                        else:
                            raise ProviderRequestFailed(f"Unsupported tool '{name}'.")
                    yield "status", f"Running {tool_id}…"
                    try:
                        result = await _execute_automation_tool(tool_id, arguments)
                        payload = {"ok": True, "tool_id": tool_id, "result": result}
                    except Exception as exc:
                        payload = {"ok": False, "tool_id": tool_id, "error": str(exc)}
                safe_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": json.dumps(payload, ensure_ascii=False, default=str)[:18_000],
                })

            safe_messages.append({
                "role": "system",
                "content": "Summarize only the tool results above. If a tool failed, say so clearly. Do not invent extra actions or sources.",
            })
            async for text in stream_completion(safe_messages):
                yield "delta", text

        async for event in _stream_with_tool_round(
            automation_messages,
            tools,
            execute_calls=_combined_exec,
        ):
            yield event
        return

    # Voice calls need low latency: hard-cap tokens and keep temperature steady.
    if mode == "voice":
        async for text in stream_completion(messages, max_tokens=550, temperature=0.4):
            yield "delta", text
        return
    async for text in stream_completion(messages, max_tokens=800, temperature=0.5):
        yield "delta", text
