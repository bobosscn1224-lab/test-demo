"""Self-learning correction engine — validate before learning.

Three-phase pipeline:
  1. DETECT  — catch correction messages via keyword patterns
  2. VALIDATE — cross-reference user claim against knowledge base
  3. ACT     — learn (VALID), reject (INVALID), or defer (UNCERTAIN)

All decisions logged to data/learning_journal.jsonl for audit.
"""
from __future__ import annotations

import json
import os
import re
import time
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.llm_service import llm_service
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

_CORRECTION_HINTS = [
    r"不对", r"错了", r"说错了", r"回答错了",
    r"搞错了", r"弄错了", r"应该是", r"纠正",
    r"校正", r"改正", r"不是.*而是",
]

JOURNAL_PATH = os.path.join("data", "learning_journal.jsonl")


# ── helpers ────────────────────────────────────────────────────────────

def looks_like_correction(message: str) -> bool:
    msg = message.strip()
    if len(msg) > 500:
        return False
    return any(re.search(p, msg) for p in _CORRECTION_HINTS)


def _append_journal(entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
        with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Failed to write learning journal")


def _extract_text(response) -> str:
    text = ""
    if response.content:
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
    return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


# ── main pipeline ──────────────────────────────────────────────────────

async def process_correction(
    message: str, session_id: str, db: AsyncSession
) -> dict | None:
    """Run the three-phase correction pipeline. Returns journal entry or None."""
    if not session_id or not looks_like_correction(message):
        return None

    from app.models.chat import ChatMessage

    # ── Phase 1: DETECT & EXTRACT ──────────────────────────────────
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(8)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    if len(messages) < 2:
        return None

    context_lines = []
    for m in messages[-8:]:
        role = "用户" if m.role == "user" else "助手"
        context_lines.append(f"{role}: {m.content[:300]}")
    context = "\n".join(context_lines)

    extract_prompt = (
        "分析这段对话，判断用户最新消息是否在纠正助手的回答。\n"
        "如果是纠正，提取：被质疑的原始问题、助手原回答、用户声称的正确信息。\n\n"
        f"对话：\n{context}\n\n"
        f"用户最新：{message}\n\n"
        "严格JSON（不要markdown）：\n"
        '纠正：{"is_correction":true,"question":"原问题","original_answer":"助手原回答","user_claim":"用户声称的正确答案"}\n'
        '非纠正：{"is_correction":false}'
    )

    try:
        resp = await llm_service.chat(
            interaction_name="correction_detection",
            system_prompt="你是对话分析助手。严格返回JSON。",
            messages=[{"role": "user", "content": extract_prompt}],
            max_tokens=400,
            temperature=0.1,
        )
        data = json.loads(_extract_text(resp))
    except Exception:
        logger.warning("Correction extraction failed", exc_info=True)
        return None

    if not data.get("is_correction") or not data.get("user_claim"):
        return None

    question = data.get("question", "")
    original = data.get("original_answer", "")
    user_claim = data["user_claim"]

    # ── Phase 2: VALIDATE ──────────────────────────────────────────
    kb_hits = await rag_service.search(question, top_k=3) if question else ""
    corrections = await rag_service.search_corrections(question, top_k=2) if question else ""

    validate_prompt = (
        "判断用户对助手回答的纠正是否正确。\n\n"
        f"原始问题：{question}\n"
        f"助手原回答：{original}\n"
        f"用户声称正确：{user_claim}\n\n"
        f"知识库相关内容：\n{kb_hits[:2000] if kb_hits else '（无相关知识库内容）'}\n\n"
        f"已有纠正记录：\n{corrections[:500] if corrections else '（无）'}\n\n"
        "判断：\n"
        "- VALID：用户说得对，助手原回答有误\n"
        "- INVALID：用户说得不对，助手原回答正确\n"
        "- UNCERTAIN：无法判断，信息不足\n\n"
        "严格JSON：\n"
        '{"verdict":"VALID|INVALID|UNCERTAIN","reasoning":"判断依据（一句话）","final_answer":"最终正确答案"}'
    )

    try:
        resp2 = await llm_service.chat(
            interaction_name="correction_validation",
            system_prompt="你是知识校验专家。基于知识库和逻辑推理判断正误。严格返回JSON。",
            messages=[{"role": "user", "content": validate_prompt}],
            max_tokens=500,
            temperature=0.1,
        )
        verdict_data = json.loads(_extract_text(resp2))
    except Exception:
        logger.warning("Correction validation failed", exc_info=True)
        verdict_data = {"verdict": "UNCERTAIN", "reasoning": "校验异常，保留待审", "final_answer": user_claim}

    verdict = verdict_data.get("verdict", "UNCERTAIN")
    reasoning = verdict_data.get("reasoning", "")
    final_answer = verdict_data.get("final_answer", user_claim)

    # ── Phase 3: ACT ───────────────────────────────────────────────
    journal_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": session_id,
        "question": question,
        "original_answer": original[:500],
        "user_claim": user_claim[:500],
        "verdict": verdict,
        "reasoning": reasoning,
        "final_answer": final_answer[:500],
    }

    if verdict == "VALID":
        await rag_service.add_correction(
            question=question, correct_answer=final_answer, source="chat_validated"
        )
        try:
            from app.services.user_profile_service import UserProfileService
            svc = UserProfileService(db)
            await svc.add_fact(
                fact=f"{question} → {final_answer[:200]}",
                category="other",
                source="user_correction_validated",
                importance=4,
            )
        except Exception:
            pass
        journal_entry["action"] = "learned"
        logger.info("VALID correction — learned: %s", question[:60])

    elif verdict == "INVALID":
        journal_entry["action"] = "rejected"
        logger.info("INVALID correction — rejected: %s", question[:60])

    else:
        await rag_service.add_correction(
            question=question, correct_answer=final_answer, source="chat_uncertain"
        )
        journal_entry["action"] = "pending_review"
        logger.info("UNCERTAIN correction — pending: %s", question[:60])

    _append_journal(journal_entry)
    return journal_entry
