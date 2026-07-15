"""Phase 1: Page layout structure analysis + semantic naming + output report.

Analyses spatial distribution of text and image elements to:
  1. Classify page structure (single-column, multi-column, card-grid, timeline, ...)
  2. Group nearby elements into logical "cards" / "sections"
  3. Assign semantic names (title, subtitle, card-1-title, etc.)
  4. Generate human-readable output report (editable vs image vs shape)
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Page structure classification
# ═══════════════════════════════════════════════════════════════════════════

def analyze_page_structure(
    text_items: list[dict[str, Any]],
    image_items: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    iw: int, ih: int,
) -> dict[str, Any]:
    """Classify page layout structure and group elements into semantic regions.

    Returns:
      layout_type: str       — "title+cards", "two-column", "timeline", "grid", "single-block"
      sections: list[dict]   — semantic groups with elements
      reading_order: list    — elements sorted by reading order (top-down, left-right)
    """
    all_elements = _merge_elements(text_items, image_items, shapes)

    layout_type = _classify_layout(all_elements, iw, ih)
    sections = _group_into_sections(all_elements, iw, ih, layout_type)
    reading_order = _compute_reading_order(all_elements)

    return {
        "layout_type": layout_type,
        "sections": sections,
        "reading_order": reading_order,
        "element_count": len(all_elements),
    }


def _merge_elements(
    text_items: list[dict], image_items: list[dict], shapes: list[dict],
) -> list[dict[str, Any]]:
    """Merge all element types into a unified list with element_type tag.

    NOTE: Reuses original dicts (does not copy) so semantic names set on
    elements are reflected in the original text_items/image_items lists.
    """
    merged = []
    for t in text_items:
        t["element_type"] = "text"
        merged.append(t)
    for img in image_items:
        img["element_type"] = "image"
        merged.append(img)
    for s in shapes:
        s["element_type"] = "shape"
        s.setdefault("x", s.get("x1", 0))
        s.setdefault("y", s.get("y1", 0))
        s.setdefault("w", s.get("w", abs(s.get("x2", 0) - s.get("x1", 0))))
        s.setdefault("h", s.get("h", abs(s.get("y2", 0) - s.get("y1", 0))))
        merged.append(s)
    return merged


def _classify_layout(elements: list[dict], iw: int, ih: int) -> str:
    """Classify page layout based on element distribution."""
    if not elements:
        return "empty"

    texts = [e for e in elements if e["element_type"] == "text"]
    if not texts:
        return "image-only"

    # Collect horizontal centers of significant text regions
    centers = []
    for t in texts:
        if t.get("w", 0) > iw * 0.05:
            cx = (t["x"] + t["w"] / 2) / iw
            centers.append(cx)

    if not centers:
        return "single-block"

    # Two-column detection: bimodal center distribution
    if len(centers) >= 4:
        left = [c for c in centers if c < 0.45]
        right = [c for c in centers if c > 0.55]
        if len(left) >= 2 and len(right) >= 2:
            return "two-column"

    # Card grid: many small-medium elements at similar y positions
    y_positions = defaultdict(list)
    for t in texts:
        row_key = round(t["y"] / (ih / 6))
        y_positions[row_key].append(t)
    rows_with_multi = sum(1 for items in y_positions.values() if len(items) >= 3)
    if rows_with_multi >= 3:
        return "card-grid"

    # Timeline: elements spread vertically with horizontal line/arrow shapes
    shapes_list = [e for e in elements if e["element_type"] == "shape"]
    has_horizontal_line = any(
        s.get("type") in ("line", "arrow") and abs(s.get("y1", 0) - s.get("y2", 0)) < 10
        for s in shapes_list
    )
    if has_horizontal_line and len(texts) >= 3:
        return "timeline"

    # Title + content: one large element at top
    large_top = [t for t in texts if t["y"] < ih * 0.2 and t.get("w", 0) > iw * 0.3]
    if large_top and len(texts) >= 3:
        return "title+content"

    return "single-block"


def _group_into_sections(elements: list[dict], iw: int, ih: int, layout_type: str) -> list[dict]:
    """Group spatially-related elements into semantic sections/cards."""
    sections = []
    used = set()

    texts = [e for e in elements if e["element_type"] == "text"]
    images = [e for e in elements if e["element_type"] == "image"]
    shapes = [e for e in elements if e["element_type"] == "shape"]

    # Title detection: largest text near top
    title_candidates = sorted(
        [t for t in texts if t["y"] < ih * 0.18 and t.get("w", 0) > iw * 0.15],
        key=lambda t: (-t.get("h", 0), t["y"]),
    )
    if title_candidates:
        title = title_candidates[0]
        used.add(id(title))
        sections.append({
            "type": "title_area",
            "label": "页面标题区",
            "y_range": (title["y"], title["y"] + title["h"]),
            "elements": [title],
        })

    # Subtitle: second text element near top
    subtitle_candidates = sorted(
        [t for t in texts if id(t) not in used and t["y"] < ih * 0.28 and t.get("w", 0) > iw * 0.12],
        key=lambda t: (t["y"], -t.get("w", 0)),
    )
    if subtitle_candidates:
        sub = subtitle_candidates[0]
        used.add(id(sub))
        sections.append({
            "type": "subtitle_area",
            "label": "副标题区",
            "y_range": (sub["y"], sub["y"] + sub["h"]),
            "elements": [sub],
        })

    # Card grouping: cluster elements by spatial proximity
    remaining_texts = [t for t in texts if id(t) not in used]
    remaining_images = [img for img in images if id(img) not in used]
    cards = _cluster_into_cards(remaining_texts, remaining_images, shapes, iw, ih)
    for card_idx, card_elements in enumerate(cards, 1):
        for e in card_elements:
            used.add(id(e))
        y_vals = [e["y"] for e in card_elements]
        sections.append({
            "type": "card" if len(card_elements) >= 2 else "text_block",
            "label": f"卡片 {card_idx}" if len(card_elements) >= 2 else f"文本块 {card_idx}",
            "index": card_idx,
            "y_range": (min(y_vals), max(e["y"] + e.get("h", 0) for e in card_elements)),
            "elements": card_elements,
        })

    # Footer / page number
    footer_texts = [
        t for t in texts
        if id(t) not in used and t["y"] > ih * 0.88
    ]
    if footer_texts:
        for ft in footer_texts:
            used.add(id(ft))
        sections.append({
            "type": "footer",
            "label": "页脚区",
            "y_range": (min(t["y"] for t in footer_texts), max(t["y"] + t["h"] for t in footer_texts)),
            "elements": footer_texts,
        })

    # Unassigned
    orphan_texts = [t for t in texts if id(t) not in used]
    orphan_images = [img for img in images if id(img) not in used]
    if orphan_texts or orphan_images:
        sections.append({
            "type": "other",
            "label": "其他元素",
            "y_range": (0, ih),
            "elements": orphan_texts + orphan_images,
        })

    return sections


def _cluster_into_cards(
    texts: list[dict], images: list[dict], shapes: list[dict], iw: int, ih: int,
) -> list[list[dict]]:
    """Cluster nearby text+image+shape elements into cards via spatial proximity."""
    all_items = texts + images + shapes
    if len(all_items) <= 2:
        return [[item] for item in all_items] if all_items else []

    # Simple greedy clustering: merge if bounding boxes overlap or are very close
    clusters = []
    used = set()

    for i, item in enumerate(all_items):
        if i in used:
            continue
        cluster = [item]
        used.add(i)

        # Expand cluster with nearby items
        changed = True
        while changed:
            changed = False
            for j, other in enumerate(all_items):
                if j in used:
                    continue
                for c in cluster:
                    if _boxes_nearby(c, other, iw, ih):
                        cluster.append(other)
                        used.add(j)
                        changed = True
                        break

        clusters.append(cluster)

    # Sort clusters by position
    clusters.sort(key=lambda c: (c[0]["y"], c[0]["x"]))
    return clusters


def _boxes_nearby(a: dict, b: dict, iw: int, ih: int, gap_ratio: float = 0.06) -> bool:
    """Check if two bounding boxes are spatially related."""
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = a["x"] + a.get("w", 10), a["y"] + a.get("h", 10)
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = b["x"] + b.get("w", 10), b["y"] + b.get("h", 10)

    # Expand boxes by gap tolerance
    gap_x = max(iw * gap_ratio, 20)
    gap_y = max(ih * gap_ratio, 14)
    ax1 -= gap_x; ax2 += gap_x
    ay1 -= gap_y; ay2 += gap_y

    # Check overlap
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def _compute_reading_order(elements: list[dict]) -> list[dict]:
    """Sort elements by reading order: top-to-bottom, left-to-right."""
    return sorted(elements, key=lambda e: (
        round(e["y"] / 60) * 60,
        e["x"],
    ))


# ═══════════════════════════════════════════════════════════════════════════
# Semantic naming
# ═══════════════════════════════════════════════════════════════════════════

def assign_semantic_names(
    text_items: list[dict[str, Any]],
    sections: list[dict],
    iw: int, ih: int,
) -> None:
    """Assign semantic names to text items in-place based on section context."""
    for section in sections:
        stype = section["type"]
        label = section.get("label", "")

        for idx, element in enumerate(section.get("elements", [])):
            if element.get("element_type") != "text":
                continue

            role = element.get("role", "body")
            text = str(element.get("text", ""))[:30]

            if stype == "title_area":
                name = "main-title"
            elif stype == "subtitle_area":
                name = "subtitle"
            elif stype == "card":
                card_idx = section.get("index", 0)
                if idx == 0 and role in ("title", "heading"):
                    name = f"card-{card_idx}-title"
                elif role == "number":
                    name = f"card-{card_idx}-badge"
                else:
                    name = f"card-{card_idx}-body-{idx}"
            elif stype == "footer":
                name = "page-number" if role == "page_number" else "footer-note"
            elif stype == "text_block":
                name = f"text-block-{section.get('index', 0)}-{idx}"
            else:
                name = f"text-{role}-{element['y']}-{element['x']}"

            element["semantic_name"] = name


# ═══════════════════════════════════════════════════════════════════════════
# Output report
# ═══════════════════════════════════════════════════════════════════════════

def generate_output_report(
    text_items: list[dict[str, Any]],
    image_items: list[dict[str, Any]],
    shapes: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    sections: list[dict],
    layout_type: str,
    color_scheme: dict[str, Any],
    quality: dict[str, Any] | None = None,
) -> str:
    """Generate a human-readable report describing the PPTX structure.

    Follows the spec requirement: explain what's editable, what's image,
    what was sacrificed for visual fidelity, etc.
    """
    lines = ["## PPTX 还原报告", ""]

    # ── Layout type ──
    layout_names = {
        "title+content": "标题+内容布局",
        "two-column": "双栏布局",
        "card-grid": "卡片网格布局",
        "timeline": "时间线/流程图布局",
        "single-block": "单区块布局",
        "image-only": "纯图片页面",
    }
    lines.append(f"**页面结构**：{layout_names.get(layout_type, layout_type)}")
    lines.append("")

    # ── Colour scheme ──
    palette = color_scheme.get("palette", [])
    if palette:
        lines.append(f"**配色方案**：{', '.join(palette[:5])}")
        accent = color_scheme.get("accent", "")
        if accent:
            lines.append(f"**强调色**：{accent}")
        lines.append("")

    # ── Editable text ──
    lines.append("### [EDITABLE] 可编辑文本")
    lines.append("")
    if text_items:
        lines.append("| 元素 | 内容 | 语义名称 |")
        lines.append("|------|------|----------|")
        for t in text_items[:50]:
            name = t.get("semantic_name", "text")
            content = str(t.get("text", ""))[:40]
            lines.append(f"| {t.get('role', 'body')} | {content} | `{name}` |")
        if len(text_items) > 50:
            lines.append(f"| ... | _等 {len(text_items)} 个文本框_ | |")
    else:
        lines.append("_无_")
    lines.append("")

    # ── Native shapes ──
    lines.append("### [SHAPES] 原生形状")
    lines.append("")
    if shapes:
        lines.append("| 类型 | 位置 | 大小 |")
        lines.append("|------|------|------|")
        for s in shapes[:30]:
            stype = s.get("type", "rect")
            x, y, w, h = s.get("x", 0), s.get("y", 0), s.get("w", 0), s.get("h", 0)
            lines.append(f"| {stype} | ({x}, {y}) | {w}×{h} |")
        if len(shapes) > 30:
            lines.append(f"| ... | _等 {len(shapes)} 个形状_ | |")
    else:
        lines.append("_未检测到可重建的原生形状_")
    lines.append("")

    # ── Image assets ──
    lines.append("### [IMAGES] 图片素材（从原图裁切）")
    lines.append("")
    if image_items:
        lines.append("| 类别 | 位置 | 大小 | 原因 |")
        lines.append("|------|------|------|------|")
        for img in image_items[:30]:
            cat = img.get("category", "visual")
            x, y, w, h = img.get("x", 0), img.get("y", 0), img.get("w", 0), img.get("h", 0)
            reason = _image_retention_reason(img)
            lines.append(f"| {cat} | ({x}, {y}) | {w}×{h} | {reason} |")
        if len(image_items) > 30:
            lines.append(f"| ... | _等 {len(image_items)} 个图片素材_ | |")
    else:
        lines.append("_无_")
    lines.append("")

    # ── Tables ──
    if tables:
        lines.append("### [TABLES] 检测到的表格")
        for i, tbl in enumerate(tables, 1):
            lines.append(f"- 表格 {i}：{tbl.get('rows', '?')}行 × {tbl.get('cols', '?')}列")
        lines.append("")

    # ── Text retained as image ──
    lines.append("### [NOTE] 嵌入复杂视觉区域保留为图片的文字")
    lines.append("")
    complex_text = [t for t in text_items if t.get("retained_as_image")]
    if complex_text:
        for t in complex_text:
            lines.append(f"- `{t.get('semantic_name', 'text')}`：{t.get('retention_reason', '视觉保真优先')}")
    else:
        lines.append("_本项目所有 OCR 识别到的文字均已重建为可编辑文本框，无文字被保留为图片。_")
    lines.append("")

    # ── Visual fidelity trade-offs ──
    lines.append("### [TRADE-OFFS] 为保留视觉质感所做的取舍")
    lines.append("")
    trade_offs = _collect_trade_offs(text_items, image_items, shapes)
    if trade_offs:
        for to in trade_offs:
            lines.append(f"- {to}")
    else:
        lines.append("_本项目未发现需要标注的视觉取舍。_")
    lines.append("")

    # ── Quality calibration ──
    if quality and quality.get("passes"):
        lines.append("### [QA] 质量校准")
        lines.append("")
        best = quality.get("best_score", 0)
        lines.append(f"- 综合评分：**{best:.2%}**（{quality.get('best_pass', 0)} 轮校准后）")
        for p in quality.get("passes", []):
            score = p.get("score", 0)
            q = p.get("quality", "unknown")
            lines.append(f"  - 第 {p['pass']} 轮：SSIM={p.get('ssim', 0):.3f}，文本SSIM={p.get('text_ssim', 0):.3f}，{q}")

    return "\n".join(lines)


def _image_retention_reason(img: dict[str, Any]) -> str:
    """Determine why an image region was retained as a crop."""
    cat = img.get("category", "visual")
    reasons = {
        "icon": "图标/标识，保留原图保真",
        "photo": "照片/人物，不可重建",
        "chart": "复杂图表，保留原图",
        "logo": "品牌Logo，保留原图",
        "background": "复杂材质/纹理背景",
        "visual": "复杂视觉元素，无法用基础形状重建",
        "decor": "装饰元素",
    }
    return reasons.get(cat, "视觉保真优先")


def _collect_trade_offs(
    text_items: list[dict], image_items: list[dict], shapes: list[dict],
) -> list[str]:
    """Collect visual fidelity trade-off notes."""
    trade_offs = []

    # Check if simple elements are missing (no shapes detected)
    if not shapes:
        trade_offs.append("未检测到可重建的原生形状（圆角卡片、分隔线、箭头等），这些视觉元素以图片裁切方式保留。")

    # Check if color information is lost for text
    texts_without_color = [t for t in text_items if not t.get("color")]
    if texts_without_color:
        trade_offs.append(f"{len(texts_without_color)} 个文本框未能提取原文字颜色，使用默认深灰色 #1A1A1A。")

    # Check for complex images that could be shapes
    large_images = [img for img in image_items if img.get("w", 0) * img.get("h", 0) > 50000]
    if large_images:
        trade_offs.append(f"{len(large_images)} 个大型视觉区域保留为图片裁切而非重建为原生形状——优先保留了视觉质感。")

    return trade_offs
