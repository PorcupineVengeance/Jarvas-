from datetime import datetime, timezone
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "jarvis_users"

    open_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), default="JARVIS user")
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Conversation(Base):
    __tablename__ = "jarvis_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("jarvis_users.open_id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "jarvis_messages"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_jarvis_messages_user_client_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("jarvis_conversations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("jarvis_users.open_id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Task(Base):
    __tablename__ = "jarvis_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("jarvis_users.open_id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Memory(Base):
    __tablename__ = "jarvis_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("jarvis_users.open_id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64), default="note")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class StoredFile(Base):
    __tablename__ = "jarvis_stored_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("jarvis_users.open_id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_type: Mapped[str] = mapped_column(String(160))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolExecution(Base):
    __tablename__ = "jarvis_tool_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("jarvis_users.open_id", ondelete="CASCADE"), index=True)
    tool_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(String(240), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
