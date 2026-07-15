"""Base skill classes — unified interface for all skills in the system.

Skill lifecycle:
  1. __init__() — registration
  2. can_handle(message) — sync check, called on every user message
  3. execute(context) — main async entry point
  4. execute_stream(context) — optional streaming variant (async generator)
  5. cleanup() — optional cleanup on shutdown
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Union

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SkillContext:
    """Context passed to a skill on execution."""
    db: AsyncSession
    user_message: str
    persona_slug: str | None = None
    session_id: str | None = None
    uploaded_files: list[dict] = field(default_factory=list)  # [{filename, path, content_type}]
    extra: dict = field(default_factory=dict)


@dataclass
class SkillResult:
    """Result returned by a skill execution."""
    success: bool
    message: str                     # Text response to show user
    data: dict = field(default_factory=dict)  # Additional data (file paths, download URLs, etc.)
    follow_up_action: str | None = None  # "download", "redirect", None


# Type for streaming: yield either SkillResult or progress strings
StreamEvent = Union[SkillResult, str]


class BaseSkill:
    """Base class for all skills.

    Subclasses must set:
      - name: unique skill identifier
      - description: human-readable description
      - triggers: list of exact trigger phrases
      - keywords: list of broader matching keywords
    """

    name: str = ""
    description: str = ""
    triggers: list[str] = []         # ["写周报", "周报"]
    keywords: list[str] = []         # ["周报", "weekly", "report"]

    # ── Trigger matching ─────────────────────────────────────────────

    def can_handle(self, message: str) -> bool:
        """Check if this skill can handle the given message.

        Default: substring match against triggers and keywords.
        Override for more complex logic (URL detection, session state, etc.).
        """
        msg_lower = message.lower()
        for trigger in self.triggers:
            if trigger.lower() in msg_lower:
                return True
        for kw in self.keywords:
            if kw.lower() in msg_lower:
                return True
        return False

    def match_score(self, message: str) -> int:
        """Return a match score for priority-based routing (higher = better match).

        Default scoring:
          - Exact trigger match: 100
          - Trigger substring: 50
          - Keyword match: 25
          - No match: 0

        Override for custom priority logic.
        """
        msg_lower = message.lower().strip()
        score = 0
        for trigger in self.triggers:
            t_lower = trigger.lower()
            if msg_lower == t_lower:
                score = max(score, 100)
            elif t_lower in msg_lower:
                score = max(score, 50)
        for kw in self.keywords:
            if kw.lower() in msg_lower:
                score = max(score, 25)
        return score

    # ── Execution ────────────────────────────────────────────────────

    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the skill. Must be overridden by subclasses."""
        raise NotImplementedError(f"{self.name}: execute() not implemented")

    async def execute_stream(self, context: SkillContext) -> AsyncGenerator[StreamEvent, None]:
        """Streaming variant of execute(). Yields progress strings and a final SkillResult.

        Default implementation falls back to execute() — yields the result in one shot.
        Override for real streaming behavior.
        """
        result = await self.execute(context)
        yield result

    # ── Lifecycle ────────────────────────────────────────────────────

    async def on_startup(self) -> None:
        """Called when the skill system starts up. Restore sessions, etc."""
        pass

    async def on_shutdown(self) -> None:
        """Called when the skill system shuts down. Clean up resources."""
        pass

    def cleanup_sessions(self) -> int:
        """Remove expired/abandoned sessions. Return count of removed sessions.
        Override in skills that manage sessions.
        """
        return 0

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def extract_text_from_llm_response(response) -> str:
        """Extract plain text from an LLM response object.

        Handles the common pattern of iterating response.content blocks.
        """
        text = ""
        if not response or not response.content:
            return text
        for block in response.content:
            block_type = getattr(block, "type", "unknown")
            if hasattr(block, "text") and block.text:
                text += block.text
            elif block_type in ("thinking", "redacted_thinking"):
                # Skip thinking blocks — they're internal reasoning
                continue
        return text.strip()
