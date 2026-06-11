import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class SkillExecution(Base):
    __tablename__ = "skill_executions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    skill_name: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=True)
    trigger_message: Mapped[str] = mapped_column(Text, default="")
    result_data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="success")  # success / error
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
