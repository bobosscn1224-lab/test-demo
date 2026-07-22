"""LLM-driven layout_plan.json generator.

Takes an image + CV/OCR pre-analysis -> LLM produces structured layout plan
with exact coordinates, text, colors, z-order, and editability intent.
"""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

LAYOUT_PLAN_SYSTEM_PROMPT = """You are a precise visual layout analyzer. Your task is to decompose a slide image into a structured JSON layout plan for image-to-editable-PPT reconstruction.

## Output Format
You MUST output ONLY valid JSON matching this schema:

```json
{
  "version": "1.0",
  "canvas": {"width": <int>, "height": <int>, "aspect": "16:9", "background": "#XXXXXX"},
  "quality_mode": "balanced",
  "assets": [
    {"id": "asset_<name>", "type": "crop", "source": "normalized.png",
     "crop": {"x": <int>, "y": <int>, "w": <int>, "h": <int>},
     "file": "asset_<name>.png", "reason": "<why preserved as image>"}
  ],
  "elements": [
    {"id": "<unique_id>", "type": "rect|text|line|circle|arrow|polygon|image|table", ...}
  ]
}
```

## Rules

### Background
- The background.type is reported in the analysis as "solid", "gradient", or "complex_image"
- For solid: create a single full-slide rect element with the background color
- For gradient: the background.gradient section contains type, angle, and color stops
- For complex_image: the full-slide image IS the background (no rect element needed)

### Coordinates
- All coordinates in image pixels, origin at top-left
- Be precise -- these are used to position PPTX elements exactly

### Text elements
- `type: "text"` for ALL readable text (titles, subtitles, body, labels, numbers, footers)
- Include EXACT text content, x, y, w, h, font_size (px), font_weight (400/700), color (#hex), align, z
- Mark uncertain text with `"needs_review": true`
- For Chinese text, prefer font_family: "Microsoft YaHei"
- Set `"editability": "editable"` for text

### Rect elements
- `type: "rect"` for cards, panels, colored bands, button backgrounds
- Include fill color, stroke color, stroke_width, rx (corner radius)
- Set `"editability": "editable"`

### Line elements
- `type: "line"` for dividers, separators, thin borders
- Include x1, y1, x2, y2, stroke color, stroke_width
- Set `"editability": "editable"`

### Circle elements
- `type: "circle"` for circular badges, icons, dots, radio buttons
- Include cx, cy, r (center x, y, radius), fill color, stroke color, stroke_width
- Set `"editability": "editable"`

### Arrow elements
- `type: "arrow"` for directional indicators, flow arrows, pointers
- Include x1, y1, x2, y2, stroke color, stroke_width, arrow_head ("start"|"end"|"both")
- Set `"editability": "editable"`

### Polygon elements
- `type: "polygon"` for triangles, hexagons, chevrons, freeform shapes
- Include points as [[x,y],[x,y],...] array, fill color, stroke color, stroke_width
- Set `"editability": "editable"`

### Image assets
- Complex logos, photos, screenshots, 3D graphics, textures, complex charts
- Declare in BOTH `assets` array AND `elements` array
- `"editability": "asset"`

### Table elements
- `type: "table"` for structured data grids
- Include rows, cols, cell_text (array of arrays), font_size

### Z-order (4-layer structure)
- Layer 0 (z=1-10): Background (full-slide rect or image)
- Layer 1 (z=10-20): Image assets (logos, photos, cropped visuals)
- Layer 2 (z=20-40): Native shapes (rects, circles, lines, arrows)
- Layer 3 (z=40-60): Text (titles, body, labels, footers)

### Quality modes
- `"quality_mode": "balanced"` (default): core text/shapes editable, complex visuals as assets
- `"quality_mode": "max_editable"`: push more elements to be editable
- `"quality_mode": "visual_locked"`: full-slide image background + overlay editable text

## CRITICAL
- Output ONLY the JSON object, no markdown fences, no explanations
- Every text element must have the EXACT text as it appears in the image
- If you cannot read text clearly, mark it `needs_review: true` and give your best guess
- Do NOT invent or hallucinate text"""


