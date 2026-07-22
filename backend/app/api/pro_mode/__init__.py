"""Pro Mode API — modular package.

Each step is an independent sub-module with its own APIRouter.
All modules share prompt_engine (AI calls + prompt building) and
projects (persistence layer) as common dependencies.

Package structure:
  models.py        — Pydantic models + templates (no router)
  prompt_engine.py — Shared AI call helper + prompt builders (no router)
  projects.py      — Project CRUD + persistence layer
  scripting.py     — Step 0: Script structuring
  resources.py     — Step 1: Resource extraction + generation
  storyboard.py    — Step 2: Storyboard planning
  director.py      — Step 3: Director suggestions
  generation.py    — Step 4: Shot generation + portrait
  compose.py       — Step 5: Auto composition
"""

from fastapi import APIRouter

from .projects import router as projects_router
from .scripting import router as scripting_router
from .resources import router as resources_router
from .storyboard import router as storyboard_router
from .director import router as director_router
from .generation import router as generation_router
from .compose import router as compose_router

router = APIRouter(prefix="/pro-mode", tags=["pro-mode"])

router.include_router(scripting_router)
router.include_router(resources_router)
router.include_router(storyboard_router)
router.include_router(director_router)
router.include_router(generation_router)
router.include_router(compose_router)
router.include_router(projects_router)

__all__ = ["router"]
