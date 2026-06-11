import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(200), default="新对话")
    persona_id: Mapped[str] = mapped_column(String(36), ForeignKey("personas.id"), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, default="")
    audio_path: Mapped[str] = mapped_column(String(500), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
