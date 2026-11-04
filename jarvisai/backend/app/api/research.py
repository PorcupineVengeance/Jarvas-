from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.models import User
from app.services.llm import ProviderRequestFailed, ProviderUnavailable
from app.services.web_research import search_web

router = APIRouter(prefix="/api/research", tags=["research"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=800)


async def search_provider_manus(query: str) -> dict:
    settings = get_settings()
    if not settings.jarvis_research_api_id:
        raise ProviderUnavailable("No research API Hub identifier is configured.")
    if not settings.manus_service_ready or not settings.api_base:
        raise ProviderUnavailable("The managed API service is not configured in this runtime.")
    url = f"{settings.api_base}/webdevtoken.v1.WebDevService/CallApi"
    payload = {"apiId": settings.jarvis_research_api_id, "query": {"q": query.strip()}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=8.0)) as client:
            response = await client.post(url, headers={"Authorization": f"Bearer {settings.manus_api_key}", "Content-Type": "application/json", "connect-protocol-version": "1"}, json=payload)
    except httpx.TimeoutException as exc:
        raise ProviderRequestFailed("The research provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise ProviderRequestFailed("The research provider could not be reached.") from exc
    if response.is_error:
        raise ProviderRequestFailed(f"The research provider returned HTTP {response.status_code}.")
    result = response.json()
    if isinstance(result, dict) and result.get("error"):
        raise ProviderRequestFailed("The selected research API reported an error.")
    if isinstance(result, dict) and isinstance(result.get("jsonData"), str):
        try:
            result = __import__("json").loads(result["jsonData"])
        except (ValueError, TypeError):
            raise ProviderRequestFailed("The research API returned an invalid JSON result.")
    return {"provider": "manus", "api_id": settings.jarvis_research_api_id, "query": query, "result": result, "source_note": "Use only source names and URLs present in the result."}


async def search_provider(query: str) -> dict:
    return await search_web(query)


@router.post("/search")
async def search(body: SearchRequest, _user: User = Depends(get_current_user)):
    settings = get_settings()
    if not settings.research_ready:
        raise HTTPException(status_code=503, detail="Research is not configured. Set JARVIS_RESEARCH_PROVIDER=duckduckgo or provide Tavily/Manus credentials.")
    try:
        return await search_provider(body.query)
    except ProviderUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderRequestFailed as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
