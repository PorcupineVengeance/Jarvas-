from typing import Any
import httpx
from app.core.config import get_settings
from app.services.llm import ProviderRequestFailed, ProviderUnavailable


async def search_web(query: str, max_results: int = 8) -> dict[str, Any]:
    settings = get_settings()
    provider = (settings.jarvis_research_provider or "duckduckgo").lower()
    if provider == "tavily":
        return await _tavily_search(query, max_results)
    if provider == "manus":
        from app.api.research import search_provider_manus
        return await search_provider_manus(query)
    if provider == "duckduckgo":
        return await _duckduckgo_search(query, max_results)
    raise ProviderUnavailable(f"Research provider '{provider}' is not supported.")


async def _tavily_search(query: str, max_results: int) -> dict[str, Any]:
    settings = get_settings()
    if not settings.jarvis_tavily_api_key:
        raise ProviderUnavailable("Tavily research requires JARVIS_TAVILY_API_KEY.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=8.0)) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": settings.jarvis_tavily_api_key, "query": query, "max_results": max_results, "include_answer": True},
            )
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed("The Tavily research provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed("The Tavily research provider could not be reached.") from exc
    if response.is_error:
        raise ProviderRequestFailed(f"Tavily returned HTTP {response.status_code}.")
    data = response.json()
    results = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": item.get("content") or item.get("snippet"),
            "score": item.get("score"),
        })
    return {
        "provider": "tavily",
        "query": query,
        "answer": data.get("answer"),
        "results": results,
        "source_note": "Cite only titles/URLs present in these results.",
    }


def _normalize_ddg_item(item: dict) -> dict | None:
    title = item.get("title") or item.get("heading")
    url = item.get("href") or item.get("link") or item.get("url") or item.get("FirstURL")
    snippet = item.get("body") or item.get("snippet") or item.get("content") or item.get("Text")
    if not (title or url or snippet):
        return None
    return {"title": title, "url": url, "snippet": snippet}


async def _duckduckgo_search(query: str, max_results: int) -> dict[str, Any]:
    errors: list[str] = []
    results: list[dict] = []

    # 1) ddgs package (preferred when it works)
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=max_results))
        for item in raw:
            if isinstance(item, dict):
                normalized = _normalize_ddg_item(item)
                if normalized:
                    results.append(normalized)
    except Exception as exc:
        errors.append(f"ddgs:{exc}")

    # 2) DuckDuckGo Instant Answer JSON API (no key)
    if not results:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    headers={"User-Agent": "JARVIS-Research/1.0"},
                )
            if response.is_error:
                errors.append(f"instant:{response.status_code}")
            else:
                data = response.json()
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading") or query,
                        "url": data.get("AbstractURL"),
                        "snippet": data.get("AbstractText"),
                    })
                for topic in (data.get("RelatedTopics") or [])[:max_results]:
                    if isinstance(topic, dict):
                        normalized = _normalize_ddg_item(topic)
                        if normalized:
                            results.append(normalized)
                    elif isinstance(topic, dict) is False and isinstance(topic, list):
                        continue
                    # Nested topic groups
                    if isinstance(topic, dict) and isinstance(topic.get("Topics"), list):
                        for nested in topic["Topics"][:5]:
                            if isinstance(nested, dict):
                                normalized = _normalize_ddg_item(nested)
                                if normalized:
                                    results.append(normalized)
        except Exception as exc:
            errors.append(f"instant:{exc}")

    # 3) Lite HTML endpoint as last resort
    if not results:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0), follow_redirects=True) as client:
                response = await client.get(
                    "https://lite.duckduckgo.com/lite/",
                    params={"q": query},
                    headers={"User-Agent": "JARVIS-Research/1.0"},
                )
            if response.is_error:
                errors.append(f"lite:{response.status_code}")
            else:
                import re
                # Extract result anchors from lite HTML.
                for match in re.finditer(r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', response.text, re.I | re.S):
                    url = match.group(1)
                    title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
                    if url.startswith("http") and title:
                        results.append({"title": title, "url": url, "snippet": None})
                    if len(results) >= max_results:
                        break
        except Exception as exc:
            errors.append(f"lite:{exc}")

    # Deduplicate by URL/title
    unique: list[dict] = []
    seen: set[str] = set()
    for item in results:
        key = (item.get("url") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= max_results:
            break

    # 4) Wikipedia OpenSearch — reliable fallback for people/places/topics.
    if not unique:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=6.0), follow_redirects=True) as client:
                response = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "opensearch",
                        "search": query,
                        "limit": max_results,
                        "namespace": 0,
                        "format": "json",
                    },
                    headers={"User-Agent": "JARVIS-Research/1.0"},
                )
            if not response.is_error:
                data = response.json()
                titles = data[1] if isinstance(data, list) and len(data) > 1 else []
                descs = data[2] if isinstance(data, list) and len(data) > 2 else []
                urls = data[3] if isinstance(data, list) and len(data) > 3 else []
                for index, title in enumerate(titles):
                    unique.append({
                        "title": title,
                        "url": urls[index] if index < len(urls) else None,
                        "snippet": descs[index] if index < len(descs) else None,
                    })
        except Exception as exc:
            errors.append(f"wikipedia:{exc}")

    if not unique:
        # Soft empty payload so chat can explain the miss instead of hard-failing the turn.
        return {
            "provider": "duckduckgo",
            "query": query,
            "results": [],
            "errors": errors[:6],
            "source_note": "No live web results were returned. Say so clearly; do not invent sources.",
        }

    return {
        "provider": "duckduckgo",
        "query": query,
        "results": unique,
        "source_note": "Cite only titles/URLs present in these results. Live pages beyond the snippets were not fetched unless separately retrieved.",
    }
