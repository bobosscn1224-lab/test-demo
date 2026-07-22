"""Agnes Vision API integration — layout understanding for PPTX reconstruction.

Uses Agnes (OpenAI-compatible multi-modal endpoint) to semantically understand
slide layout: element types, grouping relationships, color scheme, and design
intent.  This replaces the need for GPT-5.5 in the Codex pipeline and provides
the semantics that pure OCR/OpenCV pipelines lack.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")


_SYSTEM_PROMPT = """You are an expert slide design analyst. Analyze this slide mockup and return structured JSON.

Your analysis MUST be exhaustive — identify EVERY visible element on the page. Do not skip elements.

## Task
1. Classify the page layout and visual style
2. Extract the color scheme (real hex values from the image — do NOT guess)
3. List EVERY text element with its content and precise position
4. Identify EVERY shape, icon, divider, badge, logo, and image
5. Group related elements into logical units (cards, flow steps, header blocks)

## JSON Output Structure
{
  "page_structure": {
    "layout_type": "title+content | card-grid | timeline | two-column | title-only | process-flow | comparison | single-block",
    "reading_order": "top-to-bottom | left-to-right | center-out",
    "visual_style": "corporate | creative | minimal | tech | academic",
    "background_type": "solid | gradient | image | textured",
    "background_color_hex": "#XXXXXX"
  },
  "color_scheme": {
    "primary": "#XXXXXX",
    "secondary": "#XXXXXX",
    "accent": "#XXXXXX",
    "text_dark": "#XXXXXX",
    "text_light": "#XXXXXX",
    "card_fill": "#XXXXXX or null",
    "palette": ["#XXXXXX"]
  },
  "elements": [
    {
      "id": "elem-1",
      "type": "title|subtitle|body|kpi-number|kpi-label|card|icon|arrow|circle-badge|divider-line|photo|illustration|logo|page-number|bullet-list|callout-box|footer|button|tag",
      "label": "Main Title",
      "x_pct": 5.0, "y_pct": 3.0, "width_pct": 90.0, "height_pct": 8.0,
      "role": "title|heading|body|number|page_number|decorative",
      "text_content": "exact visible text",
      "font_style": {
        "weight": "bold|semibold|regular|light",
        "size_rank": "xl|lg|md|sm|xs",
        "color_hex": "#XXXXXX",
        "alignment": "left|center|right"
      },
      "shape": {
        "has_fill": true,
        "fill_color_hex": "#XXXXXX or null",
        "has_border": false,
        "border_color_hex": null,
        "corner_radius_px": 8,
        "has_shadow": false,
        "shape_type": "rounded_rect|rect|circle|line|arrow|none"
      },
      "group_id": "group-1",
      "z_index": 0
    }
  ],
  "groups": [
    {
      "id": "group-1",
      "type": "card|flow-step|comparison-col|badge-row|header-block|footer-block",
      "element_ids": ["elem-4", "elem-5", "elem-6"],
      "label": "Card 1"
    }
  ]
}

## CRITICAL RULES
1. Exhaustiveness: include EVERY visible element — do not skip small items
2. Coordinates: use percentage (0-100), x=0 y=0 is top-left, BE PRECISE (±2%)
3. Text content: copy text EXACTLY as visible — do not paraphrase
4. Colors: sample from image, do NOT guess — use hex format #RRGGBB
5. Groups: every card/block/flow-step should group its background + title + body + icon
6. z_index: 0=bg, 1=shapes, 2=images/icons, 3=foreground text
7. Output ONLY valid JSON — no markdown, no explanation
"""

_USER_PROMPT_TEMPLATE = """Analyze this slide mockup image. Identify every visual element on the page:

1. What is the page layout type?
2. What are all text elements (titles, subtitles, body text, numbers, labels)?
3. What shapes are present (cards, icons, arrows, lines, circles, badges)?
4. What groupings exist (which elements form each card/section/block)?
5. What is the color scheme?
6. What is the z-order layering?

Output the complete JSON following the schema. Be precise with coordinates (percentage, 0-100)."""


async def analyze_layout(
    image_path: str,
    api_key: str | None = None,
    model: str = "agnes-2.0-flash",
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Send slide image to Agnes for layout understanding.

    Returns structured JSON with element types, positions, groups, and colors.
    Falls back gracefully on network/API errors - returns minimal structure.
    """
    key = api_key or AGNES_API_KEY
    if not key:
        logger.warning("No Agnes API key available - layout analysis skipped")
        return _empty_layout()

    try:
        from app.services.vision_model_service import vision_model_service
        result = await vision_model_service.analyze(
            interaction_name="vision_layout_analysis",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=_USER_PROMPT_TEMPLATE,
            image_path=image_path,
            api_key=key,
        )
        _validate_and_fix_layout(result)
        return result
    except Exception as exc:
        logger.warning("Agnes gated vision analysis failed: %s", exc)
        return _empty_layout()


def _parse_response(content: str) -> dict[str, Any]:
    """Extract JSON from Agnes response, handling markdown fences."""
    content = content.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fence_match:
        content = fence_match.group(1).strip()

    try:
        result = json.loads(content)
        _validate_and_fix_layout(result)
        return result
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                result = json.loads(match.group())
                _validate_and_fix_layout(result)
                return result
            except json.JSONDecodeError:
                pass
        logger.warning("Failed to parse Agnes layout JSON. Raw: %s", content[:500])
        return _empty_layout()


