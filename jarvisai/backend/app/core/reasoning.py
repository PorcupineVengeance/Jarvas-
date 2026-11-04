"""Lightweight planning helpers for multi-step requests."""

from __future__ import annotations
import re
from typing import Any

COMPLEX_HINTS = re.compile(
    r"\b(research|report|compare|prepare|analyze|plan|automate|multi[- ]step|then|and then)\b",
    re.I,
)


def looks_complex(message: str) -> bool:
    return bool(COMPLEX_HINTS.search(message)) and len(message.split()) >= 8


def draft_plan(message: str, mode: str) -> list[dict[str, Any]]:
    """Heuristic plan skeleton; the LLM fills details during orchestration."""
    steps: list[dict[str, Any]] = [{"id": 1, "action": "understand", "detail": "Clarify the requested outcome and constraints."}]
    if mode == "research" or "research" in message.lower():
        steps.append({"id": 2, "action": "research", "detail": "Search configured providers and collect sources."})
        steps.append({"id": 3, "action": "analyze", "detail": "Compare findings and note uncertainties."})
        steps.append({"id": 4, "action": "report", "detail": "Produce a structured summary with citations from actual results."})
    elif mode == "automation":
        steps.append({"id": 2, "action": "permissions", "detail": "Check computer-control and path authorization."})
        steps.append({"id": 3, "action": "execute", "detail": "Run allow-listed tools with confirmation for write actions."})
        steps.append({"id": 4, "action": "verify", "detail": "Confirm success or report failure honestly."})
    else:
        steps.append({"id": 2, "action": "respond", "detail": "Answer using conversation context and available tools."})
    return steps
