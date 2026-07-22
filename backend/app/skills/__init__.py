from __future__ import annotations
from app.skills.base import BaseSkill, SkillContext, SkillResult

_registry: list[BaseSkill] = []


def register(skill: BaseSkill):
    _registry.append(skill)


def get_all() -> list[BaseSkill]:
    return list(_registry)


def get_registry() -> list[BaseSkill]:
    """Return the raw registry for lifecycle management (cleanup, etc.)."""
    return _registry


def find_skill(message: str) -> BaseSkill | None:
    """Find the best matching skill for a message. Uses first-match (by registration order)."""
    best_skill = None
    best_score = 0
    for skill in _registry:
        score = skill.match_score(message)
        if score > best_score:
            best_score = score
            best_skill = skill
    # Fall back to can_handle if no score-based match found
    if not best_skill:
        for skill in _registry:
            if skill.can_handle(message):
                return skill
    return best_skill


def find_skill_by_name(name: str) -> BaseSkill | None:
    for skill in _registry:
        if skill.name == name:
            return skill
    return None


async def on_startup():
    """Initialize all skills on application startup."""
    for skill in _registry:
        try:
            await skill.on_startup()
        except Exception:
            pass


async def on_shutdown():
    """Clean up all skills on application shutdown."""
    for skill in _registry:
        try:
            await skill.on_shutdown()
        except Exception:
            pass


async def cleanup_stale_sessions() -> int:
    """Remove stale sessions from all registered skills."""
    from app.skills.session_cleanup import cleanup_stale_sessions as _cleanup
    return await _cleanup(_registry)


# Import skills to trigger registration
from app.skills.weekly_report import WeeklyReportSkill
from app.skills.ppt_maker_v2 import PPTMakerSkill
from app.skills.feishu_doc_reader import FeishuDocReaderSkill
from app.skills.feishu_minutes_reader import FeishuMinutesReaderSkill
from app.skills.image_gen import ImageGenSkill

register(WeeklyReportSkill())
register(PPTMakerSkill())
register(FeishuMinutesReaderSkill())   # minutes before docs — URL pattern match priority
register(FeishuDocReaderSkill())
# ChatAnalyzerSkill removed from registry — extract_user_info_from_message
# in chat_service handles user profiling automatically in background.
register(ImageGenSkill())

