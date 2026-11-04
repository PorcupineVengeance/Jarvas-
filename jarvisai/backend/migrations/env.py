from alembic import context
from app.core.config import get_settings
from app.database.base import Base
from app.database.session import build_engine, normalize_database_url
import app.models  # noqa: F401 — register model metadata

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = normalize_database_url(get_settings().database_url or "sqlite:///./data/jarvis.db")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = build_engine()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
