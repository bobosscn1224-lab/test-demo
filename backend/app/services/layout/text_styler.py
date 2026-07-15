"""Phase 4: Text style inference + font detection for DeckWeaver pipeline.

Ports _augment_text_styles / _visual_color_runs / _font_name_for_region
from precise_reconstruction.py, adapted for the LAYOUT pipeline context.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_CJK_RE = re.compile(r"[㐀-鿿]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_DIGIT_RE = re.compile(r"[0-9]")

# System font fallback chain (Windows)
FONT_FALLBACK = {
    "cjk_sans": "Microsoft YaHei",       # 微软雅黑 — closest to 苹方/思源黑体 on Windows
    "cjk_serif": "SimSun",               # 宋体
    "latin_sans": "Arial",               # closest to Helvetica
    "latin_serif": "Georgia",
    "number": "Arial",
}


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


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _is_latin_dominant(text: str) -> bool:
    latin = len(_LATIN_RE.findall(text))
    digits = len(_DIGIT_RE.findall(text))
    cjk = len(_CJK_RE.findall(text))
    total = latin + digits + cjk
    return total > 0 and (latin + digits) / total > 0.58


# ═══════════════════════════════════════════════════════════════════════════
# Font detection
# ═══════════════════════════════════════════════════════════════════════════

def detect_font_for_region(region: dict[str, Any]) -> str:
    """Select the best system font based on text content and role."""
    role = region.get("role", "body")
    text = str(region.get("text", ""))

    if role in ("number", "page_number") and not _contains_cjk(text):
        return FONT_FALLBACK["number"]
    if _is_latin_dominant(text) and not _contains_cjk(text):
        return FONT_FALLBACK["latin_sans"]
    return FONT_FALLBACK["cjk_sans"]


def effective_bold(region: dict[str, Any]) -> bool:
    """Infer whether text should be bold based on role, size, and colour."""
    if bool(region.get("bold")):
        return True
    role = region.get("role", "body")
    if role in ("title", "heading", "number", "page_number"):
        return True
    image_height = max(1, int(region.get("image_height") or 900))
    if region.get("median_word_h", 0) >= image_height * 0.022 and len(str(region.get("text", ""))) <= 18:
        return True
    # Teal/green labels in corporate slides are usually semibold
    color = str(region.get("color", "#111111"))
    r, g, b = _hex_rgb(color, (17, 17, 17))
    if g > r * 1.15 and g >= b * 0.85 and len(str(region.get("text", ""))) <= 24:
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Per-character colour detection
# ═══════════════════════════════════════════════════════════════════════════

def sample_foreground_hex(cv_img: np.ndarray, x: int, y: int, w: int, h: int) -> str:
    """Sample the foreground (dark text) colour from a text region."""
    ih, iw = cv_img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(iw, x + w), min(ih, y + h)
    if x2 <= x1 or y2 <= y1:
        return "#111111"
    crop = cv_img[y1:y2, x1:x2]
    bg = _sample_background_bgr(cv_img, x1, y1, x2 - x1, y2 - y1)
    distance = np.linalg.norm(crop.astype(np.float32) - bg.reshape(1, 1, 3), axis=2)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    threshold = max(28.0, float(np.percentile(distance, 62)))
    fg_mask = (distance >= threshold) & (gray < 242)
    if int(fg_mask.sum()) < 8:
        return "#111111"
    fg_pixels = crop[fg_mask]
    bgr = np.median(fg_pixels, axis=0)
    return f"#{int(bgr[2]):02X}{int(bgr[1]):02X}{int(bgr[0]):02X}"


def _sample_background_bgr(cv_img: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    """Estimate local background BGR from region borders."""
    ih, iw = cv_img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(iw, x + w), min(ih, y + h)
    samples = []
    band = 2
    if y1 + band < y2:
        samples.append(cv_img[y1:y1 + band, x1:x2].reshape(-1, 3))
        samples.append(cv_img[y2 - band:y2, x1:x2].reshape(-1, 3))
    if x1 + band < x2:
        samples.append(cv_img[y1:y2, x1:x1 + band].reshape(-1, 3))
        samples.append(cv_img[y1:y2, x2 - band:x2].reshape(-1, 3))
    return np.median(np.concatenate(samples), axis=0) if samples else np.array([255, 255, 255])


def visual_color_runs(
    cv_img: np.ndarray, region: dict[str, Any], text: str,
) -> list[tuple[str, str]] | None:
    """Approximate per-character colours from source pixels.

    Returns list of (text_fragment, hex_color) or None if uniform.
    """
    text = text or ""
    if len(text) < 2 or len(text) > 120:
        return None
    ih, iw = cv_img.shape[:2]
    pad = max(2, round(float(region.get("median_word_h", region.get("h", 16))) * 0.12))
    x1 = max(0, round(region["x"] - pad))
    y1 = max(0, round(region["y"] - pad))
    x2 = min(iw, round(region["x"] + region["w"] + pad))
    y2 = min(ih, round(region["y"] + region["h"] + pad))
    if x2 <= x1 or y2 <= y1:
        return None

    crop = cv_img[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    bg = _sample_background_bgr(cv_img, x1, y1, x2 - x1, y2 - y1)
    distance = np.linalg.norm(crop.astype(np.float32) - bg.reshape(1, 1, 3), axis=2)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    threshold = max(22.0, float(np.percentile(distance, 70)))
    mask = (distance >= threshold) & (gray < 248)
    if int(mask.sum()) < max(10, len(text) * 2):
        return None

    default_color = region.get("color") or sample_foreground_hex(
        cv_img, int(region["x"]), int(region["y"]), int(region["w"]), int(region["h"]),
    )
    width = crop.shape[1]
    colors: list[str] = []
    for index, _character in enumerate(text):
        start = int(round(width * index / len(text)))
        end = int(round(width * (index + 1) / len(text)))
        end = max(end, start + 1)
        band_mask = mask[:, start:end]
        if int(band_mask.sum()) < 3:
            colors.append(default_color)
            continue
        pixels = crop[:, start:end][band_mask]
        bgr = np.median(pixels, axis=0)
        color = f"#{int(bgr[2]):02X}{int(bgr[1]):02X}{int(bgr[0]):02X}"
        if _rgb_distance(color, default_color) < 48:
            color = default_color
        colors.append(color)

    # Smooth isolated single-char glitches (anti-aliasing artefacts)
    for index in range(1, len(colors) - 1):
        if colors[index - 1] == colors[index + 1] and _rgb_distance(colors[index], colors[index - 1]) < 80:
            colors[index] = colors[index - 1]

    runs: list[tuple[str, str]] = []
    for character, color in zip(text, colors):
        if runs and _rgb_distance(runs[-1][1], color) < 38:
            runs[-1] = (runs[-1][0] + character, runs[-1][1])
        else:
            runs.append((character, color))
    distinct = {color for _, color in runs}
    if len(distinct) <= 1:
        return None
    if len(runs) > 10:
        return None
    return runs


# ═══════════════════════════════════════════════════════════════════════════
# Text style augmentation (applied to all text regions)
# ═══════════════════════════════════════════════════════════════════════════

def augment_text_styles(cv_img: np.ndarray, regions: list[dict[str, Any]]) -> None:
    """Enrich text regions with font, bold, foreground colour, and colour runs."""
    for region in regions:
        text = str(region.get("text", "")).strip()
        if not text:
            continue
        region.setdefault("image_width", cv_img.shape[1])
        region.setdefault("image_height", cv_img.shape[0])
        region["font_name"] = detect_font_for_region(region)
        region["bold"] = effective_bold(region)

        # Sample foreground colour if not already set
        if not region.get("color"):
            region["color"] = sample_foreground_hex(
                cv_img,
                int(region.get("x", 0)), int(region.get("y", 0)),
                int(region.get("w", 100)), int(region.get("h", 30)),
            )

        # Detect per-character colour runs
        visual_runs = visual_color_runs(cv_img, region, text)
        if visual_runs:
            region["visual_color_runs"] = [
                {"text": run_text, "color": run_color}
                for run_text, run_color in visual_runs
            ]
            longest = max(visual_runs, key=lambda item: len(item[0]))
            region["color"] = longest[1]


# ═══════════════════════════════════════════════════════════════════════════
# Table detection (Phase 4)
# ═══════════════════════════════════════════════════════════════════════════

def detect_tables(cv_img: np.ndarray) -> list[dict[str, Any]]:
    """Detect table regions via grid-line analysis.

    Returns list of table dicts with: x, y, w, h, rows, cols, cells.
    """
    ih, iw = cv_img.shape[:2]
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # Binary threshold to find grid lines
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Detect horizontal and vertical lines
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(24, iw // 30), 1))
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(24, ih // 30)))

    horiz_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horiz_kernel)
    vert_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vert_kernel)

    # Intersection = table grid
    grid = cv2.bitwise_and(horiz_lines, vert_lines)
    grid = cv2.dilate(grid, np.ones((3, 3), np.uint8), iterations=2)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(grid, 8)
    tables = []
    min_area = iw * ih * 0.005

    for i in range(1, num_labels):
        cx, cy, cw, ch, area = [int(v) for v in stats[i]]
        if area < min_area:
            continue
        aspect = cw / max(ch, 1)
        if aspect < 0.5 or aspect > 5:
            continue

        # Count grid lines inside region
        roi_horiz = horiz_lines[cy:cy + ch, cx:cx + cw]
        roi_vert = vert_lines[cy:cy + ch, cx:cx + cw]

        # Count rows and cols by projecting
        h_proj = np.mean(roi_horiz, axis=1)
        v_proj = np.mean(roi_vert, axis=0)

        row_count = int(np.sum(h_proj > 10)) // max(1, cw // 3)
        col_count = int(np.sum(v_proj > 10)) // max(1, ch // 3)

        if row_count >= 2 and col_count >= 2:
            tables.append({
                "x": cx, "y": cy, "w": cw, "h": ch,
                "rows": min(row_count, 30),
                "cols": min(col_count, 20),
                "confidence": min(0.9, 0.5 + 0.1 * min(row_count, col_count)),
            })

    return tables[:5]
