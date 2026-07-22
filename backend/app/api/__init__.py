"""Feature API routers — independent of skill system.

These provide direct, form-based access to stable business features
that previously only existed as conversational skills.

Routes are mounted under /api/v1/ for clear versioning.
"""
from fastapi import APIRouter

from app.api.reports import router as reports_router
from app.api.images import router as images_router
from app.api.pptx import router as pptx_router
from app.api.ppt_maker import router as ppt_maker_router
from app.api.assets import router as assets_router
from app.api.video_gen import router as video_gen_router
from app.api.pro_mode import router as pro_mode_router

feature_router = APIRouter(prefix="/api/v1")

feature_router.include_router(reports_router)
feature_router.include_router(images_router)
feature_router.include_router(pptx_router)
feature_router.include_router(ppt_maker_router)
feature_router.include_router(assets_router)
feature_router.include_router(video_gen_router)
feature_router.include_router(pro_mode_router)

__all__ = ["feature_router"]
