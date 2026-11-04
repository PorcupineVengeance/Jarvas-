import base64
import json
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from app.core.config import get_settings
from app.core.security import SESSION_COOKIE, is_allowed_request_origin, session_cookie_options

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _safe_origin(request: Request, supplied: str | None = None, check_header: bool = True) -> str:
    origin_header = request.headers.get("origin") if check_header else None
    origin = (supplied or origin_header or "").rstrip("/")
    try:
        parts = urlsplit(origin)
        valid = parts.scheme in {"https", "http"} and bool(parts.netloc) and not parts.username and not parts.password and not parts.path and not parts.query and not parts.fragment
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(status_code=400, detail="A valid application origin is required.")
    if origin_header and origin_header.rstrip("/") != origin:
        raise HTTPException(status_code=400, detail="The requested origin does not match this browser session.")
    if not is_allowed_request_origin(request, origin):
        raise HTTPException(status_code=400, detail="This application origin is not allow-listed. Configure its exact origin in JARVIS_ALLOWED_ORIGINS.")
    return origin


@router.get("/config")
def auth_config():
    settings = get_settings()
    if settings.oauth_ready:
        return {"available": True, "provider": "Manus OAuth", "local_available": settings.local_auth_ready, "reason": None}
    if settings.local_auth_ready:
        return {"available": True, "provider": "Local session", "local_available": True, "reason": None}
    return {"available": False, "provider": "none", "local_available": False, "reason": "Configure Manus OAuth or enable JARVIS_LOCAL_AUTH_ENABLED with JARVIS_LOCAL_AUTH_SECRET."}


@router.get("/session")
def session(request: Request):
    from app.core.security import decode_session
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return {"authenticated": False}
    try:
        claims = decode_session(token)
        return {"authenticated": True, "user": {"id": claims["openId"], "name": claims.get("name", "JARVIS user"), "email": claims.get("email")}}
    except HTTPException:
        return {"authenticated": False}


class LocalLoginRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)


@router.post("/local-login")
def local_login(request: Request, response: Response, body: LocalLoginRequest | None = None):
    settings = get_settings()
    if not settings.local_auth_ready:
        raise HTTPException(status_code=503, detail="Local authentication is not enabled. Set JARVIS_LOCAL_AUTH_ENABLED and JARVIS_LOCAL_AUTH_SECRET.")
    origin = request.headers.get("origin")
    if origin and not is_allowed_request_origin(request, origin):
        raise HTTPException(status_code=403, detail="Cross-origin local sign-in is not allowed.")
    name = ((body.display_name if body else None) or settings.jarvis_local_auth_display_name or "Operator").strip()[:120] or "Operator"
    now = datetime.now(timezone.utc)
    claims = {
        "openId": "local-operator",
        "appId": "jarvis-local",
        "authMode": "local",
        "name": name,
        "email": None,
        "iat": now,
        "exp": now + timedelta(seconds=settings.jarvis_session_ttl_seconds),
    }
    token = jwt.encode(claims, settings.jarvis_local_auth_secret, algorithm="HS256")
    cookie = session_cookie_options(origin)
    response.set_cookie(value=token, **cookie)
    return {"ok": True, "authenticated": True, "user": {"id": "local-operator", "name": name, "email": None}}


@router.get("/login")
def login(request: Request, origin: str | None = None):
    settings = get_settings()
    if not settings.oauth_ready:
        raise HTTPException(status_code=503, detail="Manus OAuth is not available. Use local sign-in when JARVIS_LOCAL_AUTH_ENABLED is configured.")
    public_origin = _safe_origin(request, origin)
    callback = f"{public_origin}/api/auth/callback"
    nonce = secrets.token_urlsafe(24)
    state_payload = {"redirectUri": callback, "nonce": nonce}
    state = base64.urlsafe_b64encode(json.dumps(state_payload, separators=(",", ":")).encode()).decode().rstrip("=")
    portal = (settings.manus_oauth_portal_url or "").rstrip("/") + "/app-auth"
    query = urlencode({"appId": settings.manus_project_id, "redirectUri": callback, "state": state, "responseType": "code"})
    response = RedirectResponse(f"{portal}?{query}", status_code=302)
    secure = public_origin.startswith("https://")
    response.set_cookie("jarvis_oauth_nonce", nonce, httponly=True, secure=secure, samesite="none" if secure else "lax", max_age=600, path="/api/auth")
    return response


@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    settings = get_settings()
    if not settings.oauth_ready:
        raise HTTPException(status_code=503, detail="Manus OAuth is not configured.")
    try:
        padded = state + "=" * (-len(state) % 4)
        state_data = json.loads(base64.urlsafe_b64decode(padded).decode())
        callback_uri = str(state_data["redirectUri"])
        expected_nonce = str(state_data["nonce"])
        public_origin = callback_uri.removesuffix("/api/auth/callback")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The sign-in state is invalid.") from exc
    if not secrets.compare_digest(request.cookies.get("jarvis_oauth_nonce", ""), expected_nonce):
        raise HTTPException(status_code=400, detail="The sign-in nonce did not match. Start sign-in again.")
    _safe_origin(request, public_origin, check_header=False)

    api_base = (settings.manus_oauth_api_url or "").rstrip("/")
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        exchange = await client.post(f"{api_base}/webdev.v1.WebDevAuthPublicService/ExchangeToken", json={"clientId": settings.manus_project_id, "grantType": "authorization_code", "code": code, "redirectUri": callback_uri})
        if exchange.is_error:
            raise HTTPException(status_code=502, detail="Manus sign-in could not exchange the authorization code.")
        token_data = exchange.json()
        access_token = token_data.get("accessToken")
        if not access_token:
            raise HTTPException(status_code=502, detail="Manus sign-in returned no access token.")
        identity = await client.post(f"{api_base}/webdev.v1.WebDevAuthPublicService/GetUserInfo", json={"accessToken": access_token})
        if identity.is_error:
            raise HTTPException(status_code=502, detail="Manus sign-in could not confirm your account.")
        user_info = identity.json()

    open_id = user_info.get("openId")
    if not open_id:
        raise HTTPException(status_code=502, detail="Manus sign-in returned no user identity.")
    now = datetime.now(timezone.utc)
    claims = {
        "openId": str(open_id),
        "appId": settings.manus_project_id,
        "authMode": "manus",
        "name": str(user_info.get("name") or "JARVIS user"),
        "email": user_info.get("email"),
        "iat": now,
        "exp": now + timedelta(seconds=settings.jarvis_session_ttl_seconds),
    }
    app_token = jwt.encode(claims, settings.manus_jwt_secret, algorithm="HS256")
    response = RedirectResponse(public_origin + "/", status_code=303)
    response.set_cookie(value=app_token, **session_cookie_options(public_origin))
    secure = public_origin.startswith("https://")
    response.delete_cookie("jarvis_oauth_nonce", path="/api/auth", secure=secure, samesite="none" if secure else "lax")
    return response


@router.post("/logout")
def logout(request: Request, response: Response):
    origin = request.headers.get("origin")
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=bool(origin and origin.startswith("https://")), samesite="none" if origin and origin.startswith("https://") else "lax")
    return {"ok": True}
