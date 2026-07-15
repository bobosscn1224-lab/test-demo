"""Context Manager — system-level context orchestration engine.

The single entry point for all context assembly in the digital twin system.
Queries all context sources (skill sessions, knowledge base, user memory,
global rules) and assembles them into a token-budgeted string for the LLM.

Architecture:
  ┌─────────────────────────────────────────────┐
  │              ContextManager                   │
  │  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
  │  │ Skill    │  │ Knowledge│  │ User       │  │
  │  │ Sessions │  │ Base     │  │ Memory     │  │
  │  │(Session  │  │(ChromaDB)│  │(UserProfile│  │
  │  │ Store)   │  │          │  │ +Episodic) │  │
  │  └──────────┘  └──────────┘  └───────────┘  │
  │         ↓            ↓             ↓         │
  │     Priority 1   Priority 2    Priority 3    │
  │         ↓            ↓             ↓         │
  │  ┌──────────────────────────────────────┐    │
  │  │  Token Budget Manager (8000 tokens)  │    │
  │  └──────────────────────────────────────┘    │
  │         ↓                                     │
  │  Assembled system prompt context string       │
  └─────────────────────────────────────────────┘
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.session_store import session_store

logger = logging.getLogger(__name__)


# ── token estimation ─────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough: CJK chars ≈ 1, words ≈ 1.3."""
    if not text:
        return 0
    cjk = sum(1 for c in text if '一' <= c <= '鿿' or '぀' <= c <= 'ヿ')
    words = len(text.split())
    return cjk + int(words * 1.3)


# ── global rules ──────────────────────────────────────────────────────────

def get_global_rules(mode: str = "enhanced") -> str:
    """Return mode-aware global behavioural rules.

    kb_only  — strict: only knowledge base, no external supplementation
    enhanced — flexible: KB-first, may supplement with best practices
    """
    base_rules = """## 全局行为准则

- 不确定时明确说"不确定"，并提供进一步确认的建议
- 涉及代码时提供可运行的完整示例
- 回答结构清晰，使用适当的标题和列表
- 保护用户隐私，不在回答中暴露敏感信息"""

    if mode == "kb_only":
        return base_rules + "\n- **知识库模式**：所有回答必须严格基于知识库或用户提供的文档内容，不要编造或补充任何外部信息"
    else:
        return base_rules + "\n- **增强模式**：以知识库和用户提供的内容为基础，可适当补充业界最佳实践，但不要偏离主题或凭空编造"


@dataclass
class ContextBlock:
    """A single context source with its priority and content."""
    label: str
    content: str
    priority: int  # 1 = highest, 9 = lowest


