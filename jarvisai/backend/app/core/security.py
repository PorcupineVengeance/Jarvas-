from urllib.parse import urlsplit
import jwt
from fastapi import HTTPException, Request, status
from app.core.config import get_settings

SESSION_COOKIE = "webdev_app_session"
PROJECT_PREVIEW_ORIGIN = "https://8328-i62x16wr5z34nndf3511k-d6ab6cbe.us3.manus.computer"
LOCAL_ORIGINS = {"http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"}


def _normalize_origin(origin: str) -> str | None:
    if any(character in origin for character in "\r\n\t "):
        return None
    try:
        parts = urlsplit(origin.rstrip("/"))
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
            return None
        scheme = parts.scheme.lower()
        hostname = parts.hostname.lower()
        port = parts.port
    except ValueError:
        return None
    default_port = (scheme == "https" and port == 443) or (scheme == "http" and port == 80)
    return f"{scheme}://{hostname}{f':{port}' if port and not default_port else ''}"


def allowed_origins() -> set[str]:
    configured = {value for item in get_settings().jarvis_allowed_origins.split(",") if (value := _normalize_origin(item.strip()))}
    return configured | LOCAL_ORIGINS | {PROJECT_PREVIEW_ORIGIN}


def _forwarded_origins(request: Request) -> set[str]:
    hosts = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",", 1)[0].strip().lower()
    if proto not in {"http", "https"}:
        return set()
    trusted: set[str] = set()
    for host in hosts.split(","):
        candidate = _normalize_origin(f"{proto}://{host.strip()}")
        if candidate:
            trusted.add(candidate)
    return trusted


def is_allowed_request_origin(request: Request, origin: str) -> bool:
    normalized = _normalize_origin(origin)
    if not normalized:
        return False
    return normalized in allowed_origins() or normalized in _forwarded_origins(request)


def is_allowed_origin(origin: str) -> bool:
    normalized = _normalize_origin(origin)
    return bool(normalized and normalized in allowed_origins())


def decode_session(token: str) -> dict:
    settings = get_settings()
    secret = settings.session_signing_secret
    if not secret or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is not configured.")
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp"]})
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is invalid or expired.") from exc
    if not claims.get("openId"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is not valid for this application.")
    auth_mode = claims.get("authMode", "manus")
    if auth_mode == "manus":
        if not settings.oauth_ready or claims.get("appId") != settings.manus_project_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is not valid for this application.")
    elif auth_mode == "local":
        if not settings.local_auth_ready and not settings.jarvis_open_access:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Local authentication is disabled.")
    elif auth_mode == "open":
        if not settings.jarvis_open_access:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Open access is disabled.")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session is not valid for this application.")
    return claims


def session_cookie_options(public_origin: str | None) -> dict:
    is_https = bool(public_origin and public_origin.lower().startswith("https://"))
    return {"key": SESSION_COOKIE, "httponly": True, "secure": is_https, "samesite": "none" if is_https else "lax", "path": "/", "max_age": get_settings().jarvis_session_ttl_seconds}


def request_origin_is_trusted(request: Request) -> bool:
    origin = request.headers.get("origin")
    return bool(origin and is_allowed_request_origin(request, origin))
