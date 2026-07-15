"""Task Review model — session-level retrospective.

Each completed chat session generates one review capturing:
  intent, scenario, inputs, outputs, quality, feedback, improvements.
"""
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class TaskReview(Base):
    __tablename__ = "task_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="未命名任务")

    # Phase-1 dimensions
    user_intent: Mapped[str] = mapped_column(Text, default="")
    business_scenario: Mapped[str] = mapped_column(Text, default="")
    input_sources: Mapped[str] = mapped_column(Text, default="")   # JSON list
    output_summary: Mapped[str] = mapped_column(Text, default="")
    quality_issues: Mapped[str] = mapped_column(Text, default="")  # JSON list
    user_feedback: Mapped[str] = mapped_column(Text, default="")   # explicit + implicit
    improvement_points: Mapped[str] = mapped_column(Text, default="")  # JSON list

    # Scores
    quality_score: Mapped[float] = mapped_column(Float, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    user_corrections: Mapped[int] = mapped_column(Integer, default=0)  # times user corrected

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
