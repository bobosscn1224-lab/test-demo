"""Context Builder — unified priority-sorted context assembly.

Replaces the scattered context assembly in chat_service.py with a single,
token-budget-aware pipeline.  Context sources are queried in priority order
and assembled into a Markdown block for injection into the system prompt.

Priority (highest first):
  1. Skill context         — active skill's loaded content (e.g. minutes transcript)
  2. User corrections      — ChromaDB corrections with high similarity match
  3. Episodic memory       — past conversation summaries semantically relevant
  4. Knowledge base (RAG)  — document chunks from watched dirs / Feishu imports
  5. User profile          — learned facts, preferences, expertise
  6. Global rules          — persona-agnostic system-wide behavioural rules
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.session_store import session_store

logger = logging.getLogger(__name__)

# ── token estimation helpers ──────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    """Rough token count: CJK chars ≈ 1 token each, words ≈ 1.3 tokens."""
    cjk = sum(1 for c in text if '一' <= c <= '鿿' or '぀' <= c <= 'ヿ')
    words = len(text.split())
    return cjk + int(words * 1.3)


# ── global rules ──────────────────────────────────────────────────────────
# These are persona-agnostic behavioural rules injected into every prompt.
# Content will be confirmed with the user before finalizing.

DEFAULT_GLOBAL_RULES = """## 全局行为准则

- 所有回答必须基于知识库或用户提供的文档内容，不要编造信息
- 不确定时明确说"不确定"，并提供进一步确认的建议
- 涉及代码时提供可运行的完整示例
- 回答结构清晰，使用适当的标题和列表
- 保护用户隐私，不在回答中暴露敏感信息"""


@dataclass
class ContextSources:
    """All context sources, assembled and prioritized."""
    system_prompt_template: str = ""
    persona_config: dict = field(default_factory=dict)
    skill_context: str = ""
    corrections: str = ""
    episodic_memory: str = ""
    knowledge_base: str = ""
    user_profile: str = ""
    global_rules: str = ""
    mode: str = "enhanced"


class ContextBuilder:
    """Assembles context from all sources with priority-based token budgeting."""

    def __init__(self, token_budget: int = 8000):
        self.token_budget = token_budget

    # ── public API ─────────────────────────────────────────────────────

    async def build(
        self,
        *,
        session_id: str | None = None,
        user_message: str = "",
        persona_system_template: str = "",
        persona_config: dict | None = None,
        knowledge_context: str = "",
        user_profile: str = "",
        mode: str = "enhanced",
    ) -> str:
        """Assemble all context into a single string for system prompt injection.

        Returns a Markdown-formatted string. Does NOT render the persona template —
        that is still done by render_system_prompt / build_system_prompt.
        """
        sources = ContextSources(
            system_prompt_template=persona_system_template,
            persona_config=persona_config or {},
            knowledge_base=knowledge_context,
            user_profile=user_profile,
            mode=mode,
        )

        # Priority 1: active skill context
        sources.skill_context = await self._fetch_skill_context(session_id)

        # Priority 3: episodic memory (relevant past conversations)
        sources.episodic_memory = await self._fetch_episodic_memory(user_message)

        # Priority 6: global rules (lowest priority, trimmed first)
        sources.global_rules = DEFAULT_GLOBAL_RULES

        return self._assemble(sources)

    # ── context fetchers ───────────────────────────────────────────────

    async def _fetch_skill_context(self, session_id: str | None) -> str:
        """Return active skill content as high-priority context."""
        if not session_id:
            return ""

        # Check known skills for loaded content
        skill_names = [
            "feishu_minutes_reader",
            "feishu_doc_reader",
            "weekly_report",
            "ppt_maker",
        ]
        parts: list[str] = []
        for skill_name in skill_names:
            state = await session_store.get(session_id, skill_name)
            if state and state.get("_stage") in ("minutes_loaded", "doc_loaded"):
                title = state.get("title", "")
                url = state.get("url", "")
                content_length = state.get("content_length", 0)
                if title:
                    parts.append(f"**当前已加载{skill_name}内容**：{title}")
                if url:
                    parts.append(f"来源：{url}")
                if content_length:
                    parts.append(f"内容长度：{content_length} 字符")
                parts.append("（完整内容已保存在会话中，可直接基于此内容回答用户问题）")
                break  # Only one active skill at a time
        return "\n".join(parts) if parts else ""

    async def _fetch_episodic_memory(self, user_message: str) -> str:
        """Return semantically relevant past conversation summaries.

        This is a stub — the episodic memory store will be wired in later.
        """
        _ = user_message
        return ""

    # ── assembly ───────────────────────────────────────────────────────

    def _assemble(self, s: ContextSources) -> str:
        """Combine context sources, trimming low-priority ones to fit budget."""
        # Sources in priority order (highest first, trimmed last)
        ordered: list[tuple[str, str]] = [
            ("skill_context", s.skill_context),
            ("corrections", s.corrections),
            ("episodic_memory", s.episodic_memory),
            ("knowledge_base", s.knowledge_base),
            ("user_profile", s.user_profile),
            ("global_rules", s.global_rules),
        ]

        # Calculate total tokens
        total_tokens = sum(_estimate_tokens(text) for _, text in ordered if text)

        # If over budget, trim from lowest priority upward
        while total_tokens > self.token_budget and ordered:
            label, text = ordered.pop()  # remove lowest priority
            removed = _estimate_tokens(text) if text else 0
            total_tokens -= removed
            logger.debug("ContextBuilder: trimmed %s (%d tokens) to fit budget", label, removed)

        # Build Markdown block
        blocks: list[str] = []
        for label, text in ordered:
            if text and text.strip():
                blocks.append(text.strip())

        result = "\n\n".join(blocks)
        used = _estimate_tokens(result)
        logger.debug("ContextBuilder: assembled %d tokens (budget %d)", used, self.token_budget)
        return result


# Module-level singleton
context_builder = ContextBuilder(token_budget=8000)
