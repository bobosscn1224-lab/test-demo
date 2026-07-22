"""Deterministic fixed-grid reference image for collage generation."""

from __future__ import annotations

import base64
import io
import math

from PIL import Image, ImageDraw, ImageFont

from app.services.image_quality_gate import get_image_spec


def render_collage_grid_template(
    *, total_pages: int, columns: int = 3,
) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
    """Render equal 16:9 slots, including complete empty slots in the last row."""
    if total_pages <= 0 or columns <= 0:
        raise ValueError("total_pages and columns must be positive")
    geometry = get_image_spec("ppt_collage").get("grid_geometry") or {}
    template = geometry.get("generation_template") or {}
    canvas_width = int(template.get("canvas_width") or 1200)
    border_width = int(template.get("border_width") or 4)
    rows = math.ceil(total_pages / columns)

    # For the configured 1200px canvas these values produce 384x216 cells,
    # 12px horizontal gutters and 8px vertical gutters.  The 4-row result is
    # exactly 1200x900 (4:3), matching 3x4 cells whose individual ratio is 16:9.
    margin_x = max(4, round(canvas_width * 0.01))
    gap_x = margin_x
    cell_width = (canvas_width - 2 * margin_x - (columns - 1) * gap_x) // columns
    cell_height = round(cell_width * 9 / 16)
    gap_y = max(4, round(gap_x * 2 / 3))
    margin_y = max(4, round(gap_y * 3 / 4))
    canvas_height = rows * cell_height + (rows - 1) * gap_y + 2 * margin_y

    image = Image.new("RGB", (canvas_width, canvas_height), (15, 27, 46))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    boxes: list[tuple[int, int, int, int]] = []
    for index in range(rows * columns):
        row, column = divmod(index, columns)
        left = margin_x + column * (cell_width + gap_x)
        top = margin_y + row * (cell_height + gap_y)
        right, bottom = left + cell_width, top + cell_height
        boxes.append((left, top, right, bottom))
        active = index < total_pages
        fill = (248, 250, 253) if active else (31, 47, 68)
        outline = (45, 117, 220) if active else (91, 108, 130)
        draw.rectangle(
            (left, top, right - 1, bottom - 1),
            fill=fill, outline=outline, width=border_width,
        )
        label = f"PAGE {index + 1:02d}" if active else "EMPTY SLOT"
        badge_fill = (22, 76, 164) if active else (52, 65, 82)
        draw.rounded_rectangle(
            (left + 10, top + 10, left + 98, top + 34),
            radius=5, fill=badge_fill,
        )
        draw.text((left + 17, top + 17), label, fill="white", font=font)
        if active:
            draw.text(
                (left + 16, bottom - 28),
                "KEEP THIS 16:9 SLOT BOUNDARY",
                fill=(93, 108, 128), font=font,
            )
    return image, boxes


def build_collage_grid_template_reference(*, total_pages: int, columns: int = 3) -> str:
    """Return the fixed grid as an inline PNG accepted by Tutujin multimodal calls."""
    image, _boxes = render_collage_grid_template(
        total_pages=total_pages, columns=columns,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
