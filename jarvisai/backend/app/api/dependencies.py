from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models import User
from app.core.security import SESSION_COOKIE, decode_session


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to use JARVIS.")
    claims = decode_session(token)
    open_id = str(claims["openId"])
    user = db.get(User, open_id)
    if user is None:
        user = User(open_id=open_id, display_name=str(claims.get("name") or "JARVIS user"), email=claims.get("email"))
        db.add(user)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="User storage is temporarily unavailable.") from exc
    return user