LAYOUT_PLAN_USER_PROMPT = """Analyze this slide image and create a layout_plan.json.

## Image Info
- Dimensions: {width}x{height} pixels
- Aspect ratio: {aspect}

## Background Analysis
- Type: {bg_type}
- {bg_details}

## OCR-Detected Text Regions
The following text was detected by OCR with positions (x, y, width, height in pixels):

{ocr_data}

## CV-Detected Shapes
The following visual elements were detected:

{shape_data}

## Circle & Arrow Regions
{circle_arrow_data}

## Detected Table/Chart Regions
{table_data}

## Color Analysis
- Slide background: {bg_color}
- Dominant font color (estimated): {font_color}
- Dominant colors detected: {dominant_colors}
- Estimated font families: {font_families}

## Instructions
1. Use the OCR text as a starting point but CORRECT any recognition errors
2. Group related text into appropriate text elements with proper hierarchy
3. Identify cards, panels, and colored regions as rect elements
4. Identify lines and dividers
5. Place detected circles and arrows as native shape elements
6. Represent table regions as table elements with rows and columns
7. Mark logos, photos, and complex graphics as image asset crops
8. Assign proper z-order following the 4-layer structure
9. For the background: if solid or gradient, create a background rect; if complex, note it
10. Output ONLY the JSON -- no markdown, no explanations

Create the complete layout_plan.json:"""


