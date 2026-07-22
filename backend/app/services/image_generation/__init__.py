"""Image generation package — unified image processing and generation.

=== Public API Registry ===

Types:
    GridLayout            — precise pixel layout for collage grids
    GenerationResult      — single image generation result
    CollageBatchResult    — batch collage generation result

Grid & Layout:
    calculate_grid_layout(total_pages, ...)  → GridLayout
    normalize_collage_image(path, pages)      → str | None

Prompts:
    build_collage_prompts(project)            → list[(label, prompt)]
    build_collage_regen_prompt(project, ...)  → str
    count_pages_in_outline(text)              → int
    build_briefing_context(project)           → str

Service (high-level):
    ImageGenerationService.text_to_image(...)
    ImageGenerationService.image_to_image(...)
    ImageGenerationService.generate_collage_variants(...)
    ImageGenerationService.generate_collage_single(...)

=== Usage ===
    from app.services.image_generation import (
        calculate_grid_layout,
        normalize_collage_image,
        build_collage_prompts,
        ImageGenerationService,
    )
"""

from .types import GridLayout, GenerationResult, CollageBatchResult
from .layout import calculate_grid_layout, normalize_collage_image, grid_canvas_size
from .prompts import (
    build_collage_prompts,
    build_collage_regen_prompt,
    count_pages_in_outline,
    build_briefing_context,
)
from .service import ImageGenerationService

# ── Public API registry ──────────────────────────────────────────────────
# Callable by other projects/features to discover available functions.

__all__ = [
    # Types
    "GridLayout",
    "GenerationResult",
    "CollageBatchResult",
    # Layout
    "calculate_grid_layout",
    "normalize_collage_image",
    "grid_canvas_size",
    # Prompts
    "build_collage_prompts",
    "build_collage_regen_prompt",
    "count_pages_in_outline",
    "build_briefing_context",
    # Service
    "ImageGenerationService",
]

# Registry: name → callable, for dynamic discovery
_REGISTRY: dict[str, object] = {
    "calculate_grid_layout": calculate_grid_layout,
    "normalize_collage_image": normalize_collage_image,
    "build_collage_prompts": build_collage_prompts,
    "build_collage_regen_prompt": build_collage_regen_prompt,
    "count_pages_in_outline": count_pages_in_outline,
    "build_briefing_context": build_briefing_context,
    "generate_collage_variants": ImageGenerationService.generate_collage_variants,
    "generate_collage_single": ImageGenerationService.generate_collage_single,
    "text_to_image": ImageGenerationService.text_to_image,
    "image_to_image": ImageGenerationService.image_to_image,
}


def list_registered() -> dict[str, str]:
    """Return all registered functions with their docstrings.

    Other projects can call this to discover what's available:

        from app.services.image_generation import list_registered
        for name, doc in list_registered().items():
            print(f"{name}: {doc}")
    """
    result: dict[str, str] = {}
    for name, fn in _REGISTRY.items():
        doc = (getattr(fn, "__doc__") or "").strip().split("\n")[0]
        result[name] = doc
    return result
