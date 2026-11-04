from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Memory


def recent_memories(db: Session, owner_id: str, limit: int = 8) -> list[Memory]:
    return list(db.scalars(select(Memory).where(Memory.owner_id == owner_id).order_by(Memory.updated_at.desc()).limit(limit)).all())


def search_memories(db: Session, owner_id: str, query: str, limit: int = 20) -> list[Memory]:
    return list(
        db.scalars(
            select(Memory)
            .where(Memory.owner_id == owner_id, Memory.content.ilike(f"%{query}%"))
            .order_by(Memory.updated_at.desc())
            .limit(limit)
        ).all()
    )
