"""Task Review Service — generates and stores session retrospectives.

Auto-triggered after a chat session ends.  Uses LLM to analyze the full
conversation and extract structured insights for continuous improvement.

Aligns with: Mechanism 1 (任务复盘) + Learning Layer (学习层)
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.chat import ChatMessage, ChatSession
from app.models.task_review import TaskReview
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ReviewService:
    """Generates task reviews from completed chat sessions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── public API ────────────────────────────────────────────────────

    async def generate(self, session_id: str) -> TaskReview | None:
        """Generate a task review for a completed chat session."""
        # Load session
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            return None

        # Load messages
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        messages = list(result.scalars().all())
        if len(messages) < 2:
            return None  # too short to review

        # Count user corrections
        correction_count = sum(
            1 for m in messages
            if m.role == "user" and _looks_like_correction(m.content)
        )

        # Format conversation for LLM
        transcript = []
        for m in messages[-30:]:  # last 30 messages
            role = "用户" if m.role == "user" else "助手"
            transcript.append(f"{role}: {m.content[:400]}")
        transcript_text = "\n".join(transcript)

        # Generate review via LLM
        review_data = await self._llm_review(transcript_text)
        if not review_data:
            return None

        # Save
        review = TaskReview(
            id=str(uuid.uuid4()),
            session_id=session_id,
            title=session.title or "未命名对话",
            user_intent=review_data.get("user_intent", ""),
            business_scenario=review_data.get("business_scenario", ""),
            input_sources=json.dumps(review_data.get("input_sources", []), ensure_ascii=False),
            output_summary=review_data.get("output_summary", ""),
            quality_issues=json.dumps(review_data.get("quality_issues", []), ensure_ascii=False),
            user_feedback=review_data.get("user_feedback", ""),
            improvement_points=json.dumps(review_data.get("improvement_points", []), ensure_ascii=False),
            quality_score=review_data.get("quality_score"),
            message_count=len(messages),
            user_corrections=correction_count,
        )
        self.db.add(review)
        await self.db.commit()
        logger.info("Task review generated for session %s (score: %s)", session_id, review_data.get("quality_score"))
        return review

    async def get_by_session(self, session_id: str) -> TaskReview | None:
        result = await self.db.execute(
            select(TaskReview).where(TaskReview.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 20) -> list[TaskReview]:
        result = await self.db.execute(
            select(TaskReview)
            .order_by(TaskReview.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── LLM review generation ────────────────────────────────────────

    async def _llm_review(self, transcript: str) -> dict | None:
        prompt = (
            "你是一个任务复盘专家。请对以下对话进行分析，提取结构化复盘信息。\n\n"
            "## 对话内容\n"
            f"{transcript[:8000]}\n\n"
            "## 请按以下维度分析（返回严格JSON，不要markdown）：\n\n"
            "1. user_intent（用户意图）：用户真正想解决什么问题？\n"
            "2. business_scenario（业务场景）：属于哪个流程、岗位或业务阶段？\n"
            "3. input_sources（输入资料）：使用了哪些文档、知识、数据？（字符串数组）\n"
            "4. output_summary（输出摘要）：产出了什么内容或结论？（200字内）\n"
            "5. quality_issues（质量问题）：存在哪些遗漏、错误或不足？（字符串数组）\n"
            "6. user_feedback（用户反馈）：用户是否修改、否定或补充了结果？\n"
            "7. improvement_points（改进点）：下次类似任务应如何优化？（字符串数组）\n"
            "8. quality_score（质量评分）：1-5分\n\n"
            '格式：{"user_intent":"...","business_scenario":"...","input_sources":[...],'
            '"output_summary":"...","quality_issues":[...],"user_feedback":"...",'
            '"improvement_points":[...],"quality_score":3}'
        )
        try:
            resp = await llm_service.chat(
                system_prompt="你是任务复盘专家。严格返回JSON格式。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.2,
                thinking={"type": "disabled"},
            )
            text = ""
            if resp.content:
                for block in resp.content:
                    if hasattr(block, "text"):
                        text += block.text
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except Exception as exc:
            logger.warning("Task review generation failed: %s", exc)
            return None


def _looks_like_correction(msg: str) -> bool:
    """Quick check if message contains correction patterns."""
    import re
    hints = [r"不对", r"错了", r"应该是", r"纠正", r"不是.*而是"]
    return len(msg) < 500 and any(re.search(p, msg) for p in hints)


# Module-level factory
def create_review_service(db: AsyncSession) -> ReviewService:
    return ReviewService(db)
