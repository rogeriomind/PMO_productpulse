import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Generator

from sqlalchemy import (
    CHAR,
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.config import get_settings


class GUID(TypeDecorator[str]):
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=False))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(value)


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ConversationRecord(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_chat_id", name="uq_conversation_provider_chat"
        ),
    )

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_chat_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_user_id: Mapped[str | None] = mapped_column(String(255))
    provider_user_name: Mapped[str | None] = mapped_column(String(255))
    provider_username: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    messages: Mapped[list["MessageRecord"]] = relationship(
        back_populates="conversation"
    )


class MessageRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_message_id", name="uq_message_provider_message"
        ),
        UniqueConstraint("event_id", name="uq_messages_event_id"),
    )

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("conversations.id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    provider_update_id: Mapped[str | None] = mapped_column(String(255))
    event_id: Mapped[str | None] = mapped_column(String(255))
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown"
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    callback_query_id: Mapped[str | None] = mapped_column(String(255))
    callback_data: Mapped[str | None] = mapped_column(Text)
    media_file_id: Mapped[str | None] = mapped_column(String(255))
    media_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    conversation: Mapped[ConversationRecord] = relationship(back_populates="messages")


class QueueRecord(Base):
    __tablename__ = "message_queue"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    message_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("messages.id"), nullable=False
    )
    conversation_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("conversations.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    message: Mapped[MessageRecord] = relationship()


class DebounceBufferRecord(Base):
    __tablename__ = "debounce_buffers"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("conversations.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    combined_text: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class TaskActionRecord(Base):
    __tablename__ = "task_actions"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("conversations.id"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(String(255))
    intent: Mapped[str] = mapped_column(String(100), nullable=False)
    action_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_confirmation"
    )
    confirmation_token: Mapped[str | None] = mapped_column(String(100))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime)
    result_payload: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class AgentDispatchRecord(Base):
    __tablename__ = "agent_dispatches"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_agent_dispatches_event_id"),
    )

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    conversation_id: Mapped[str] = mapped_column(
        GUID(), ForeignKey("conversations.id"), nullable=False
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_message_ids: Mapped[list | None] = mapped_column(JSON)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    agent_called_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(GUID(), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str | None] = mapped_column(GUID())
    message_id: Mapped[str | None] = mapped_column(GUID())
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


settings = get_settings()
engine = create_engine(
    normalize_database_url(settings.database_url), pool_pre_ping=True
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_sqlite_memory_session() -> Session:
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    return factory()
