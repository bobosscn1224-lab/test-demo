"""SQLAlchemy model for persistent skill session state.

Replaces the in-memory _sessions dict in each skill handler,
surviving uvicorn reloads and server restarts.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SkillSessionState(Base):
    __tablename__ = "skill_session_state"

    session_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Chat session ID"
    )
    skill_name: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Skill name, e.g. feishu_minutes_reader"
    )
    stage: Mapped[str] = mapped_column(
        String(64), default="", comment="Current stage, e.g. minutes_loaded"
    )
    data_json: Mapped[str] = mapped_column(
        Text, default="{}", comment="JSON blob: content, title, url, metadata ..."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
