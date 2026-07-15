"""PPT Maker Feature API — standalone REST endpoints at /api/v1/ppt-maker/.

Independent of the conversational skill system. Provides structured, form-based
access to the full PPT creation pipeline:

1. Project CRUD       → /projects
2. Content upload     → /projects/{id}/content
3. Outline generation → /projects/{id}/outline
4. Collage variants   → /projects/{id}/collages
5. Page generation    → /projects/{id}/pages
"""

from fastapi import APIRouter

from app.api.ppt_maker import projects, outline, collage, pages

router = APIRouter(prefix="/ppt-maker", tags=["ppt-maker"], redirect_slashes=False)

router.include_router(projects.router)
router.include_router(outline.router)
router.include_router(collage.router)
router.include_router(pages.router)

__all__ = ["router"]
