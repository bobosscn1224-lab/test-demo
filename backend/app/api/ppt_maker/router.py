"""PPT Maker Feature API — router re-export.

Import this module to get the fully assembled ppt-maker router
with all sub-routers (projects, outline, collage, pages) included.
"""

from app.api.ppt_maker import router

__all__ = ["router"]
