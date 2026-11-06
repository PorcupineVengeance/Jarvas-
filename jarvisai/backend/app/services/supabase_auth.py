"""Supabase Auth (email/password) via the public Auth REST API."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


class SupabaseAuthError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _headers(*, admin: bool = False) -> dict[str, str]:
    settings = get_settings()
    key = settings.supabase_service_role_key if admin and settings.supabase_service_role_key else settings.supabase_anon_key
    if not settings.supabase_url or not key:
        raise SupabaseAuthError("Supabase Auth is not configured.", status_code=503)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    settings = get_settings()
    return (settings.supabase_url or "").rstrip("/")


def _user_from_payload(data: dict[str, Any], fallback_name: str = "") -> dict[str, str | None]:
    user = data.get("user") if isinstance(data.get("user"), dict) else data
    if not isinstance(user, dict):
        raise SupabaseAuthError("Supabase returned an unexpected user payload.")
    user_id = user.get("id")
    if not user_id:
        raise SupabaseAuthError("Supabase did not return a user id.")
    meta = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    name = (
        str(meta.get("full_name") or meta.get("name") or fallback_name or user.get("email") or "JARVIS user")
    ).strip()[:120] or "JARVIS user"
    email = user.get("email")
    return {
        "id": f"supabase:{user_id}",
        "supabase_id": str(user_id),
        "name": name,
        "email": str(email) if email else None,
    }


async def signup(name: str, email: str, password: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_auth_ready:
        raise SupabaseAuthError("Supabase Auth is not configured.", status_code=503)
    payload = {
        "email": email.strip().lower(),
        "password": password,
        "data": {"full_name": name.strip(), "name": name.strip()},
    }
    # Service role can create + confirm in one step for smoother personal deploys.
    use_admin = bool(settings.supabase_service_role_key)
    url = f"{_base()}/auth/v1/admin/users" if use_admin else f"{_base()}/auth/v1/signup"
    if use_admin:
        payload = {
            "email": email.strip().lower(),
            "password": password,
            "email_confirm": True,
            "user_metadata": {"full_name": name.strip(), "name": name.strip()},
        }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=6.0)) as client:
            response = await client.post(url, headers=_headers(admin=use_admin), json=payload)
    except httpx.HTTPError as exc:
        raise SupabaseAuthError("Could not reach Supabase Auth.", status_code=502) from exc

    if response.status_code >= 400:
        detail = "Sign-up failed."
        try:
            body = response.json()
            detail = str(body.get("msg") or body.get("error_description") or body.get("message") or detail)
        except Exception:
            pass
        raise SupabaseAuthError(detail, status_code=400 if response.status_code < 500 else 502)

    data = response.json() if response.content else {}
    if not isinstance(data, dict):
        raise SupabaseAuthError("Supabase returned an invalid sign-up response.")

    # Public signup may require email confirmation (no session yet).
    if not use_admin and not data.get("access_token") and data.get("user"):
        user = _user_from_payload(data, fallback_name=name)
        return {
            "needs_confirmation": True,
            "user": user,
            "message": "Account created. Confirm your email, then sign in.",
        }

    # Admin create does not return a session — sign in immediately.
    if use_admin:
        return await login(email, password)

    if not data.get("access_token"):
        raise SupabaseAuthError("Sign-up succeeded but no session was returned. Confirm your email, then sign in.")
    user = _user_from_payload(data, fallback_name=name)
    return {"needs_confirmation": False, "user": user, "message": "Signed up."}


async def login(email: str, password: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_auth_ready:
        raise SupabaseAuthError("Supabase Auth is not configured.", status_code=503)
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=6.0)) as client:
            response = await client.post(
                f"{_base()}/auth/v1/token?grant_type=password",
                headers=_headers(),
                json={"email": email.strip().lower(), "password": password},
            )
    except httpx.HTTPError as exc:
        raise SupabaseAuthError("Could not reach Supabase Auth.", status_code=502) from exc

    if response.status_code >= 400:
        detail = "Invalid email or password."
        try:
            body = response.json()
            detail = str(body.get("msg") or body.get("error_description") or body.get("message") or detail)
        except Exception:
            pass
        raise SupabaseAuthError(detail, status_code=401 if response.status_code in {400, 401} else 502)

    data = response.json()
    if not isinstance(data, dict) or not data.get("access_token"):
        raise SupabaseAuthError("Supabase did not return a session.")
    user = _user_from_payload(data)
    return {"needs_confirmation": False, "user": user, "message": "Signed in."}
