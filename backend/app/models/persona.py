import uuid
from datetime import datetime
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    voice_id: Mapped[str] = mapped_column(String(100), default="zh-CN-YunxiNeural")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    system_prompt_template: Mapped[str] = mapped_column(Text, default="")
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
