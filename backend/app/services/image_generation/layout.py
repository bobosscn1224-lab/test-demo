"""Grid layout calculation and image normalization.

These are pure image-processing utilities — no API calls, no LLM interaction.
"""

from __future__ import annotations

import logging
import math
import os

from .types import GridLayout

logger = logging.getLogger(__name__)


# ── Grid calculation ─────────────────────────────────────────────────────

def calculate_grid_layout(
    total_pages: int,
    *,
    columns: int = 4,
    cell_w: int = 400,
    cell_h: int = 225,
    gap: int = 12,
    margin: int = 20,
) -> GridLayout:
    """Calculate precise pixel positions for a collage grid.

    Args:
        total_pages: number of slides
        columns: grid columns (default 4)
        cell_w: thumbnail width in px (default 400)
        cell_h: thumbnail height in px (default 225, for 16:9)
        gap: spacing between cells in px
        margin: edge margin in px

    Returns:
        GridLayout with canvas dimensions and per-slide positions.
    """
    rows = math.ceil(total_pages / columns)
    canvas_w = 2 * margin + columns * cell_w + (columns - 1) * gap
    canvas_h = 2 * margin + rows * cell_h + (rows - 1) * gap

    # Round to multiples of 16 for API compatibility
    canvas_w = (canvas_w + 8) // 16 * 16
    canvas_h = (canvas_h + 8) // 16 * 16

    positions: list[tuple[int, int, int, int]] = []
    page = 1
    for r in range(rows):
        for c in range(columns):
            if page > total_pages:
                break
            x = margin + c * (cell_w + gap)
            y = margin + r * (cell_h + gap)
            positions.append((page, x, y, cell_w, cell_h))
            page += 1

    return GridLayout(
        canvas_w=canvas_w, canvas_h=canvas_h,
        columns=columns, rows=rows, total_pages=total_pages,
        cell_w=cell_w, cell_h=cell_h, gap=gap, margin=margin,
        positions=positions,
    )


def grid_canvas_size(total_pages: int, columns: int = 4) -> str:
    """Return the API size string for the calculated grid canvas."""
    layout = calculate_grid_layout(total_pages, columns=columns)
    return f"{layout.canvas_w}x{layout.canvas_h}"


# ── Normalization ────────────────────────────────────────────────────────

def normalize_collage_image(image_path: str, total_pages: int) -> str | None:
    """Normalize a generated collage to exact grid dimensions.

    Two-pass approach:
    1. Resize the whole image to the target canvas (fixes aspect ratio)
    2. Crop each cell by known coordinates, resize to uniform size, recompose
       (fixes internal stretching/misalignment)

    Returns None on success, or an error string on failure.
    """
    try:
        from PIL import Image
    except ImportError:
        return "Pillow not installed — cannot normalize collage"

    try:
        img = Image.open(image_path).convert("RGB")
        layout = calculate_grid_layout(total_pages)

        # Step 1: Resize whole image to target canvas
        img = img.resize((layout.canvas_w, layout.canvas_h), Image.LANCZOS)

        # Step 2: Crop each cell and recompose into a clean grid
        canvas = Image.new("RGB", (layout.canvas_w, layout.canvas_h), (255, 255, 255))
        for page, x, y, w, h in layout.positions:
            cell = img.crop((x, y, x + w, y + h))
            if cell.size != (w, h):
                cell = cell.resize((w, h), Image.LANCZOS)
            canvas.paste(cell, (x, y))

        canvas.save(image_path, "PNG")

        logger.info(
            "Collage normalized: %s → %d×%d, %d cells recomposed",
            os.path.basename(image_path), layout.canvas_w, layout.canvas_h, total_pages,
        )
        return None
    except Exception as exc:
        return f"Collage normalization failed: {exc}"
