"""Backward-compatible re-export.  New code should import from the package directly.

    from app.services.image_generation import (
        calculate_grid_layout,
        normalize_collage_image,
        build_collage_prompts,
        ImageGenerationService,
    )
"""

from app.services.image_generation import (
    # Types
    GridLayout,
    GenerationResult,
    CollageBatchResult,
    # Layout
    calculate_grid_layout,
    normalize_collage_image,
    # Prompts
    build_collage_prompts,
    build_collage_regen_prompt,
    count_pages_in_outline,
    build_briefing_context,
    # Service
    ImageGenerationService,
    # Registry
    list_registered,
)

# Keep __all__ in sync with the package
__all__ = [
    "GridLayout", "GenerationResult", "CollageBatchResult",
    "calculate_grid_layout", "normalize_collage_image",
    "build_collage_prompts", "build_collage_regen_prompt",
    "count_pages_in_outline", "build_briefing_context",
    "ImageGenerationService", "list_registered",
]
