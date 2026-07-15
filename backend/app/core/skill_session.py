"""Shared skill session persistence — one helper for all skills.

Each skill keeps an in-memory _sessions cache for fast sync access (can_handle).
All writes are dual-routed to SQLite via SessionStore for persistence across reloads.

Usage (in any skill handler):

    from app.core.skill_session import SkillSessionHelper

    SKILL_NAME = "my_skill"
    _sessions: dict[str, dict] = {}
    _helper = SkillSessionHelper(SKILL_NAME, _sessions)

    # In can_handle (sync):
    if any(s.get("stage") == "loaded" for s in _sessions.values()):
        return True

    # In execute (async):
    await _helper.restore()
    await _helper.save(sid, {"stage": "loaded", "title": "...", "content": "..."})
    await _helper.delete(sid)
"""
from __future__ import annotations

import logging

from app.core.session_store import session_store

logger = logging.getLogger(__name__)


class SkillSessionHelper:
    """Manages the dual-layer (memory + SQLite) session state for one skill."""

    def __init__(self, skill_name: str, cache: dict[str, dict]):
        self.skill_name = skill_name
        self.cache = cache

    async def restore(self) -> int:
        """Load active sessions from DB into the memory cache. Returns count.

        Finds ALL sessions for this skill, regardless of stage.
        Safe to call before routing — won't overwrite existing in-memory sessions.
        """
        try:
            # Find all sessions for this skill (any stage, limit 50)
            active = await session_store.find_all(self.skill_name, limit=50)
            count = 0
            for s in active:
                sid = s.pop("_session_id", "")
                stage = s.pop("_stage", None)
                s.pop("_updated_at", None)
                if sid and sid not in self.cache:
                    self.cache[sid] = s
                    count += 1
            if count:
                logger.info("SkillSession(%s): restored %d sessions from DB", self.skill_name, count)
            return count
        except Exception as exc:
            logger.warning("SkillSession(%s).restore failed: %s", self.skill_name, exc)
            return 0

    async def save(self, session_id: str, data: dict) -> None:
        """Write to memory + DB."""
        stage = data.get("stage", "")
        self.cache[session_id] = data
        db_data = {k: v for k, v in data.items() if k != "content"}
        db_data["content_length"] = len(data.get("content") or "")
        try:
            await session_store.set(session_id, self.skill_name, stage, db_data)
        except Exception as exc:
            logger.warning("SkillSession(%s).save failed: %s", self.skill_name, exc)

    async def delete(self, session_id: str) -> None:
        """Remove from memory + DB."""
        self.cache.pop(session_id, None)
        try:
            await session_store.delete(session_id, self.skill_name)
        except Exception as exc:
            logger.warning("SkillSession(%s).delete failed: %s", self.skill_name, exc)

    def has_active(self, stage: str | None = None) -> bool:
        """Check if any session is in the given stage (sync, for can_handle)."""
        if stage:
            return any(s.get("stage") == stage for s in self.cache.values())
        return bool(self.cache)
