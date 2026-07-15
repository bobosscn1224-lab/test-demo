"""Session cleanup — periodically remove stale/abandoned skill sessions.

Run via the skill system's on_startup or as a FastAPI background task.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

# Sessions older than this (seconds) are considered abandoned
DEFAULT_SESSION_TTL = 3600 * 24  # 24 hours


async def cleanup_stale_sessions(skills_registry, ttl: int = DEFAULT_SESSION_TTL) -> int:
    """Remove sessions older than TTL from all registered skills. Returns count removed."""
    removed = 0
    now = time.time()
    cutoff = now - ttl

    for skill in skills_registry:
        try:
            # Try the standardized cleanup_sessions method first
            if hasattr(skill, "cleanup_sessions"):
                count = skill.cleanup_sessions()
                removed += count
                if count:
                    logger.info("Skill %s: cleaned up %d stale sessions", skill.name, count)
        except Exception as exc:
            logger.warning("Session cleanup failed for skill %s: %s", skill.name, exc)

    # Note: DB-level session cleanup is handled by the session_store's
    # own TTL mechanism. Skill-level cleanup is sufficient here.

    return removed


async def periodic_cleanup(skills_registry, interval: int = 3600, ttl: int = DEFAULT_SESSION_TTL):
    """Background task: run cleanup every `interval` seconds."""
    while True:
        await asyncio.sleep(interval)
        try:
            removed = await cleanup_stale_sessions(skills_registry, ttl)
            if removed:
                logger.info("Periodic cleanup: removed %d stale sessions", removed)
        except Exception as exc:
            logger.warning("Periodic cleanup error: %s", exc)
