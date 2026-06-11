from datetime import datetime
from sqlalchemy import String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: "default")
    basic_info: Mapped[dict] = mapped_column(JSON, default=dict)       # {name, role, company, ...}
    expertise: Mapped[list] = mapped_column(JSON, default=list)        # ["流程管理", "LTC", ...]
    projects: Mapped[list] = mapped_column(JSON, default=list)         # [{name, description, status}, ...]
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)      # {language, tone, ...}
    learned_facts: Mapped[list] = mapped_column(JSON, default=list)    # [{fact, category, source, learned_at}, ...]
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