def _validate_and_fix_layout(layout: dict[str, Any]) -> None:
    """Ensure the layout has all required fields; fill defaults where missing."""
    if "page_structure" not in layout:
        layout["page_structure"] = {}
    ps = layout["page_structure"]
    ps.setdefault("layout_type", "title+content")
    ps.setdefault("reading_order", "top-to-bottom")
    ps.setdefault("visual_style", "corporate")
    ps.setdefault("background_type", "solid")
    ps.setdefault("background_color_hex", "#FFFFFF")

    if "color_scheme" not in layout:
        layout["color_scheme"] = {}
    cs = layout["color_scheme"]
    cs.setdefault("primary", "#08766F")
    cs.setdefault("text_dark", "#111111")
    cs.setdefault("text_light", "#FFFFFF")
    cs.setdefault("palette", [cs.get("primary", "#08766F"), cs.get("text_dark", "#111111")])

    elements = layout.get("elements", [])
    for elem in elements:
        elem.setdefault("id", f"elem-{elements.index(elem)}")
        elem.setdefault("type", "body")
        elem.setdefault("x_pct", 0)
        elem.setdefault("y_pct", 0)
        elem.setdefault("width_pct", 10)
        elem.setdefault("height_pct", 5)
        elem.setdefault("role", "body")
        elem.setdefault("text_content", None)
        elem.setdefault("font_style", {})
        elem.setdefault("shape", {})
        elem.setdefault("group_id", None)
        elem.setdefault("z_index", 3)

    if "groups" not in layout:
        layout["groups"] = []


def _empty_layout() -> dict[str, Any]:
    return {
        "page_structure": {
            "layout_type": "title+content",
            "reading_order": "top-to-bottom",
            "visual_style": "corporate",
            "background_type": "solid",
            "background_color_hex": "#FFFFFF",
        },
        "color_scheme": {
            "primary": "#08766F",
            "text_dark": "#111111",
            "text_light": "#FFFFFF",
            "palette": ["#08766F", "#111111", "#FFFFFF"],
        },
        "elements": [],
        "groups": [],
        "_empty": True,
    }


def fuse_agnes_with_ocr(
    agnes_layout: dict[str, Any],
    ocr_regions: list[dict[str, Any]],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    """Merge Agnes layout understanding with OCR text regions.

    For each Agnes element that has a text role, match it to the best
    OCR region by spatial overlap.  Non-text elements (shapes, icons,
    photos) come exclusively from Agnes.
    """
    fused_elements: list[dict[str, Any]] = []
    unmatched_ocr = list(ocr_regions)

    for elem in agnes_layout.get("elements", []):
        elem_type = elem.get("type", "body")
        is_text_element = elem_type in {
            "title", "subtitle", "body", "kpi-number", "kpi-label",
            "bullet-list", "page-number", "footer", "tag", "callout-box",
        }

        if is_text_element and unmatched_ocr:
            ex = elem["x_pct"] / 100.0 * image_width
            ey = elem["y_pct"] / 100.0 * image_height
            ew = elem["width_pct"] / 100.0 * image_width
            eh = elem["height_pct"] / 100.0 * image_height

            best_match = None
            best_iou = 0.0
            for ocr in unmatched_ocr:
                iou = _iou_rects(
                    ex, ey, ew, eh,
                    ocr["x"], ocr["y"], ocr["w"], ocr["h"],
                )
                if iou > best_iou:
                    best_iou = iou
                    best_match = ocr

            if best_match and best_iou > 0.08:
                fused = dict(best_match)
                fused["agnes_type"] = elem_type
                fused["agnes_role"] = elem.get("role", "body")
                fused["agnes_group_id"] = elem.get("group_id")
                fused["agnes_font_style"] = elem.get("font_style", {})
                fused["agnes_shape"] = elem.get("shape", {})
                fused["agnes_z"] = elem.get("z_index", 3)
                fused_elements.append(fused)
                unmatched_ocr.remove(best_match)
                continue

        fused_elements.append({
            "id": elem.get("id", f"agnes-{len(fused_elements)}"),
            "text": elem.get("text_content", ""),
            "x": round(elem["x_pct"] / 100.0 * image_width),
            "y": round(elem["y_pct"] / 100.0 * image_height),
            "w": round(elem["width_pct"] / 100.0 * image_width),
            "h": round(elem["height_pct"] / 100.0 * image_height),
            "agnes_type": elem_type,
            "agnes_role": elem.get("role", "body"),
            "agnes_group_id": elem.get("group_id"),
            "agnes_font_style": elem.get("font_style", {}),
            "agnes_shape": elem.get("shape", {}),
            "agnes_z": elem.get("z_index", 3),
            "role": elem.get("role", "body"),
            "words": [],
            "confidence": 0.0,
        })

    for ocr in unmatched_ocr:
        ocr["agnes_type"] = "body"
        ocr["agnes_role"] = "body"
        ocr["agnes_group_id"] = None
        ocr["agnes_font_style"] = {}
        ocr["agnes_shape"] = {}
        ocr["agnes_z"] = 3
        fused_elements.append(ocr)

    fused_elements.sort(key=lambda e: (e["y"], e["x"]))

    return {
        **agnes_layout,
        "fused_elements": fused_elements,
        "ocr_count": len(ocr_regions),
        "agnes_count": len(agnes_layout.get("elements", [])),
        "fused_count": len(fused_elements),
    }


def _iou_rects(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> float:
    x1 = max(ax, bx)
    y1 = max(ay, by)
    x2 = min(ax + aw, bx + bw)
    y2 = min(ay + ah, by + bh)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / max(union, 1.0)