class ContextManager:
    """System-level context orchestration.

    Usage:
        ctx = await context_manager.gather(
            session_id="...",
            user_message="用户的问题",
            knowledge_context="RAG结果...",
            user_profile="用户画像...",
        )
        # ctx is a Markdown string ready for system prompt injection
    """

    def __init__(self, token_budget: int = 8000):
        self.token_budget = token_budget

    # ── public API ─────────────────────────────────────────────────────

    async def gather(
        self,
        *,
        session_id: str | None = None,
        user_message: str = "",
        knowledge_context: str = "",
        user_profile: str = "",
        mode: str = "enhanced",
        history: list[dict] | None = None,
        perception_result: str = "",  # pre-computed by background task
    ) -> str:
        """Gather all context sources, prioritize, and assemble."""
        blocks: list[ContextBlock] = []

        # P0: Multi-dimensional perception analysis (highest priority)
        if perception_result:
            blocks.append(ContextBlock("perception", perception_result, 0))
        elif user_message:
            # Fallback: run synchronously only if not pre-computed
            perc_ctx = await self._fetch_perception(user_message, history)
            if perc_ctx:
                blocks.append(ContextBlock("perception", perc_ctx, 0))

        # P1: Active skill session (doc/minutes loaded)
        skill_ctx = await self._fetch_skill_context(session_id)
        if skill_ctx:
            blocks.append(ContextBlock("skill", skill_ctx, 1))

        # P2: Knowledge base (RAG results)
        if knowledge_context.strip():
            blocks.append(ContextBlock("knowledge", knowledge_context.strip(), 2))

        # P3: User profile (learned facts, preferences)
        if user_profile.strip():
            blocks.append(ContextBlock("user_profile", user_profile.strip(), 3))

        # P4: Episodic memory — past conversation summaries
        episodic = await self._fetch_episodic(user_message)
        if episodic:
            blocks.append(ContextBlock("episodic", episodic, 4))

        # P5: Global rules (lowest priority, mode-aware)
        blocks.append(ContextBlock("rules", get_global_rules(mode), 5))

        return self._assemble(blocks)

    # ── context fetchers ───────────────────────────────────────────────

    async def _fetch_perception(
        self, user_message: str, history: list[dict] | None
    ) -> str:
        """Run multi-dimensional perception (skip for very short messages)."""
        if len(user_message) < 10:
            return ""
        try:
            import asyncio as _asyncio
            from app.services.perception_engine import perception_engine
            result = await _asyncio.wait_for(
                perception_engine.perceive(user_message, history),
                timeout=3.0,
            )
            return perception_engine.to_context(result)
        except Exception:
            return ""

    async def _fetch_skill_context(self, session_id: str | None) -> str:
        """Query SessionStore for active skill sessions with loaded content."""
        if not session_id:
            return ""

        skill_names = [
            "feishu_minutes_reader",
            "feishu_doc_reader",
            "weekly_report",
            "ppt_maker",
        ]
        for sn in skill_names:
            state = await session_store.get(session_id, sn)
            stage = (state or {}).get("_stage", "")
            if stage in ("minutes_loaded", "doc_loaded"):
                title = state.get("title", "")
                url = state.get("url", "")
                return (
                    f"## 当前已加载的文档/妙记\n"
                    f"**{title}**\n来源：{url}\n"
                    f"内容已加载到会话中，请严格基于该内容回答用户问题。\n"
                    f"如果用户的问题与该文档/妙记无关，正常回答即可。"
                )
        return ""

    async def _fetch_episodic(self, user_message: str) -> str:
        """Semantically relevant past conversation summaries."""
        try:
            from app.services.episodic_memory import episodic_memory
            return await episodic_memory.search(user_message, top_k=3)
        except Exception:
            return ""

    # ── assembly ───────────────────────────────────────────────────────

    def _assemble(self, blocks: list[ContextBlock]) -> str:
        """Combine blocks by priority, trimming low-priority ones to fit budget."""
        blocks.sort(key=lambda b: b.priority)

        # Track token usage
        used = 0
        included: list[ContextBlock] = []

        for b in blocks:
            t = estimate_tokens(b.content)
            if used + t <= self.token_budget:
                included.append(b)
                used += t
            else:
                # Try to trim this block
                available = self.token_budget - used
                if available > 200:
                    trimmed = self._trim(b.content, available)
                    if trimmed:
                        included.append(ContextBlock(b.label, trimmed, b.priority))
                        used += estimate_tokens(trimmed)
                logger.debug("ContextManager: trimmed %s (would use %d tokens)", b.label, t)
                break

        result = "\n\n".join(b.content for b in included)
        logger.debug("ContextManager: assembled %d tokens from %d blocks", used, len(included))
        return result

    @staticmethod
    def _trim(text: str, max_tokens: int) -> str:
        """Truncate text to fit max_tokens, keeping whole sentences."""
        if estimate_tokens(text) <= max_tokens:
            return text
        sentences = text.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")
        result = ""
        for s in sentences:
            candidate = result + s
            if estimate_tokens(candidate) > max_tokens:
                break
            result = candidate
        return result.strip()


# Module-level singleton
context_manager = ContextManager(token_budget=8000)
