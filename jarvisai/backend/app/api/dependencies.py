from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.database.session import get_db
from app.models import User
from app.core.security import SESSION_COOKIE, decode_session

OPEN_ACCESS_USER_ID = "local-operator"


def _ensure_user(db: Session, open_id: str, display_name: str, email: str | None = None) -> User:
    user = db.get(User, open_id)
    if user is None:
        user = User(open_id=open_id, display_name=display_name, email=email)
        db.add(user)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="User storage is temporarily unavailable.") from exc
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    settings = get_settings()
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            claims = decode_session(token)
            open_id = str(claims["openId"])
            return _ensure_user(
                db,
                open_id,
                str(claims.get("name") or settings.jarvis_local_auth_display_name or "Operator"),
                claims.get("email"),
            )
        except HTTPException:
            if not settings.jarvis_open_access:
                raise
    if settings.jarvis_open_access:
        return _ensure_user(db, OPEN_ACCESS_USER_ID, settings.jarvis_local_auth_display_name or "Operator")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to use JARVIS.")
