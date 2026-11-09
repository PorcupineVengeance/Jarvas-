import json
import re
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.core.permissions import (
    SENSITIVE_ACTIONS,
    bluetooth_control_enabled,
    computer_control_enabled,
    full_device_access_enabled,
    live_web_enabled,
)
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
    "computer.storage",
    "computer.open_settings",
    "computer.device_access",
    "browser.search",
    "bluetooth.list",
    "bluetooth.connect",
    "bluetooth.disconnect",
    "files.list",
    "files.find",
    "files.read",
}

LIVE_TOOL_NAMES = {
    "research_search",
    "research_fetch",
    "weather_lookup",
    "location_ip",
    "time_now",
    "time_world_clock",
    "browser_open_url",
    "browser_clipboard_write",
    "browser_notify",
    "browser_share",
    "browser_wake_lock",
    "browser_pick_files",
    "browser_device_snapshot",
    "browser_vibrate",
    "browser_download_text",
    "browser_camera_capture",
    "browser_screen_capture",
}

CLIENT_ACTION_TOOLS = {
    "browser_open_url",
    "browser_clipboard_write",
    "browser_notify",
    "browser_share",
    "browser_wake_lock",
    "browser_pick_files",
    "browser_vibrate",
    "browser_download_text",
    "browser_camera_capture",
    "browser_screen_capture",
}
WEATHER_HINT = re.compile(r"\b(weather|forecast|temperature|humidity|rain|snow|windy|uv index|how (?:hot|cold|warm))\b", re.I)
TIME_HINT = re.compile(
    r"\b("
    r"what(?:'s| is) the (?:time|date)|what time is it|what(?:'s| is) (?:the )?time|"
    r"tell me the time|tell me (?:the )?date|current (?:time|date)|world clock|time in |"
    r"date (?:and|&) time|what day is it|timezone|o'?clock"
    r")\b",
    re.I,
)
LOCATION_HINT = re.compile(
    r"\b("
    r"where am i|my location|my (?:ip|city|country)|what(?:'s| is) my (?:ip|location|city)|"
    r"detect (?:my )?location|ip (?:address )?location"
    r")\b",
    re.I,
)


def _research_guidance(messages: list[dict[str, Any]], configured: bool, *, spoken: bool = False) -> list[dict[str, Any]]:
    result = list(messages)
    if configured:
        instruction = (
            "You have permissioned live tools: research_search (web search), research_fetch (read a public page), "
            "weather_lookup (live weather; use location 'here' when the user means local/auto weather), "
            "location_ip (approximate city from this device's public IP), "
            "time_now (accurate OS date/time; optional city/timezone), and time_world_clock (multiple cities). "
            "For weather with no city given, call weather_lookup with location 'here'. "
            "For date/time or world clock, always call time_now or time_world_clock — never guess the clock. "
            "For 'where am I' / IP location, call location_ip. "
            "For other current facts call research_search first; use research_fetch on a promising URL when snippets are thin. "
            "Cite only source names/URLs returned by tools; do not invent facts. "
            "If no tool call occurs, say clearly that live sources were not accessed."
        )
        if spoken:
            instruction += " Keep the final spoken answer to 1–3 short sentences."
    else:
        instruction = (
            "Live web and weather are unavailable because the user disabled them or no research provider is ready. "
            "You may still use time_now / time_world_clock for accurate clock answers. "
            "Do not fabricate search results, citations, URLs, weather, or other current facts."
        )
    result.append({"role": "system", "content": instruction})
    return result


