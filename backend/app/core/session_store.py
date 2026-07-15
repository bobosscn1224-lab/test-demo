"""Persistent session store for skill state machines.

Usage (inside a skill handler):
    from app.core.session_store import session_store

    # Read
    state = await session_store.get(session_id, "feishu_minutes_reader")
    if state:
        content = state.get("content")

    # Write
    await session_store.set(session_id, "feishu_minutes_reader",
                            stage="minutes_loaded",
                            data={"content": "...", "title": "...", "url": "..."})

    # Delete
    await session_store.delete(session_id, "feishu_minutes_reader")

    # Find active sessions by stage
    active = await session_store.find_by_stage("feishu_minutes_reader", "minutes_loaded")
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select, delete as sql_delete
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from app.core.database import async_session
from app.models.skill_state import SkillSessionState

logger = logging.getLogger(__name__)


class SessionStore:
    """Async persistent store for skill multi-turn session state."""

    # ── single-key operations ─────────────────────────────────────────

    async def get(self, session_id: str, skill_name: str) -> dict | None:
        """Return stored data dict, or None."""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(SkillSessionState).where(
                        SkillSessionState.session_id == session_id,
                        SkillSessionState.skill_name == skill_name,
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                data = json.loads(row.data_json) if row.data_json else {}
                data["_stage"] = row.stage
                data["_updated_at"] = row.updated_at.isoformat()
                return data
        except Exception as exc:
            logger.warning(f"SessionStore.get({session_id}, {skill_name}) failed: {exc}")
            return None

    async def set(
        self, session_id: str, skill_name: str, stage: str, data: dict | None = None
    ) -> None:
        """Upsert session state."""
        data_json = json.dumps(data or {}, ensure_ascii=False)
        try:
            async with async_session() as db:
                # SQLite-compatible upsert
                stmt = sqlite_upsert(SkillSessionState).values(
                    session_id=session_id,
                    skill_name=skill_name,
                    stage=stage,
                    data_json=data_json,
                    updated_at=datetime.utcnow(),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["session_id", "skill_name"],
                    set_=dict(stage=stmt.excluded.stage,
                              data_json=stmt.excluded.data_json,
                              updated_at=stmt.excluded.updated_at),
                )
                await db.execute(stmt)
                await db.commit()
        except Exception as exc:
            logger.warning(f"SessionStore.set({session_id}, {skill_name}) failed: {exc}")

    async def delete(self, session_id: str, skill_name: str) -> None:
        """Remove session state for a skill."""
        try:
            async with async_session() as db:
                await db.execute(
                    sql_delete(SkillSessionState).where(
                        SkillSessionState.session_id == session_id,
                        SkillSessionState.skill_name == skill_name,
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.warning(f"SessionStore.delete({session_id}, {skill_name}) failed: {exc}")

    # ── query operations ──────────────────────────────────────────────

    async def find_by_stage(self, skill_name: str, stage: str) -> list[dict]:
        """Return all sessions for a skill in a given stage."""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(SkillSessionState).where(
                        SkillSessionState.skill_name == skill_name,
                        SkillSessionState.stage == stage,
                    ).order_by(SkillSessionState.updated_at.desc())
                )
                rows = result.scalars().all()
                out: list[dict] = []
                for row in rows:
                    data = json.loads(row.data_json) if row.data_json else {}
                    data["_session_id"] = row.session_id
                    data["_stage"] = row.stage
                    out.append(data)
                return out
        except Exception as exc:
            logger.warning(f"SessionStore.find_by_stage({skill_name}, {stage}) failed: {exc}")
            return []

    async def find_all(self, skill_name: str, limit: int = 50) -> list[dict]:
        """Return all sessions for a skill, regardless of stage. Most recent first."""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(SkillSessionState).where(
                        SkillSessionState.skill_name == skill_name,
                    ).order_by(SkillSessionState.updated_at.desc()).limit(limit)
                )
                rows = result.scalars().all()
                out: list[dict] = []
                for row in rows:
                    data = json.loads(row.data_json) if row.data_json else {}
                    data["_session_id"] = row.session_id
                    data["_stage"] = row.stage
                    out.append(data)
                return out
        except Exception as exc:
            logger.warning(f"SessionStore.find_all({skill_name}) failed: {exc}")
            return []

    async def find_active_session_id(self, skill_name: str, stage: str) -> str | None:
        """Return the most recent session_id for a skill in a given stage."""
        sessions = await self.find_by_stage(skill_name, stage)
        if sessions:
            return sessions[0].get("_session_id")
        return None

    async def clear_skill(self, skill_name: str) -> None:
        """Delete all sessions for a given skill."""
        try:
            async with async_session() as db:
                await db.execute(
                    sql_delete(SkillSessionState).where(
                        SkillSessionState.skill_name == skill_name
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.warning(f"SessionStore.clear_skill({skill_name}) failed: {exc}")


# Module-level singleton
session_store = SessionStore()
