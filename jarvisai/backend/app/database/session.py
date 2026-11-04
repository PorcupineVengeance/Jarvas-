from functools import lru_cache
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import get_settings


def normalize_database_url(url: str) -> str:
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+pymysql://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+" not in url.split(":", 1)[0]:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def build_engine(url: str | None = None) -> Engine:
    database_url = normalize_database_url(url or get_settings().resolved_database_url)
    engine_options: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite:"):
        raw_path = database_url.removeprefix("sqlite:///")
        if raw_path.startswith("./") or raw_path.startswith("tmp/") or raw_path.startswith("/"):
            path = Path(raw_path)
            if not path.is_absolute():
                path = Path.cwd() / path
            path.parent.mkdir(parents=True, exist_ok=True)
        engine_options["connect_args"] = {"check_same_thread": False, "timeout": 15}
    return create_engine(database_url, **engine_options)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return build_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