def _automation_guidance(messages: list[dict[str, Any]], enabled: bool, *, spoken: bool = False) -> list[dict[str, Any]]:
    result = list(messages)
    if enabled:
        full = full_device_access_enabled()
        scope = (
            "Full device access is ON: files anywhere under the user's home folder are authorized, "
            "plus storage reports and system settings. Do not refuse home-folder file access."
            if full
            else "Full device access is off: only the allowed folder list is in scope. "
            "If a path is blocked, say they can enable Full device access in Settings."
        )
        instruction = (
            "You are running inside JARVIS Desktop with computer control ENABLED. "
            "Never say you are unable to access the computer, files, storage, or settings when a matching tool exists — call the tool. "
            "When the user asks to open an app, website, folder, search in the browser, take a screenshot, "
            "check storage/disk space, open system settings, control the laptop, or list/find/read files, call the matching tool immediately. "
            "If they ask whether you have access or to 'use my computer', call computer_device_access first, then help with the next concrete action. "
            "computer_storage reports real disk usage; computer_open_settings opens OS Settings (storage/privacy/etc). "
            "browser_search opens a real web search page in their browser (DuckDuckGo by default). "
            f"{scope} "
            "files_list / files_find / files_read work inside authorized paths. "
            "For Bluetooth headphones/speakers/keyboards: use bluetooth_list, bluetooth_connect, or bluetooth_disconnect when Bluetooth permission is on. "
            "Only use tools for actions the user clearly requested. "
            "After tools run, briefly confirm what happened using the tool results. "
            "Never claim you controlled the computer, files, or Bluetooth unless a tool result confirms it."
        )
        if spoken:
            instruction += " Keep the final spoken answer to 1–3 short sentences. Plain speech only."
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
                "description": "Get live current weather and a short forecast via Open-Meteo. Use location 'here' for auto IP-based local weather.",
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
        {
            "type": "function",
            "function": {
                "name": "location_ip",
                "description": "Resolve this computer's approximate city/region/country/timezone from its public IP address.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "time_now",
                "description": "Accurate current date and time from the OS clock. Optional city or IANA timezone.",
                "parameters": {
                    "type": "object",
                    "properties": {"timezone": {"type": "string", "maxLength": 80}},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "time_world_clock",
                "description": "Accurate current times for multiple cities or IANA timezones.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "places": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1, "maxLength": 80},
                            "minItems": 1,
                            "maxItems": 12,
                        },
                    },
                    "required": ["places"],
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

    if tool_id.startswith("files."):
        from app.services import file_manager

        if tool_id == "files.list":
            return file_manager.list_directory(str(arguments.get("path", "")))
        if tool_id == "files.find":
            return file_manager.find_files(str(arguments.get("directory", "")), str(arguments.get("pattern", "")))
        if tool_id == "files.read":
            max_chars = arguments.get("max_chars", 40_000)
            try:
                max_chars_i = int(max_chars)
            except (TypeError, ValueError):
                max_chars_i = 40_000
            return file_manager.read_text_file(str(arguments.get("path", "")), max_chars=max(200, min(max_chars_i, 40_000)))
        raise ProviderRequestFailed(f"No executor for '{tool_id}'.")

    if tool_id == "computer.open_app":
        return computer_control.open_application(str(arguments.get("name", "")))
    if tool_id == "computer.open_url":
        return computer_control.open_url(str(arguments.get("url", "")))
    if tool_id == "computer.open_path":
        return computer_control.open_path(str(arguments.get("path", "")))
    if tool_id == "computer.screenshot":
        return computer_control.take_screenshot()
    if tool_id == "computer.storage":
        return computer_control.storage_report()
    if tool_id == "computer.open_settings":
        return computer_control.open_system_settings(str(arguments.get("section") or "general"))
    if tool_id == "computer.device_access":
        return computer_control.device_access_summary()
    if tool_id == "browser.search":
        site = arguments.get("site") or "https://duckduckgo.com/?q="
        return await browser_automation.open_and_search(str(arguments.get("query", "")), str(site))
    raise ProviderRequestFailed(f"No executor for '{tool_id}'.")


def _browser_geo_coords(browser_context: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not isinstance(browser_context, dict):
        return None, None
    geo = browser_context.get("geolocation")
    if not isinstance(geo, dict):
        return None, None
    lat, lon = geo.get("latitude"), geo.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    return None, None


def _browser_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "browser_device_snapshot",
                "description": "Summarize browser device context: GPS, battery, network, storage quota, screen, media device counts, clipboard if read, locale.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_open_url",
                "description": "Open an https URL in a new browser tab on the user's device.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 2000}},
                    "required": ["url"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_clipboard_write",
                "description": "Copy text to the user's clipboard in this browser.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 8000}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_notify",
                "description": "Show a system notification in the user's browser (requires notification permission).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 120},
                        "body": {"type": "string", "maxLength": 400},
                    },
                    "required": ["body"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_share",
                "description": "Open the device share sheet (mobile) with text/url.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "maxLength": 120},
                        "text": {"type": "string", "maxLength": 2000},
                        "url": {"type": "string", "maxLength": 2000},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_wake_lock",
                "description": "Keep the phone/laptop screen awake while JARVIS is active.",
                "parameters": {
                    "type": "object",
                    "properties": {"enable": {"type": "boolean"}},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_pick_files",
                "description": "Ask the user to pick local files in the browser and upload them to JARVIS.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "multiple": {"type": "boolean"},
                        "accept": {"type": "string", "maxLength": 120},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_vibrate",
                "description": "Vibrate the user's phone briefly (mobile browsers).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 0, "maximum": 1000},
                            "maxItems": 8,
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_download_text",
                "description": "Download a text/markdown file onto the user's device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "maxLength": 120},
                        "text": {"type": "string", "minLength": 1, "maxLength": 100000},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_camera_capture",
                "description": "Capture a still photo from the user's camera and upload it to JARVIS files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "facing": {"type": "string", "enum": ["user", "environment"]},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "browser_screen_capture",
                "description": "Capture the user's screen/tab (browser will prompt) and upload the image to JARVIS files.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
    ]


async def _execute_live_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    browser_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Clock tools are always available (local OS time; no network required).
    if name == "time_now":
        from app.services.world_time import now_in_timezone

        tz = arguments.get("timezone")
        return now_in_timezone(str(tz).strip() if isinstance(tz, str) and tz.strip() else None)
    if name == "time_world_clock":
        from app.services.world_time import world_clock

        places = arguments.get("places") if isinstance(arguments.get("places"), list) else []
        return world_clock([str(p) for p in places if str(p).strip()])

    if name == "browser_device_snapshot":
        ctx = browser_context if isinstance(browser_context, dict) else {}
        return {
            "ok": True,
            "surface": "web_browser",
            "geolocation": ctx.get("geolocation"),
            "battery": ctx.get("battery"),
            "connection": ctx.get("connection"),
            "screen": ctx.get("screen"),
            "locale": ctx.get("locale"),
            "timezone": ctx.get("timezone"),
            "clipboard_present": bool(ctx.get("clipboard_text")),
            "clipboard_text": ctx.get("clipboard_text"),
            "storage": ctx.get("storage"),
            "media_devices": ctx.get("media_devices"),
            "hardware_concurrency": ctx.get("hardware_concurrency"),
            "device_memory_gb": ctx.get("device_memory_gb"),
            "permissions": ctx.get("permissions"),
            "capabilities": ctx.get("capabilities"),
            "note": "Live browser device snapshot from this user session.",
        }

    if name in CLIENT_ACTION_TOOLS:
        return {
            "ok": True,
            "queued": True,
            "client_action": {"name": name, "arguments": arguments},
            "note": "Action will run in the user's browser.",
        }

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
            location = "here"
        units = arguments.get("units") or "metric"
        lat, lon = _browser_geo_coords(browser_context)
        return await lookup_weather(location.strip(), str(units), latitude=lat, longitude=lon)
    if name == "location_ip":
        lat, lon = _browser_geo_coords(browser_context)
        if lat is not None and lon is not None:
            return {
                "source": "browser_geolocation",
                "latitude": lat,
                "longitude": lon,
                "accuracy_m": (browser_context or {}).get("geolocation", {}).get("accuracy_m") if isinstance(browser_context, dict) else None,
                "label": "Browser GPS location",
                "note": "Precise location from the user's browser (not IP).",
            }
        from app.services.geolocation import resolve_ip_location

        return await resolve_ip_location()
    raise ProviderRequestFailed(f"Unsupported live tool '{name}'.")


async def _stream_with_tool_round(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    execute_calls,
    max_tokens: int | None = None,
    temperature: float = 0.5,
    tool_choice: str | dict[str, Any] = "auto",
) -> AsyncIterator[tuple[str, str]]:
    try:
        decision = await complete_with_tools(messages, tools, tool_choice=tool_choice)
    except ProviderRequestFailed:
        # Retry once with auto if required tool_choice was rejected by the provider.
        if tool_choice != "auto":
            try:
                decision = await complete_with_tools(messages, tools, tool_choice="auto")
            except ProviderRequestFailed:
                async for text in stream_completion(messages, max_tokens=max_tokens, temperature=temperature):
                    yield "delta", text
                return
        else:
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
    browser_context: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
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
            "location_ip": "Resolving location…",
            "time_now": "Reading system clock…",
            "time_world_clock": "Checking world clock…",
            "browser_device_snapshot": "Reading browser device info…",
            "browser_open_url": "Opening a link…",
            "browser_clipboard_write": "Copying to clipboard…",
            "browser_notify": "Sending a notification…",
            "browser_share": "Opening share sheet…",
            "browser_wake_lock": "Updating wake lock…",
            "browser_pick_files": "Opening file picker…",
            "browser_vibrate": "Vibrating device…",
            "browser_download_text": "Preparing download…",
            "browser_camera_capture": "Opening camera…",
            "browser_screen_capture": "Capturing screen…",
        }.get(name, "Using a live tool…")
        yield "status", label
        try:
            result = await _execute_live_tool(name, arguments, browser_context=browser_context)
            if isinstance(result, dict) and isinstance(result.get("client_action"), dict):
                yield "client_action", result["client_action"]
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
        "For time/world clock, speak the exact tool times — never invent a clock reading. "
        "For IP location, note it is approximate city-level from public IP, not GPS. "
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


async def _run_automation_tools(
    calls: list[Any],
    safe_messages: list[dict[str, Any]],
    *,
    spoken: bool = False,
) -> AsyncIterator[tuple[str, str]]:
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

    summary = (
        "Summarize only the tool results above. If a tool failed, say so clearly. "
        "Do not invent additional computer actions. Do not claim you lack access if a tool succeeded."
    )
    if spoken:
        summary += " Answer in 1–3 short spoken sentences. Plain speech only."
    safe_messages.append({"role": "system", "content": summary})
    async for text in stream_completion(
        safe_messages,
        max_tokens=550 if spoken else None,
        temperature=0.4 if spoken else 0.5,
    ):
        yield "delta", text


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            return item["content"]
    return ""


ACCESS_FORCE_TERMS = re.compile(
    r"\b("
    r"access|control|permission|full device|my (?:computer|laptop|pc|files|folder|desktop|downloads|documents)|"
    r"open |launch |screenshot|storage|disk|settings|bluetooth|list (?:my |the )?files|"
    r"read (?:the |my )?file|what(?:'s| is) on my|"
    r"battery|clipboard|notify|notification|share (?:this|it|link)|wake lock|where am i|my location|"
    r"screenshot|screen capture|take a photo|camera|vibrate|download (?:this|a )?file|save (?:this|as)"
    r")\b",
    re.I,
)


async def _combined_desktop_exec(
    calls: list[Any],
    safe_messages: list[dict[str, Any]],
    *,
    spoken: bool = False,
    browser_context: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
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
                "location_ip": "Resolving location…",
                "time_now": "Reading system clock…",
                "time_world_clock": "Checking world clock…",
                "browser_device_snapshot": "Reading browser device info…",
                "browser_open_url": "Opening a link…",
                "browser_clipboard_write": "Copying to clipboard…",
                "browser_notify": "Sending a notification…",
                "browser_share": "Opening share sheet…",
                "browser_wake_lock": "Updating wake lock…",
                "browser_pick_files": "Opening file picker…",
                "browser_vibrate": "Vibrating device…",
                "browser_download_text": "Preparing download…",
                "browser_camera_capture": "Opening camera…",
                "browser_screen_capture": "Capturing screen…",
            }.get(name, "Using a live tool…")
            try:
                result = await _execute_live_tool(name, arguments, browser_context=browser_context)
                if isinstance(result, dict) and isinstance(result.get("client_action"), dict):
                    yield "client_action", result["client_action"]
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

    summary = (
        "Summarize only the tool results above. If a tool failed, say so clearly. "
        "Do not invent extra actions or sources. Do not claim you lack access if a tool succeeded."
    )
    if spoken:
        summary += " Answer in 1–3 short spoken sentences. Plain speech only."
    safe_messages.append({"role": "system", "content": summary})
    async for text in stream_completion(
        safe_messages,
        max_tokens=550 if spoken else None,
        temperature=0.4 if spoken else 0.5,
    ):
        yield "delta", text


def _browser_context_guidance(browser_context: dict[str, Any] | None) -> str:
    if not isinstance(browser_context, dict) or not browser_context:
        return (
            "This is hosted web JARVIS in the user's browser. "
            "You can use live web/weather/time tools and browser_* device tools "
            "(GPS, battery, clipboard, notifications, share, files, camera, screen capture, vibrate, downloads, wake lock). "
            "Do not claim you control their OS desktop apps or arbitrary disk paths — that needs JARVIS Desktop. "
            "When the user asks to take a photo, capture the screen, save a file, or vibrate, call the matching browser_* tool."
        )
    parts = [
        "This is hosted web JARVIS running in the user's browser with live device context below.",
        "Never say you cannot access location, battery, clipboard, notifications, share, files, camera, screen, vibrate, or downloads when tools/context cover them.",
        "For photos use browser_camera_capture; for screen use browser_screen_capture; for saving text use browser_download_text.",
        "OS-level app control and home-folder browsing still require JARVIS Desktop.",
        f"Browser context JSON: {json.dumps(browser_context, ensure_ascii=False, default=str)[:6000]}",
    ]
    return " ".join(parts)


async def _desktop_tool_stream(
    messages: list[dict[str, Any]],
    *,
    spoken: bool = False,
    live_ok: bool = False,
    browser_context: dict[str, Any] | None = None,
    include_computer: bool = True,
) -> AsyncIterator[tuple[str, Any]]:
    """Tool-enabled turn for Desktop (computer tools) or Web (browser tools)."""
    computer_on = include_computer and computer_control_enabled()
    bluetooth_on = include_computer and bluetooth_control_enabled()
    enabled = computer_on or bluetooth_on
    user_text = _last_user_text(messages)

    prompt = list(messages)
    if include_computer:
        prompt = _automation_guidance(prompt, enabled, spoken=spoken)
    else:
        prompt.append({"role": "system", "content": _browser_context_guidance(browser_context)})
        if spoken:
            prompt.append({"role": "system", "content": "Keep the final spoken answer to 1–3 short sentences. Plain speech only."})
    prompt = _research_guidance(prompt, live_ok, spoken=spoken)
    if computer_on:
        prompt.append({
            "role": "system",
            "content": (
                "CRITICAL: Computer control is ENABLED on this Desktop session. "
                "Never say you cannot access the computer, files, storage, settings, or folders. "
                "Call computer_device_access, computer_storage, computer_open_path, files_list, "
                "files_find, files_read, computer_open_app, computer_open_settings, or related tools instead. "
                f"Full device access is {'ON (entire user home)' if full_device_access_enabled() else 'limited to allowed folders'}."
            ),
        })
    if WEATHER_HINT.search(user_text):
        prompt.append({
            "role": "system",
            "content": "Weather question — call weather_lookup (location 'here' if no city named).",
        })
    if TIME_HINT.search(user_text):
        prompt.append({
            "role": "system",
            "content": "Date/time question — call time_now or time_world_clock. Never guess the clock.",
        })
    if LOCATION_HINT.search(user_text):
        prompt.append({
            "role": "system",
            "content": "Location question — call location_ip (uses browser GPS when present, otherwise IP).",
        })

    tools: list[dict[str, Any]] = []
    if include_computer:
        tools = _automation_tool_schemas()
        if not computer_on:
            tools = [tool for tool in tools if str(tool.get("function", {}).get("name", "")).startswith("bluetooth_")]
        if not bluetooth_on:
            tools = [tool for tool in tools if not str(tool.get("function", {}).get("name", "")).startswith("bluetooth_")]
    else:
        tools = tools + _browser_tool_schemas()

    live_schemas = _live_tool_schemas()
    if live_ok:
        tools = tools + live_schemas
    else:
        tools = tools + [
            tool for tool in live_schemas
            if str(tool.get("function", {}).get("name", "")) in {"time_now", "time_world_clock"}
        ]
    if not include_computer:
        # Web always gets browser device tools even when live web is off.
        existing = {str(tool.get("function", {}).get("name", "")) for tool in tools}
        for tool in _browser_tool_schemas():
            name = str(tool.get("function", {}).get("name", ""))
            if name and name not in existing:
                tools.append(tool)

    if not tools:
        async for text in stream_completion(prompt, max_tokens=550 if spoken else 800, temperature=0.4 if spoken else 0.5):
            yield "delta", text
        return

    force_tools = bool(
        ACCESS_FORCE_TERMS.search(user_text)
        and (computer_on or bluetooth_on or not include_computer)
    )
    async for event in _stream_with_tool_round(
        prompt,
        tools,
        execute_calls=lambda calls, safe: _combined_desktop_exec(
            calls, safe, spoken=spoken, browser_context=browser_context,
        ),
        max_tokens=550 if spoken else 900,
        temperature=0.4 if spoken else 0.45,
        tool_choice="required" if force_tools else "auto",
    ):
        yield event


async def orchestrated_stream(
    messages: list[dict[str, Any]],
    mode: str,
    *,
    spoken: bool = False,
    browser_context: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    from app.services.desktop_settings import sync_desktop_settings_from_disk

    # Always re-apply Desktop permission JSON so toggles take effect without restart.
    sync_desktop_settings_from_disk()
    settings = get_settings()
    live_ok = live_web_enabled() and settings.research_ready

    # Desktop: tools every turn when permissions are on (voice/normal/auto all work).
    if settings.is_desktop:
        async for event in _desktop_tool_stream(
            messages, spoken=spoken, live_ok=live_ok, browser_context=browser_context, include_computer=True,
        ):
            yield event
        return

    # Hosted web: always give live + browser device tools so it stops falsely refusing access.
    async for event in _desktop_tool_stream(
        messages, spoken=spoken, live_ok=live_ok, browser_context=browser_context, include_computer=False,
    ):
        yield event
    _ = mode  # retained for API compatibility with callers