async def generate_layout_plan(
    image_path: str,
    ocr_text_regions: list[dict],
    cv_shapes: list[dict],
    dominant_colors: list[str],
    bg_color: str,
    width: int,
    height: int,
    quality_mode: str = "balanced",
    bg_type: str = "complex",
    bg_gradient: dict | None = None,
    table_regions: list[dict] | None = None,
    font_families: list[str] | None = None,
    dominant_font_color: str | None = None,
) -> dict | None:
    """Use LLM to generate a structured layout_plan.json from image analysis data."""
    from app.services.llm_service import llm_service

    # Format OCR data
    ocr_lines = []
    for i, tr in enumerate(ocr_text_regions):
        review = " [NEEDS REVIEW]" if tr.get("needs_review") else ""
        ocr_lines.append(
            f"  {i+1}. \"{tr['text'][:100]}\" "
            f"at ({tr['x']},{tr['y']}) {tr['w']}x{tr['h']} "
            f"font_est={tr.get('font_size_est', '?')}pt "
            f"title={tr.get('is_title', False)}{review}"
        )
    ocr_data_str = "\n".join(ocr_lines) if ocr_lines else "(no text detected)"

    # Format shape data
    shape_lines = []
    for s in cv_shapes[:25]:
        if s["type"] == "line":
            shape_lines.append(
                f"  - Line({s.get('subtype', '')}): ({s['x1']:.0f},{s['y1']:.0f})->({s['x2']:.0f},{s['y2']:.0f})"
            )
        elif s["type"] == "rectangle":
            shape_lines.append(
                f"  - Rect: ({s['x']:.1f},{s['y']:.1f}) {s['w']:.1f}x{s['h']:.1f} fill=({s.get('fill', (0,0,0))})"
            )
        elif s["type"] == "circle":
            shape_lines.append(
                f"  - Circle: cx={s['cx']:.1f} cy={s['cy']:.1f} r={s['r']:.1f}"
            )
        elif s["type"] == "arrow":
            shape_lines.append(
                f"  - Arrow: ({s['x']:.1f},{s['y']:.1f}) {s['w']:.1f}x{s['h']:.1f}"
            )
    shape_data_str = "\n".join(shape_lines[:35]) if shape_lines else "(no shapes detected)"

    # Format circle/arrow data
    ca_items = [s for s in cv_shapes if s["type"] in ("circle", "arrow")]
    if ca_items:
        ca_lines = []
        for s in ca_items[:10]:
            if s["type"] == "circle":
                ca_lines.append(f"  - Circle at ({s['cx']:.0f},{s['cy']:.0f}) radius={s['r']:.0f}")
            elif s["type"] == "arrow":
                ca_lines.append(f"  - Arrow at ({s['x']:.0f},{s['y']:.0f}) {s['w']:.0f}x{s['h']:.0f}")
        circle_arrow_str = "\n".join(ca_lines)
    else:
        circle_arrow_str = "(no circles or arrows detected)"

    # Format table data
    if table_regions:
        table_lines = []
        for i, t in enumerate(table_regions):
            table_lines.append(
                f"  {i+1}. {t.get('category', 'table')}: "
                f"({t['x']:.0f},{t['y']:.0f}) {t['w']:.0f}x{t['h']:.0f} "
                f"~{t.get('rows', '?')}rows x {t.get('cols', '?')}cols"
            )
        table_data_str = "\n".join(table_lines)
    else:
        table_data_str = "(no tables detected)"

    # Format colors
    colors_str = ", ".join(dominant_colors[:8]) if dominant_colors else "unknown"
    font_color = dominant_font_color or "#000000"
    font_fam_str = ", ".join(font_families[:4]) if font_families else "Microsoft YaHei, Arial"

    # Format background details
    if bg_type == "gradient" and bg_gradient:
        stops_desc = ", ".join(
            f"{s.get('pos', '?')}:{s.get('color', '?')}"
            for s in bg_gradient.get("stops", [])
        )
        bg_details = f"Gradient ({bg_gradient.get('type', 'linear')}, {bg_gradient.get('angle', 0)}deg): {stops_desc}"
    elif bg_type == "solid":
        bg_details = f"Solid color: {bg_color}"
    else:
        bg_details = "Complex (photo, texture, or multi-element background)"

    user_prompt = LAYOUT_PLAN_USER_PROMPT.format(
        width=width,
        height=height,
        aspect="16:9",
        bg_type=bg_type,
        bg_details=bg_details,
        ocr_data=ocr_data_str,
        shape_data=shape_data_str,
        circle_arrow_data=circle_arrow_str,
        table_data=table_data_str,
        bg_color=bg_color,
        font_color=font_color,
        dominant_colors=colors_str,
        font_families=font_fam_str,
    )

    if quality_mode == "max_editable":
        user_prompt += "\n\nIMPORTANT: Use max_editable mode -- push more elements to be editable text/shapes. Only preserve truly complex images as assets."
    elif quality_mode == "visual_locked":
        user_prompt += "\n\nIMPORTANT: Use visual_locked mode -- keep full-slide image as base, overlay editable text only where safe."

    try:
        response = await llm_service.chat(
            interaction_name="layout_plan_generation",
            system_prompt=LAYOUT_PLAN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=8192,
            temperature=0.2,
        )

        text = ""
        if hasattr(response, "content") and response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        elif isinstance(response, str):
            text = response
        else:
            text = str(response)

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        plan = json.loads(text)

        if "canvas" not in plan:
            plan["canvas"] = {"width": width, "height": height, "aspect": "16:9", "background": f"#{bg_color}"}
        if "elements" not in plan:
            logger.warning("Layout plan missing 'elements'")
            return None
        if "version" not in plan:
            plan["version"] = "1.0"
        if "quality_mode" not in plan:
            plan["quality_mode"] = quality_mode
        if "assets" not in plan:
            plan["assets"] = []

        logger.info(
            "Layout plan generated: %d elements, %d assets",
            len(plan.get("elements", [])),
            len(plan.get("assets", [])),
        )
        return plan

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse layout plan JSON: %s", e)
        logger.debug("Raw response: %s", text[:500] if 'text' in dir() else 'N/A')
        return None
    except Exception as e:
        logger.warning("Layout plan generation failed: %s", e)
        return None
