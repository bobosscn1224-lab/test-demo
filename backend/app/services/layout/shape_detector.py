"""Phase 2: Native shape detection + colour-scheme extraction for DeckWeaver pipeline.

Ports and extends _detect_native_shapes from precise_reconstruction.py, adding:
  - Rounded-rect / rect / circle / line / arrow classification
  - K-Means colour palette extraction
  - Shape deduplication and confidence scoring
"""
from __future__ import annotations

import logging
import math
from collections import Counter
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Colour utilities
# ═══════════════════════════════════════════════════════════════════════════

def _bgr_to_hex(bgr: np.ndarray) -> str:
    b, g, r = (int(np.clip(v, 0, 255)) for v in bgr)
    return f"#{r:02X}{g:02X}{b:02X}"


def _hex_rgb(hex_color: str, fallback: tuple[int, int, int] = (17, 17, 17)) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return fallback


def _rgb_distance(a: str, b: str) -> float:
    ra, ga, ba = _hex_rgb(a)
    rb, gb, bb = _hex_rgb(b)
    return math.sqrt((ra - rb) ** 2 + (ga - gb) ** 2 + (ba - bb) ** 2)


def _is_nearly_background(hex_color: str, bg_hex: str, tolerance: int = 38) -> bool:
    return _rgb_distance(hex_color, bg_hex) < tolerance


