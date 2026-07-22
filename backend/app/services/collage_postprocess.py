"""Content-preserving collage grid normalization.

Image models create the visual content; deterministic code owns the exact grid.
Detected cards are fitted wholly inside equal 16:9 cells.  This module never
crops card content and never stretches it to a different aspect ratio.
"""

from __future__ import annotations

import logging
import math
import os
import statistics
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

logger = logging.getLogger(__name__)


def _median_color(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    return tuple(
        int(statistics.median(color[channel] for color in colors))
        for channel in range(3)
    )


def _canvas_background(image: Image.Image) -> tuple[int, int, int]:
    width, height = image.size
    samples: list[tuple[int, int, int]] = []
    step_x = max(1, width // 80)
    step_y = max(1, height // 80)
    for x in range(0, width, step_x):
        samples.extend((image.getpixel((x, 0)), image.getpixel((x, height - 1))))
    for y in range(0, height, step_y):
        samples.extend((image.getpixel((0, y)), image.getpixel((width - 1, y))))
    return _median_color(samples)


def _cell_background(cell: Image.Image) -> tuple[int, int, int]:
    width, height = cell.size
    return _median_color([
        cell.getpixel((0, 0)),
        cell.getpixel((width - 1, 0)),
        cell.getpixel((0, height - 1)),
        cell.getpixel((width - 1, height - 1)),
    ])


def normalize_collage_grid(
    input_path: str,
    output_path: str,
    total_pages: int,
    columns: int = 3,
    *,
    spec: dict[str, Any],
) -> bool:
    """Reassemble detected cards into an exact, content-preserving grid."""
    geometry = spec.get("grid_geometry") or {}
    normalization = geometry.get("normalization") or {}
    if not normalization.get("enabled", False):
        return True
    if normalization.get("fit_mode") != "contain":
        logger.error("Unsupported collage normalization fit_mode: %s", normalization.get("fit_mode"))
        return False

    temporary_path: Path | None = None
    try:
        source = Image.open(input_path).convert("RGB")
        width, height = source.size
        rows = math.ceil(total_pages / max(columns, 1))
        if total_pages <= 0 or columns <= 0 or rows <= 0:
            return False

        from app.services.image_quality_gate import detect_confident_collage_grid_boxes

        boxes = detect_confident_collage_grid_boxes(
            source,
            expected_pages=total_pages,
            columns=columns,
        )
        if len(boxes) != total_pages:
            logger.warning(
                "Collage normalization cannot identify every card: expected=%d detected=%d",
                total_pages,
                len(boxes),
            )
            return False

        target_aspect = float(geometry.get("target_cell_aspect", 16 / 9))
        margin_fraction = float(normalization.get("margin_fraction", 0.02))
        gap_fraction = float(normalization.get("gap_fraction", 0.01))
        border_width = int(normalization.get("border_width", 2))
        shortest = min(width, height)
        margin = max(4, round(shortest * margin_fraction))
        gap = max(4, round(shortest * gap_fraction))
        available_width = width - 2 * margin - (columns - 1) * gap
        available_height = height - 2 * margin - (rows - 1) * gap
        cell_width = min(
            available_width // columns,
            int((available_height // rows) * target_aspect),
        )
        cell_height = round(cell_width / target_aspect)
        if cell_width < 64 or cell_height < 36:
            logger.error("Normalized collage cells would be too small: %dx%d", cell_width, cell_height)
            return False

        canvas_color = _canvas_background(source)
        canvas = Image.new("RGB", (width, height), canvas_color)
        grid_width = columns * cell_width + (columns - 1) * gap
        grid_height = rows * cell_height + (rows - 1) * gap
        origin_x = (width - grid_width) // 2
        origin_y = (height - grid_height) // 2
        outline = (35, 50, 70) if sum(canvas_color) / 3 >= 128 else (225, 230, 240)
        resampling = getattr(Image, "Resampling", Image).LANCZOS

        for index, box in enumerate(boxes):
            left, top, right, bottom = box
            # Include antialiased borders around the detected projection line.
            left = max(0, math.floor(left) - 2)
            top = max(0, math.floor(top) - 2)
            right = min(width, math.ceil(right) + 2)
            bottom = min(height, math.ceil(bottom) + 2)
            if right <= left or bottom <= top:
                return False
            source_cell = source.crop((left, top, right, bottom))
            cell = Image.new("RGB", (cell_width, cell_height), _cell_background(source_cell))
            inner_size = (
                max(1, cell_width - 2 * border_width),
                max(1, cell_height - 2 * border_width),
            )
            fitted = ImageOps.contain(source_cell, inner_size, method=resampling)
            paste_x = (cell_width - fitted.width) // 2
            paste_y = (cell_height - fitted.height) // 2
            cell.paste(fitted, (paste_x, paste_y))
            if border_width > 0:
                ImageDraw.Draw(cell).rectangle(
                    (0, 0, cell_width - 1, cell_height - 1),
                    outline=outline,
                    width=border_width,
                )

            row, column = divmod(index, columns)
            destination = (
                origin_x + column * (cell_width + gap),
                origin_y + row * (cell_height + gap),
            )
            canvas.paste(cell, destination)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output.with_name(
            f".{output.stem}.normalized-{uuid.uuid4().hex[:8]}.png"
        )
        canvas.save(temporary_path, "PNG", optimize=True)
        os.replace(temporary_path, output)
        logger.info(
            "Normalized collage without crop/stretch: %s (%d cards, %dx%d each)",
            output,
            total_pages,
            cell_width,
            cell_height,
        )
        return True
    except Exception as exc:
        logger.error("Collage normalization failed: %s", exc, exc_info=True)
        return False
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
