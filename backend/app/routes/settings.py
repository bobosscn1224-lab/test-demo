import os
from fastapi import APIRouter
from app.config import settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings():
    import json as _json
    watch_dirs_raw = settings.watch_dirs
    try:
        watch_dirs = _json.loads(watch_dirs_raw) if isinstance(watch_dirs_raw, str) else watch_dirs_raw
    except _json.JSONDecodeError:
        watch_dirs = []
    return {
        "watch_dirs": watch_dirs,
        "active_persona": settings.active_persona,
        "deepseek_model": settings.claude_model,
        "feishu_enabled": bool(settings.feishu_app_id or os.environ.get("FEISHU_APP_ID", "")),
    }


@router.get("/user-profile")
async def get_user_profile():
    from app.services.user_profile_service import UserProfileService
    from app.core.database import async_session

    async with async_session() as db:
        svc = UserProfileService(db)
        profile = await svc.get_or_create()
        return {
            "basic_info": profile.basic_info,
            "expertise": profile.expertise,
            "projects": profile.projects,
            "preferences": profile.preferences,
            "learned_facts": profile.learned_facts,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
        }


@router.post("/watch-dirs")
async def set_watch_dirs(data: dict):
    dirs = data.get("dirs", "")
    os.environ["WATCH_DIRS"] = dirs
    return {"ok": True, "watch_dirs": dirs}