def _sample_fill_hex(cv_img: np.ndarray, x: int, y: int, w: int, h: int) -> str:
    """Sample the interior colour of a region (inset from border)."""
    ih, iw = cv_img.shape[:2]
    margin = max(5, min(w, h) // 7)
    x1 = max(0, x + margin)
    y1 = max(0, y + margin)
    x2 = min(iw, x + w - margin)
    y2 = min(ih, y + h - margin)
    if x2 <= x1 or y2 <= y1:
        x1, y1, x2, y2 = max(0, x), max(0, y), min(iw, x + w), min(ih, y + h)
    roi = cv_img[y1:y2, x1:x2]
    return _bgr_to_hex(np.median(roi.reshape(-1, 3), axis=0)) if roi.size else "#FFFFFF"


def _sample_stroke_hex(cv_img: np.ndarray, x: int, y: int, w: int, h: int) -> str:
    """Sample the border colour of a region."""
    ih, iw = cv_img.shape[:2]
    band = max(2, min(4, min(w, h) // 10))
    x1, y1, x2, y2 = max(0, x), max(0, y), min(iw, x + w), min(ih, y + h)
    border_pixels = []
    if y1 + band < y2:
        border_pixels.append(cv_img[y1:y1 + band, x1:x2])
        border_pixels.append(cv_img[y2 - band:y2, x1:x2])
    if x1 + band < x2:
        border_pixels.append(cv_img[y1:y2, x1:x1 + band])
        border_pixels.append(cv_img[y1:y2, x2 - band:x2])
    if not border_pixels:
        return "#CCCCCC"
    combined = np.concatenate([p.reshape(-1, 3) for p in border_pixels])
    return _bgr_to_hex(np.median(combined, axis=0))


def _iou(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax1, ay1 = a["x"], a["y"]
    ax2, ay2 = a["x"] + a["w"], a["y"] + a["h"]
    bx1, by1 = b["x"], b["y"]
    bx2, by2 = b["x"] + b["w"], b["y"] + b["h"]
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    area_a = max(1, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1, (bx2 - bx1) * (by2 - by1))
    return inter_area / min(area_a, area_b)


# ═══════════════════════════════════════════════════════════════════════════
# Shape detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_native_shapes(cv_img: np.ndarray) -> list[dict[str, Any]]:
    """Detect conservative, high-confidence editable PPT geometry.

    Returns list of shapes: rounded_rect, rect, circle, line, arrow.
    Each shape has: type, x, y, w, h, fill, stroke, stroke_width, radius (if round_rect),
    confidence.
    """
    ih, iw = cv_img.shape[:2]
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 55, 150)

    # ── Estimate background colour ──
    bg_samples = np.concatenate([
        cv_img[0:8, :, :].reshape(-1, 3),
        cv_img[-8:, :, :].reshape(-1, 3),
        cv_img[:, 0:8, :].reshape(-1, 3),
        cv_img[:, -8:, :].reshape(-1, 3),
    ])
    background_hex = _bgr_to_hex(np.median(bg_samples, axis=0))

    shapes: list[dict[str, Any]] = []

    # ── 1. Rounded rectangles / cards / pill bands ──
    rect_edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _hierarchy = cv2.findContours(rect_edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    rects: list[dict[str, Any]] = []

    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < max(42, iw * 0.025) or h < max(18, ih * 0.020):
            continue
        if w > iw * 0.94 or h > ih * 0.42:
            continue
        box_area = w * h
        if box_area < iw * ih * 0.0008 or box_area > iw * ih * 0.18:
            continue
        aspect = w / max(h, 1)
        if aspect < 0.55 or aspect > 42:
            continue
        roi_edges = edges[y:y + h, x:x + w]
        if roi_edges.size == 0:
            continue

        # Border density check
        band = max(2, min(7, round(min(w, h) * 0.11)))
        border_mask = np.zeros((h, w), dtype=np.uint8)
        border_mask[:band, :] = 1
        border_mask[-band:, :] = 1
        border_mask[:, :band] = 1
        border_mask[:, -band:] = 1
        border_density = float(np.count_nonzero((roi_edges > 0) & (border_mask > 0))) / max(
            1, int(np.count_nonzero(border_mask))
        )
        interior_mask = border_mask == 0
        interior_density = float(np.count_nonzero((roi_edges > 0) & interior_mask)) / max(
            1, int(np.count_nonzero(interior_mask))
        )
        if border_density < 0.012:
            continue
        if interior_density > max(0.115, border_density * 3.8) and box_area < iw * ih * 0.035:
            continue

        fill_hex = _sample_fill_hex(cv_img, x, y, w, h)
        stroke_hex = _sample_stroke_hex(cv_img, x, y, w, h)

        # White-on-white artefacts (glyph fragments)
        if (
            box_area < iw * ih * 0.006
            and _is_nearly_background(fill_hex, background_hex)
            and _is_nearly_background(stroke_hex, background_hex, tolerance=28)
        ):
            continue

        # Classify: rounded_rect vs circle vs rect
        shape_type = _classify_contour_shape(contour, x, y, w, h)
        entry: dict[str, Any] = {
            "type": shape_type,
            "x": int(x), "y": int(y), "w": int(w), "h": int(h),
            "fill": fill_hex,
            "stroke": stroke_hex,
            "stroke_width": 0.55 if min(w, h) > 34 else 0.35,
            "confidence": 0.82,
        }
        if shape_type == "rounded_rect":
            entry["radius"] = round(min(0.45, max(0.08, min(w, h) / max(w, h) * 0.65)), 3)
        rects.append(entry)

    # Deduplicate by IoU
    rects.sort(key=lambda item: (item["w"] * item["h"], item["w"]), reverse=True)
    deduped_rects: list[dict[str, Any]] = []
    for rect in rects:
        duplicate = False
        for existing in deduped_rects:
            if _iou(rect, existing) > 0.72:
                duplicate = True
                break
            same_center = (
                abs((rect["x"] + rect["w"] / 2) - (existing["x"] + existing["w"] / 2)) < 8
                and abs((rect["y"] + rect["h"] / 2) - (existing["y"] + existing["h"] / 2)) < 8
            )
            if same_center and abs(rect["w"] - existing["w"]) < 18 and abs(rect["h"] - existing["h"]) < 18:
                duplicate = True
                break
        if not duplicate:
            deduped_rects.append(rect)
        if len(deduped_rects) >= 45:
            break
    shapes.extend(sorted(deduped_rects, key=lambda item: (item["y"], item["x"])))

    # ── 2. Lines (Hough) ──
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=max(28, round(iw * 0.022)),
        minLineLength=max(36, round(iw * 0.035)),
        maxLineGap=max(6, round(iw * 0.006)),
    )
    line_shapes: list[dict[str, Any]] = []
    if lines is not None:
        for raw in lines[:, 0]:
            x1, y1, x2, y2 = map(int, raw)
            if x2 < x1 or y2 < y1:
                x1, y1, x2, y2 = x2, y2, x1, y1
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            angle = abs(math.degrees(math.atan2(dy, dx)))
            if not (angle <= 2.5 or angle >= 177.5 or 87.5 <= angle <= 92.5):
                continue
            horizontal = angle <= 2.5 or angle >= 177.5
            minimum_length = max(48, iw * 0.055) if horizontal else max(38, ih * 0.055)
            if length < minimum_length:
                continue
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            sample = cv_img[max(0, my - 1):my + 2, max(0, mx - 1):mx + 2]
            bgr = np.median(sample.reshape(-1, 3), axis=0).astype(int)
            luminance = 0.114 * bgr[0] + 0.587 * bgr[1] + 0.299 * bgr[2]
            saturation = int(max(bgr) - min(bgr))
            if luminance < 105 and saturation < 30:
                continue
            # Exclude rectangle borders
            on_rect_border = False
            for rect in deduped_rects:
                near_horizontal_border = horizontal and (
                    abs(y1 - rect["y"]) < 5 or abs(y1 - (rect["y"] + rect["h"])) < 5
                ) and min(x2, rect["x"] + rect["w"]) - max(x1, rect["x"]) > length * 0.55
                near_vertical_border = (not horizontal) and (
                    abs(x1 - rect["x"]) < 5 or abs(x1 - (rect["x"] + rect["w"])) < 5
                ) and min(y2, rect["y"] + rect["h"]) - max(y1, rect["y"]) > length * 0.55
                if near_horizontal_border or near_vertical_border:
                    on_rect_border = True
                    break
            if on_rect_border:
                continue
            # Classify line vs arrow
            line_type = _classify_line_type(cv_img, x1, y1, x2, y2, edges)
            line_shapes.append({
                "type": line_type,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "stroke": f"#{bgr[2]:02X}{bgr[1]:02X}{bgr[0]:02X}",
                "stroke_width": 0.35 if luminance > 135 else 0.55,
                "confidence": 0.85 if line_type == "arrow" else 0.78,
            })

    # Deduplicate collinear lines
    deduped_lines: list[dict[str, Any]] = []
    for shape in sorted(line_shapes, key=lambda item: -math.hypot(item["x2"] - item["x1"], item["y2"] - item["y1"])):
        duplicate = False
        for existing in deduped_lines:
            horizontal = abs(shape["y2"] - shape["y1"]) < abs(shape["x2"] - shape["x1"])
            if horizontal:
                if abs(shape["y1"] - existing["y1"]) < 4 and min(shape["x2"], existing["x2"]) - max(shape["x1"], existing["x1"]) > 20:
                    duplicate = True
            else:
                if abs(shape["x1"] - existing["x1"]) < 4 and min(shape["y2"], existing["y2"]) - max(shape["y1"], existing["y1"]) > 20:
                    duplicate = True
            if duplicate:
                break
        if not duplicate:
            deduped_lines.append(shape)
    shapes.extend(deduped_lines[:80])

    # ── 3. Circles / ellipses ──
    circles = _detect_circles(cv_img, gray, iw, ih, background_hex)
    shapes.extend(circles[:30])

    return shapes[:120]


def _classify_contour_shape(contour, x: int, y: int, w: int, h: int) -> str:
    """Classify contour as rounded_rect, circle, or rect."""
    # Circle test: aspect ratio near 1 + high circularity
    aspect = w / max(h, 1)
    if 0.78 <= aspect <= 1.28:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity > 0.78:
                return "circle"

    # Rounded rect vs rect: check convexity defects + aspect
    hull = cv2.convexHull(contour)
    hull_area = cv2.contourArea(hull)
    contour_area = cv2.contourArea(contour)
    if hull_area > 0 and contour_area / hull_area < 0.92:
        return "rounded_rect"
    # Wide cards are usually rounded in modern slide decks
    if aspect > 3.5 and w > 200:
        return "rounded_rect"
    return "rect"


def _classify_line_type(cv_img: np.ndarray, x1: int, y1: int, x2: int, y2: int, edges: np.ndarray) -> str:
    """Distinguish arrow from plain line by checking for arrowhead at endpoint."""
    ih, iw = cv_img.shape[:2]
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 20:
        return "line"

    # Check end region for arrowhead (wider than the line)
    ux, uy = dx / length, dy / length
    tip_x, tip_y = x2, y2
    head_size = min(24, length * 0.22)
    head_x = int(tip_x - ux * head_size)
    head_y = int(tip_y - uy * head_size)

    # Sample perpendicular width near the tip
    px, py = -uy, ux
    samples = []
    for t in np.linspace(0, head_size, 3):
        cx = int(tip_x - ux * t)
        cy = int(tip_y - uy * t)
        for s in range(-8, 9, 4):
            sx = int(cx + px * s)
            sy = int(cy + py * s)
            if 0 <= sx < iw and 0 <= sy < ih:
                samples.append(edges[sy, sx])

    if samples:
        edge_count = sum(1 for v in samples if v > 0)
        if edge_count >= len(samples) * 0.35:
            return "arrow"
    return "line"


def _detect_circles(cv_img: np.ndarray, gray: np.ndarray, iw: int, ih: int, bg_hex: str) -> list[dict[str, Any]]:
    """Hough Circle detection for numbered badges, icons, etc."""
    circles_out: list[dict[str, Any]] = []
    try:
        detected = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=max(18, iw // 20),
            param1=70, param2=28,
            minRadius=max(8, iw // 100),
            maxRadius=min(60, iw // 12),
        )
        if detected is not None:
            for circle in detected[0, :]:
                cx, cy, r = int(circle[0]), int(circle[1]), int(circle[2])
                x, y, w, h = cx - r, cy - r, r * 2, r * 2
                if x < 0 or y < 0 or x + w > iw or y + h > ih:
                    continue
                fill_hex = _sample_fill_hex(cv_img, x, y, w, h)
                if _is_nearly_background(fill_hex, bg_hex, tolerance=20):
                    continue
                circles_out.append({
                    "type": "circle",
                    "x": x, "y": y, "w": w, "h": h,
                    "fill": fill_hex,
                    "stroke": _sample_stroke_hex(cv_img, x, y, w, h),
                    "stroke_width": 0.45,
                    "confidence": 0.75,
                })
    except Exception:
        pass
    return circles_out


# ═══════════════════════════════════════════════════════════════════════════
# Colour scheme extraction
# ═══════════════════════════════════════════════════════════════════════════

def extract_color_scheme(cv_img: np.ndarray, k: int = 5) -> dict[str, Any]:
    """Extract the dominant colour palette via K-Means in RGB space.

    Returns dict with:
      - palette: list of hex colours sorted by dominance
      - background: estimated background hex
      - accent: most saturated non-background colour
    """
    ih, iw = cv_img.shape[:2]
    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    pixels = rgb.reshape(-1, 3).astype(np.float32)

    # Sample edge pixels for background estimate
    edge_pixels = np.concatenate([
        rgb[0:8, :, :].reshape(-1, 3),
        rgb[-8:, :, :].reshape(-1, 3),
        rgb[:, 0:8, :].reshape(-1, 3),
        rgb[:, -8:, :].reshape(-1, 3),
    ]).astype(np.float32)
    bg_median = np.median(edge_pixels, axis=0)
    background_hex = f"#{int(bg_median[0]):02X}{int(bg_median[1]):02X}{int(bg_median[2]):02X}"

    # K-Means clustering
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    try:
        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    except Exception:
        return {"palette": [background_hex], "background": background_hex, "accent": background_hex}

    centers = centers.astype(int)
    label_counts = Counter(labels.flatten().tolist())
    total = sum(label_counts.values())

    palette = []
    for idx, _count in label_counts.most_common():
        r, g, b = centers[idx]
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        ratio = round(label_counts[idx] / total, 3)
        palette.append({"hex": hex_color, "ratio": ratio, "rgb": (int(r), int(g), int(b))})

    # Find accent (most saturated non-background colour with meaningful presence)
    accent = background_hex
    max_saturation = 0
    for entry in palette:
        if entry["ratio"] < 0.04:
            continue
        r, g, b = entry["rgb"]
        sat = max(r, g, b) - min(r, g, b)
        if sat > max_saturation and _rgb_distance(entry["hex"], background_hex) > 35:
            max_saturation = sat
            accent = entry["hex"]

    return {
        "palette": [p["hex"] for p in palette],
        "palette_detailed": palette,
        "background": background_hex,
        "accent": accent,
    }
