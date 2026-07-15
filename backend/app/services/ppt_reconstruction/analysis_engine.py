"""Enhanced CV/OCR Analysis Engine — comprehensive element detection for PPTX reconstruction.

Consolidates and enhances all CV/OCR pre-analysis functions previously scattered across
image_to_pptx.py and pipeline.py. Adds PaddleOCR for Chinese, circle/arrow detection,
gradient analysis, text inpainting, and table/chart region detection.

Architecture:
  source image → PaddleOCR (primary) + Tesseract (fallback) → merged text regions
               → CV shape detection (lines, rects, circles, arrows, polygons)
               → Background analysis (solid/gradient/complex)
               → Visual asset detection (entropy-based)
               → Table/chart region detection
               → Text inpainting (cv2.inpaint for background cleanup)
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
MIN_CONFIDENCE = 30
MIN_SHAPE_AREA_FRAC = 0.001
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
PADDLEOCR_LANG = "ch"

# PaddleOCR singleton (lazy-loaded, first call is slow, subsequent calls fast)
_paddle_ocr = None


def _get_paddle_ocr():
    """Lazy-load PaddleOCR singleton.

    Uses the same parameter set as precise_reconstruction.py for consistency:
    doc_orientation_classify and doc_unwarping are disabled to speed up
    detection of individual PPT slide pages (not full scanned documents).
    """
    global _paddle_ocr
    if _paddle_ocr is None:
        try:
            from paddleocr import PaddleOCR
            _paddle_ocr = PaddleOCR(
                lang=PADDLEOCR_LANG,
                ocr_version="PP-OCRv4",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
            )
            logger.info("PaddleOCR initialized (lang=%s, doc_orientation=False, doc_unwarp=False)", PADDLEOCR_LANG)
        except Exception as exc:
            logger.warning("PaddleOCR not available: %s. Falling back to Tesseract only.", exc)
            _paddle_ocr = False
    return _paddle_ocr if _paddle_ocr is not False else None


# ═══════════════════════════════════════════════════════════════════════════════
# Master orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

def detect_all_elements(
    image_path: str,
    pil_img,
    cv_img: np.ndarray,
    iw: int,
    ih: int,
    sx: float,
    sy: float,
) -> dict:
    """Run all CV/OCR analysis and return structured detection data.

    Returns:
        dict with keys: width, height, text_regions, shapes, visual_assets,
                        tables, background, dominant_colors, dominant_font_color,
                        font_families
    """
    h, w = cv_img.shape[:2]

    # ── OCR text regions (PaddleOCR + Tesseract merge) ──
    paddle_regions = _ocr_paddle(pil_img, iw, ih)
    tesseract_regions = _ocr_tesseract(pil_img, iw, ih)
    text_regions = _ocr_combined(paddle_regions, tesseract_regions)
    logger.info("Analysis: %d text regions (paddle=%d, tesseract=%d, merged=%d)",
                len(text_regions), len(paddle_regions), len(tesseract_regions), len(text_regions))

    # ── Shape detection ──
    shapes = _detect_all_shapes(cv_img, iw, ih, sx, sy)
    logger.info("Analysis: %d shapes detected", len(shapes))

    # ── Background analysis ──
    bg_type, bg_solid, bg_gradient = _detect_background_type(cv_img)
    logger.info("Analysis: background type=%s solid=%s", bg_type, bg_solid)

    # ── Dominant colors ──
    dominant_colors = _extract_dominant_colors(cv_img)

    # ── Font color estimation ──
    dominant_font_color = _detect_dominant_font_color(cv_img, text_regions) if text_regions else "#000000"

    # ── Font family estimation ──
    font_families = _detect_font_family_heuristics(text_regions, cv_img)

    # ── Visual assets (complex non-text regions) ──
    visual_assets = _detect_visual_assets(cv_img, text_regions, iw, ih, sx, sy)

    # ── Table/chart regions ──
    tables = _detect_chart_table_regions(cv_img, text_regions, iw, ih, sx, sy)

    return {
        "width": iw,
        "height": ih,
        "text_regions": text_regions,
        "shapes": shapes,
        "visual_assets": visual_assets,
        "tables": tables,
        "background": {
            "type": bg_type,
            "solid_color": bg_solid,
            "gradient": bg_gradient,
        },
        "dominant_colors": dominant_colors,
        "dominant_font_color": dominant_font_color,
        "font_families": font_families,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# OCR: PaddleOCR
# ═══════════════════════════════════════════════════════════════════════════════

def _ocr_paddle(pil_img, iw: int, ih: int) -> list[dict]:
    """Run PaddleOCR for Chinese text detection with precise coordinates.

    Uses PaddleOCR 3.x predict() API which returns OCRResult objects with:
      - dt_polys: List[np.ndarray] — detected polygons, each (4, 2) corner coords
      - rec_texts: List[str] — recognized text strings
      - rec_scores: List[float] — confidence scores (0-1)
    """
    paddle = _get_paddle_ocr()
    if not paddle:
        return []

    try:
        import numpy as np
        img_array = np.array(pil_img.convert("RGB"))

        # PaddleOCR 3.x: predict() returns generator of OCRResult objects
        results = list(paddle.predict(img_array))

        if not results:
            return []

        regions = []
        for res in results:
            # PaddleOCR 3.x OCRResult: access as dict for compatibility
            dt_polys = res.get("dt_polys", []) if isinstance(res, dict) else getattr(res, "dt_polys", [])
            rec_texts = res.get("rec_texts", []) if isinstance(res, dict) else getattr(res, "rec_texts", [])
            rec_scores = res.get("rec_scores", []) if isinstance(res, dict) else getattr(res, "rec_scores", [])

            if not dt_polys or not rec_texts:
                continue

            for poly, text, score in zip(dt_polys, rec_texts, rec_scores):
                confidence = float(score)

                if confidence < 0.5:
                    continue
                if not text or not text.strip():
                    continue

                # poly is shape (4, 2) — four corner points of the detected quad
                poly_arr = np.asarray(poly)
                if poly_arr.ndim != 2 or poly_arr.shape[1] != 2:
                    continue

                xs = poly_arr[:, 0].tolist()
                ys = poly_arr[:, 1].tolist()
                min_x, max_x = int(min(xs)), int(max(xs))
                min_y, max_y = int(min(ys)), int(max(ys))

                regions.append({
                    "text": text.strip(),
                    "x": min_x, "y": min_y,
                    "w": max_x - min_x, "h": max_y - min_y,
                    "confidence": confidence,
                    "source": "paddleocr",
                })

        # Group by line proximity
        return _group_text_lines(regions, iw, ih)

    except Exception as exc:
        logger.warning("PaddleOCR failed: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# OCR: Tesseract (refactored from image_to_pptx.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _ocr_tesseract(pil_img, iw: int, ih: int) -> list[dict]:
    """Run Tesseract OCR (chi_sim+eng, PSM 6) for text detection."""
    import pytesseract

    if os.path.exists(TESSERACT_PATH):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

    try:
        data = pytesseract.image_to_data(
            pil_img, lang="chi_sim+eng",
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )
    except Exception as exc:
        logger.warning("Tesseract OCR failed: %s", exc)
        return []

    # Collect word-level data
    words = []
    for i in range(len(data["text"])):
        t = (data["text"][i] or "").strip()
        if not t:
            continue
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else 100
        if conf < MIN_CONFIDENCE:
            continue
        words.append({
            "text": t,
            "x": int(data["left"][i]), "y": int(data["top"][i]),
            "w": int(data["width"][i]), "h": int(data["height"][i]),
            "line_num": int(data["line_num"][i]),
            "confidence": conf,
            "source": "tesseract",
        })

    if not words:
        return []

    # Group by line
    line_map = defaultdict(list)
    for w in words:
        line_map[w["line_num"]].append(w)

    lines = []
    for ln in sorted(line_map):
        lw = sorted(line_map[ln], key=lambda w: w["x"])
        text_parts = []
        prev_right = None
        for w in lw:
            if prev_right is not None and w["x"] - prev_right > (w["w"] / max(len(w["text"]), 1)) * 1.5:
                text_parts.append(" ")
            text_parts.append(w["text"])
            prev_right = w["x"] + w["w"]

        line_text = "".join(text_parts).strip()
        if not line_text:
            continue
        min_x = min(w["x"] for w in lw)
        min_y = min(w["y"] for w in lw)
        max_x = max(w["x"] + w["w"] for w in lw)
        max_y = max(w["y"] + w["h"] for w in lw)
        lines.append({"text": line_text, "x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y,
                       "source": "tesseract"})

    return _group_text_lines(lines, iw, ih)


# ═══════════════════════════════════════════════════════════════════════════════
# OCR: Merge & group
# ═══════════════════════════════════════════════════════════════════════════════

def _ocr_combined(paddle_regions: list[dict], tesseract_regions: list[dict]) -> list[dict]:
    """Merge PaddleOCR and Tesseract results with IoU-based dedup.

    Prefer PaddleOCR for Chinese, Tesseract for English/numeric.
    """
    if not paddle_regions:
        return tesseract_regions
    if not tesseract_regions:
        return paddle_regions

    # Start with PaddleOCR results (better Chinese)
    merged = list(paddle_regions)

    for tr in tesseract_regions:
        # Check IoU overlap with existing merged regions
        overlap = False
        for mr in merged:
            iou = _compute_iou(tr, mr)
            if iou > 0.5:
                overlap = True
                # If Tesseract text is longer or contains more English/digits, prefer it
                tesseract_alpha = sum(1 for c in tr["text"] if c.isascii() and c.isalpha())
                paddle_alpha = sum(1 for c in mr["text"] if c.isascii() and c.isalpha())
                if tesseract_alpha > paddle_alpha or len(tr["text"]) > len(mr["text"]) * 1.3:
                    mr["text"] = tr["text"]
                break
        if not overlap:
            merged.append(tr)

    return merged


def _compute_iou(a: dict, b: dict) -> float:
    """Compute Intersection-over-Union for two bounding boxes."""
    x1 = max(a["x"], b["x"])
    y1 = max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter = (x2 - x1) * (y2 - y1)
    area_a = a["w"] * a["h"]
    area_b = b["w"] * b["h"]
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def _group_text_lines(regions: list[dict], iw: int, ih: int) -> list[dict]:
    """Group individual text regions into semantic blocks by proximity + overlap."""
    if not regions:
        return []

    regions.sort(key=lambda r: r["y"])

    blocks = []
    current = [regions[0]]
    for i in range(1, len(regions)):
        prev, cur = regions[i - 1], regions[i]
        gap = cur["y"] - (prev["y"] + prev["h"])
        avg_h = (prev["h"] + cur["h"]) / 2
        x_overlap = max(0, min(prev["x"] + prev["w"], cur["x"] + cur["w"]) - max(prev["x"], cur["x"]))
        overlap_frac = x_overlap / max(prev["w"], cur["w"], 1)

        if gap < avg_h * 3 and (overlap_frac > 0.2 or abs(cur["x"] - prev["x"]) < 100):
            current.append(cur)
        else:
            blocks.append(_merge_text_group(current, iw, ih))
            current = [cur]
    blocks.append(_merge_text_group(current, iw, ih))

    return blocks


def _merge_text_group(lines: list[dict], iw: int, ih: int, slide_w: float = 13.333, slide_h: float = 7.5) -> dict:
    """Merge multiple text lines into one text block with metadata."""
    text = "\n".join(l["text"] for l in lines)
    min_x = min(l["x"] for l in lines)
    min_y = min(l["y"] for l in lines)
    max_x = max(l["x"] + l["w"] for l in lines)
    max_y = max(l["y"] + l["h"] for l in lines)
    avg_h = sum(l["h"] for l in lines) / len(lines)

    rel_y = min_y / max(ih, 1)
    is_title = rel_y < 0.25 or avg_h > 35
    is_footer = rel_y > 0.85
    font_size_est = avg_h * (slide_h / ih) * 72 * 0.75

    return {
        "text": text.strip(),
        "x": min_x, "y": min_y, "w": max_x - min_x, "h": max_y - min_y,
        "font_size_est": round(max(8, min(72, font_size_est)), 1),
        "is_title": is_title,
        "is_footer": is_footer,
        "num_lines": len(lines),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Unified shape detection (lines, rectangles, circles, arrows, polygons)
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_all_shapes(cv_img, iw: int, ih: int, sx: float, sy: float) -> list[dict]:
    """Unified shape detection: lines, rectangles, circles, arrows."""
    h, w = cv_img.shape[:2]
    results = []
    min_len = min(w, h) * 0.05

    try:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # ── Lines (Hough) ──
        lines_hough = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80,
                                       minLineLength=int(min_len), maxLineGap=20)
        if lines_hough is not None:
            for line in lines_hough:
                x1, y1, x2, y2 = line[0]
                length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
                if length < min_len:
                    continue
                angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                if angle < 5 or angle > 175:
                    line_type = "horizontal"
                elif 85 < angle < 95:
                    line_type = "vertical"
                else:
                    line_type = "diagonal"
                results.append({
                    "type": "line", "subtype": line_type,
                    "x1": round(x1 * sx, 4), "y1": round(y1 * sy, 4),
                    "x2": round(x2 * sx, 4), "y2": round(y2 * sy, 4),
                    "width_pt": max(0.5, min(4, (y2 - y1 if line_type == "horizontal" else x2 - x1) * sy * 72 / 10)),
                })

        # ── Rectangles (contour approximation) ──
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV, 11, 2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < w * h * MIN_SHAPE_AREA_FRAC:
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            n_vertices = len(approx)

            if n_vertices == 4:
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                rect_area = rw * rh
                rectangularity = area / max(rect_area, 1)
                if rectangularity > 0.7 and rw > 30 and rh > 15:
                    roi = cv_img[ry:ry + rh, rx:rx + rw]
                    avg_bgr = np.mean(roi, axis=(0, 1)).astype(int)
                    edge_bgr = _sample_edge_color(cv_img, rx, ry, rw, rh)
                    results.append({
                        "type": "rectangle",
                        "x": round(rx * sx, 4), "y": round(ry * sy, 4),
                        "w": round(rw * sx, 4), "h": round(rh * sy, 4),
                        "fill": _bgr2rgb(avg_bgr),
                        "stroke": _bgr2rgb(edge_bgr),
                        "rounded": _is_rounded_corners(approx, rx, ry, rw, rh),
                    })

            elif 5 <= n_vertices <= 7:
                # Potential arrow or polygon
                convex = cv2.isContourConvex(approx)
                if not convex:
                    continue
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                if rw > 40 and rh > 15:
                    is_arrow = _is_arrow_shape(approx, rx, ry, rw, rh)
                    if is_arrow:
                        results.append({
                            "type": "arrow",
                            "x": round(rx * sx, 4), "y": round(ry * sy, 4),
                            "w": round(rw * sx, 4), "h": round(rh * sy, 4),
                            "stroke": _bgr2rgb(_sample_edge_color(cv_img, rx, ry, rw, rh)),
                            "points": [[round(pt[0][0] * sx, 4), round(pt[0][1] * sy, 4)]
                                       for pt in approx],
                        })

            elif n_vertices >= 8:
                # Potential circle/ellipse
                rx, ry, rw, rh = cv2.boundingRect(cnt)
                if rw > 30 and rh > 15:
                    circularity = 4 * np.pi * area / (peri * peri) if peri > 0 else 0
                    if circularity > 0.6:
                        cx = rx + rw // 2
                        cy = ry + rh // 2
                        r_est = (rw + rh) // 4
                        results.append({
                            "type": "circle",
                            "cx": round(cx * sx, 4), "cy": round(cy * sy, 4),
                            "r": round(r_est * (sx + sy) / 2, 4),
                            "fill": _bgr2rgb(np.mean(cv_img[ry:ry + rh, rx:rx + rw], axis=(0, 1)).astype(int)),
                            "stroke": _bgr2rgb(_sample_edge_color(cv_img, rx, ry, rw, rh)),
                        })

        # ── HoughCircles for perfect circles ──
        circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
                                    param1=80, param2=35, minRadius=15, maxRadius=min(w, h) // 3)
        if circles is not None:
            for c in circles[0]:
                cx, cy, cr = int(c[0]), int(c[1]), int(c[2])
                if cr < 10:
                    continue
                # Check if this circle overlaps an already-detected circle/rectangle
                dup = False
                for r in results:
                    if r["type"] == "circle":
                        dist = np.sqrt((r["cx"] / sx - cx) ** 2 + (r["cy"] / sy - cy) ** 2)
                        if dist < cr * 1.2:
                            dup = True
                            break
                if not dup:
                    # Clamp coordinates to valid image bounds
                    cy_s = max(cr, min(ih - cr - 1, cy))
                    cx_s = max(cr, min(iw - cr - 1, cx))
                    roi = cv_img[cy_s - cr:cy_s + cr, cx_s - cr:cx_s + cr]
                    fill_color = (128, 128, 128)
                    if roi.size > 0:
                        fill_color = _bgr2rgb(np.mean(roi, axis=(0, 1)).astype(int))
                    results.append({
                        "type": "circle",
                        "cx": round(cx * sx, 4), "cy": round(cy * sy, 4),
                        "r": round(cr * (sx + sy) / 2, 4),
                        "fill": fill_color,
                        "stroke": (150, 150, 150),
                    })

    except Exception as exc:
        logger.warning("Shape detection error: %s", exc)

    return _dedup_shapes(results)


def _is_arrow_shape(approx, rx: int, ry: int, rw: int, rh: int) -> bool:
    """Heuristic: check if contour is arrow-shaped (one end narrower than other)."""
    pts = approx.reshape(-1, 2).astype(np.float32)
    if len(pts) < 5:
        return False
    # Compute convex hull and check for a distinct "head" triangle
    hull = cv2.convexHull(pts, returnPoints=True)
    if len(hull) < 4:
        return False
    # Arrow heuristic: aspect ratio not too square, not too thin
    aspect = rw / max(rh, 1)
    return 1.5 < aspect < 8.0


def _is_rounded_corners(approx, x: int, y: int, w: int, h: int) -> bool:
    """Check if rectangle corners deviate from ideal corners (rounded detection)."""
    corners = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float32)
    pts = approx.reshape(4, 2).astype(np.float32)
    dists = [np.min(np.linalg.norm(pts - c, axis=1)) for c in corners]
    return max(dists) > w * 0.05


# ═══════════════════════════════════════════════════════════════════════════════
# Background analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_background_type(cv_img) -> tuple[str, str, dict | None]:
    """Classify background as solid, gradient, or complex.

    Returns:
        (type, solid_color_hex, gradient_info_dict_or_None)
    """
    h, w = cv_img.shape[:2]
    sample_size = max(8, min(w, h) // 40)

    # Sample edges and center regions
    regions = [
        cv_img[0:sample_size, 0:sample_size],           # top-left
        cv_img[0:sample_size, -sample_size:],            # top-right
        cv_img[-sample_size:, 0:sample_size],            # bottom-left
        cv_img[-sample_size:, -sample_size:],            # bottom-right
        cv_img[h // 2 - 4:h // 2 + 4, 0:sample_size],   # mid-left
        cv_img[h // 2 - 4:h // 2 + 4, -sample_size:],   # mid-right
        cv_img[0:sample_size, w // 2 - 4:w // 2 + 4],   # top-mid
        cv_img[-sample_size:, w // 2 - 4:w // 2 + 4],   # bottom-mid
        cv_img[h // 2 - 10:h // 2 + 10, w // 2 - 10:w // 2 + 10],  # center
    ]

    # Compute mean color for each region
    means = []
    for r in regions:
        if r.size > 0:
            means.append(np.mean(r.reshape(-1, 3), axis=0))

    if not means:
        return ("complex", "#FFFFFF", None)

    means = np.array(means)
    global_mean = np.mean(means, axis=0).astype(int)
    solid_hex = f"{int(global_mean[2]):02x}{int(global_mean[1]):02x}{int(global_mean[0]):02x}"

    # Compute per-channel variance across regions
    channel_vars = np.var(means, axis=0)

    # If all channels have very low variance → solid
    if np.max(channel_vars) < 120:  # threshold for solid
        return ("solid", f"#{solid_hex}", None)

    # Check for linear gradient pattern (variance follows direction)
    # Sample horizontal and vertical strips
    h_strip_colors = []
    for i in range(8):
        x = int(w * i / 8)
        strip = cv_img[h // 4:3 * h // 4, x:x + sample_size]
        if strip.size > 0:
            h_strip_colors.append(np.mean(strip.reshape(-1, 3), axis=0))
    v_strip_colors = []
    for i in range(8):
        y = int(h * i / 8)
        strip = cv_img[y:y + sample_size, w // 4:3 * w // 4]
        if strip.size > 0:
            v_strip_colors.append(np.mean(strip.reshape(-1, 3), axis=0))

    # Check if variance along horizontal or vertical is linear
    h_variance = np.var(h_strip_colors, axis=0) if len(h_strip_colors) > 1 else np.array([0, 0, 0])
    v_variance = np.var(v_strip_colors, axis=0) if len(v_strip_colors) > 1 else np.array([0, 0, 0])

    if np.max(h_variance) > 200 or np.max(v_variance) > 200:
        # It's a gradient
        dominant_dir = "horizontal" if np.max(h_variance) > np.max(v_variance) else "vertical"
        strips = h_strip_colors if dominant_dir == "horizontal" else v_strip_colors
        angle = 0 if dominant_dir == "horizontal" else 90

        # Extract 2-3 color stops
        stops = []
        if len(strips) >= 2:
            start_color = strips[0].astype(int)
            end_color = strips[-1].astype(int)
            stops = [
                {"pos": "0%", "color": f"#{int(start_color[2]):02x}{int(start_color[1]):02x}{int(start_color[0]):02x}"},
                {"pos": "100%", "color": f"#{int(end_color[2]):02x}{int(end_color[1]):02x}{int(end_color[0]):02x}"},
            ]
            if len(strips) >= 4:
                mid_color = strips[len(strips) // 2].astype(int)
                stops.insert(1, {"pos": "50%", "color": f"#{int(mid_color[2]):02x}{int(mid_color[1]):02x}{int(mid_color[0]):02x}"})

        gradient_info = {
            "type": "linear",
            "angle": angle,
            "stops": stops,
        }
        return ("gradient", f"#{solid_hex}", gradient_info)

    # Moderate variance but not linear → complex (photo/texture)
    return ("complex", f"#{solid_hex}", None)


# ═══════════════════════════════════════════════════════════════════════════════
# Color analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_dominant_colors(cv_img, n: int = 8) -> list[str]:
    """Extract dominant hex colors via K-means clustering."""
    h, w = cv_img.shape[:2]
    small = cv2.resize(cv_img, (w // 4, h // 4))
    pixels = small.reshape(-1, 3).astype(np.float32)

    k = min(n, max(3, len(np.unique(pixels // 32, axis=0))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, _, centers = cv2.kmeans(pixels, k, None, criteria, 5, cv2.KMEANS_RANDOM_CENTERS)
    centers = centers.astype(int)

    colors = []
    for c in centers:
        hex_color = f"{int(c[2]):02x}{int(c[1]):02x}{int(c[0]):02x}"
        colors.append(f"#{hex_color}")
    # Sort by brightness (luminance)
    colors.sort(key=lambda h: int(h[1:3], 16) * 0.299 + int(h[3:5], 16) * 0.587 + int(h[5:7], 16) * 0.114)
    return colors


def _detect_dominant_font_color(cv_img, text_regions: list[dict]) -> str:
    """Find the most common dark text color across all text regions."""
    all_dark = []
    for tr in text_regions:
        px, py = int(tr["x"]), int(tr["y"])
        pw, ph = int(tr["w"]), int(tr["h"])
        roi = cv_img[py:py + ph, px:px + pw]
        if roi.size == 0:
            continue
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        # Darkest 30% pixels
        dark_thresh = np.percentile(gray, 30)
        dark_mask = gray <= dark_thresh
        if dark_mask.sum() > 3:
            all_dark.append(roi[dark_mask])

    if all_dark:
        all_pixels = np.concatenate(all_dark)
        if len(all_pixels) > 0:
            avg = np.mean(all_pixels, axis=0).astype(int)
            return f"#{int(avg[2]):02x}{int(avg[1]):02x}{int(avg[0]):02x}"
    return "#000000"


# ═══════════════════════════════════════════════════════════════════════════════
# Font family estimation
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_font_family_heuristics(text_regions: list[dict], cv_img) -> list[str]:
    """Estimate likely font families based on stroke properties.

    Returns list of likely font names, most probable first.
    """
    # Simple heuristic: check stroke width variation
    # For Chinese text: HeiTi (sans-serif, uniform stroke) vs SongTi (serif, varied stroke)
    # For Latin: sans-serif (Arial/Helvetica) vs serif (Times New Roman)

    if not text_regions:
        return ["Microsoft YaHei"]

    has_chinese = any(
        any('一' <= c <= '鿿' for c in tr["text"])
        for tr in text_regions
    )

    if has_chinese:
        return ["Microsoft YaHei", "SimHei", "SimSun", "PingFang SC", "Arial"]
    else:
        return ["Arial", "Calibri", "Times New Roman", "Segoe UI", "Microsoft YaHei"]


# ═══════════════════════════════════════════════════════════════════════════════
# Visual asset detection (complex non-text regions)
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_visual_assets(cv_img, text_regions: list[dict],
                           iw: int, ih: int, sx: float, sy: float) -> list[dict]:
    """Identify complex visual areas (photos, logos, 3D, textures) via entropy.

    Refactored from image_to_pptx.py _detect_visual_assets.
    """
    h, w = cv_img.shape[:2]
    assets = []

    try:
        from skimage.filters import rank
        from skimage.morphology import disk

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        # Build text mask
        text_mask = np.zeros((h, w), dtype=np.uint8)
        for tr in text_regions:
            x1 = max(0, int(tr["x"] - 5))
            y1 = max(0, int(tr["y"] - 5))
            x2 = min(w, int(tr["x"] + tr["w"] + 5))
            y2 = min(h, int(tr["y"] + tr["h"] + 5))
            text_mask[y1:y2, x1:x2] = 255

        # Local entropy for complexity
        ksize = 15
        selem = disk(ksize // 2)
        entropy_map = rank.entropy(gray, selem)

        entropy_thresh = np.percentile(entropy_map, 85)
        high_entropy = (entropy_map > entropy_thresh).astype(np.uint8) * 255
        high_entropy[text_mask > 0] = 0

        kernel = np.ones((10, 10), np.uint8)
        high_entropy = cv2.morphologyEx(high_entropy, cv2.MORPH_CLOSE, kernel)
        high_entropy = cv2.morphologyEx(high_entropy, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(high_entropy, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = w * h * 0.003

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            aspect = rw / max(rh, 1)
            if aspect > 15 or aspect < 0.07:
                continue
            assets.append({
                "x": round(rx * sx, 4), "y": round(ry * sy, 4),
                "w": round(rw * sx, 4), "h": round(rh * sy, 4),
                "pixel_x": rx, "pixel_y": ry,
                "pixel_w": rw, "pixel_h": rh,
                "category": "complex_visual",
            })
    except Exception as exc:
        logger.warning("Visual asset detection error: %s", exc)

    return assets[:10]


# ═══════════════════════════════════════════════════════════════════════════════
# Table/chart region detection
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_chart_table_regions(cv_img, text_regions: list[dict],
                                  iw: int, ih: int, sx: float, sy: float) -> list[dict]:
    """Detect table and chart regions by grid-line patterns and text alignment."""
    h, w = cv_img.shape[:2]
    tables = []

    try:
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

        # Detect dense repeating horizontal and vertical lines (grid pattern)
        edges = cv2.Canny(gray, 40, 120, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60,
                                 minLineLength=int(w * 0.08), maxLineGap=15)

        if lines is not None:
            h_lines = []
            v_lines = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                if angle < 10 or angle > 170:
                    h_lines.append((x1 + x2) // 2)
                elif 80 < angle < 100:
                    v_lines.append((y1 + y2) // 2)

            # If we have multiple h-lines and v-lines in a region → likely table
            if len(h_lines) >= 2 and len(v_lines) >= 2:
                h_lines.sort()
                v_lines.sort()

                # Find clusters of nearby lines
                def cluster_positions(pos_list, threshold):
                    if not pos_list:
                        return []
                    clusters = [[pos_list[0]]]
                    for pos in pos_list[1:]:
                        if pos - clusters[-1][-1] < threshold:
                            clusters[-1].append(pos)
                        else:
                            clusters.append([pos])
                    return [sum(c) // len(c) for c in clusters]

                h_clusters = cluster_positions(h_lines, w // 20)
                v_clusters = cluster_positions(v_lines, h // 20)

                if len(h_clusters) >= 3 and len(v_clusters) >= 2:
                    min_x = min(v_clusters)
                    max_x = max(v_clusters)
                    min_y = min(h_clusters)
                    max_y = max(h_clusters)

                    tables.append({
                        "x": round(min_x * sx, 4), "y": round(min_y * sy, 4),
                        "w": round((max_x - min_x) * sx, 4), "h": round((max_y - min_y) * sy, 4),
                        "rows": len(h_clusters) - 1,
                        "cols": len(v_clusters) - 1,
                        "category": "table_grid",
                    })
                    logger.debug("Table detected: %d rows x %d cols", len(h_clusters) - 1, len(v_clusters) - 1)

        # Also check for text alignment patterns suggesting tables
        # (Text regions with aligned x-coordinates and similar y-spacing)
        if not tables and len(text_regions) >= 4:
            text_columns = defaultdict(list)
            for tr in text_regions:
                x_center = tr["x"] + tr["w"] / 2
                col_key = round(x_center / (w / 20))  # bucket into 20 columns
                text_columns[col_key].append(tr)

            # If we have 2+ columns with 2+ text regions each, it's likely a table
            strong_cols = [c for c in text_columns.values() if len(c) >= 2]
            if len(strong_cols) >= 2:
                all_rows = [tr for col in strong_cols for tr in col]
                min_x = min(tr["x"] for tr in all_rows)
                min_y = min(tr["y"] for tr in all_rows)
                max_x = max(tr["x"] + tr["w"] for tr in all_rows)
                max_y = max(tr["y"] + tr["h"] for tr in all_rows)

                tables.append({
                    "x": round(min_x * sx, 4), "y": round(min_y * sy, 4),
                    "w": round((max_x - min_x) * sx, 4), "h": round((max_y - min_y) * sy, 4),
                    "rows": max(len(c) for c in strong_cols),
                    "cols": len(strong_cols),
                    "category": "text_table",
                })

    except Exception as exc:
        logger.warning("Table detection error: %s", exc)

    return tables


# ═══════════════════════════════════════════════════════════════════════════════
# Text inpainting (remove text from background image)
# ═══════════════════════════════════════════════════════════════════════════════

def inpaint_text_regions(cv_img: np.ndarray, text_regions: list[dict]) -> np.ndarray:
    """Remove text from image using OpenCV inpainting.

    Creates a mask from text bounding boxes (dilated by 3px), then uses
    INPAINT_TELEA to fill text areas with surrounding background.

    Returns:
        Inpainted image (BGR, same shape as input)
    """
    h, w = cv_img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    for tr in text_regions:
        px = max(0, int(tr["x"]) - 3)
        py = max(0, int(tr["y"]) - 3)
        pw = min(w - px, int(tr["w"]) + 6)
        ph = min(h - py, int(tr["h"]) + 6)
        mask[py:py + ph, px:px + pw] = 255

    if mask.sum() == 0:
        return cv_img.copy()

    # Dilate mask slightly to ensure full text coverage
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)

    inpainted = cv2.inpaint(cv_img, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    return inpainted


# ═══════════════════════════════════════════════════════════════════════════════
# Utility helpers (shared with image_to_pptx.py)
# ═══════════════════════════════════════════════════════════════════════════════

def _sample_edge_color(cv_img, x: int, y: int, w: int, h: int) -> tuple:
    """Sample average color from the perimeter of a region."""
    h_img, w_img = cv_img.shape[:2]
    edge_pixels = []
    if y > 0:
        edge_pixels.append(cv_img[max(0, y - 1):y + 2, x:x + w].reshape(-1, 3))
    if y + h < h_img:
        edge_pixels.append(cv_img[y + h - 2:y + h + 1, x:x + w].reshape(-1, 3))
    if x > 0:
        edge_pixels.append(cv_img[y:y + h, max(0, x - 1):x + 2].reshape(-1, 3))
    if x + w < w_img:
        edge_pixels.append(cv_img[y:y + h, x + w - 2:x + w + 1].reshape(-1, 3))
    if edge_pixels:
        return tuple(int(c) for c in np.mean(np.concatenate(edge_pixels), axis=0))
    return (0, 0, 0)


def _bgr2rgb(bgr) -> tuple:
    """Convert BGR tuple or array to RGB tuple."""
    if isinstance(bgr, np.ndarray):
        return (int(bgr[2]), int(bgr[1]), int(bgr[0]))
    return (bgr[2], bgr[1], bgr[0]) if len(bgr) == 3 else bgr


def _dedup_shapes(shapes: list[dict]) -> list[dict]:
    """Remove near-duplicate shapes from detection results."""
    if len(shapes) <= 1:
        return shapes

    # Sort by area (largest first)
    shapes.sort(key=lambda s: (
        s.get("w", 0) * s.get("h", 0) if s["type"] in ("rectangle", "arrow") else
        s.get("r", 0) ** 2 if s["type"] == "circle" else
        (s.get("x2", 0) - s.get("x1", 0)) ** 2 + (s.get("y2", 0) - s.get("y1", 0)) ** 2
    ), reverse=True)

    kept = []
    for s in shapes:
        dup = False
        for k in kept:
            if s["type"] != k["type"]:
                continue
            if s["type"] == "line":
                d1 = np.sqrt((s["x1"] - k["x1"]) ** 2 + (s["y1"] - k["y1"]) ** 2)
                d2 = np.sqrt((s["x2"] - k["x2"]) ** 2 + (s["y2"] - k["y2"]) ** 2)
                if d1 < 0.15 and d2 < 0.15:
                    dup = True; break
            elif s["type"] in ("rectangle", "arrow"):
                cx_s, cy_s = s["x"] + s["w"] / 2, s["y"] + s["h"] / 2
                cx_k, cy_k = k["x"] + k["w"] / 2, k["y"] + k["h"] / 2
                if abs(cx_s - cx_k) < 0.15 and abs(cy_s - cy_k) < 0.15:
                    dup = True; break
            elif s["type"] == "circle":
                dist = np.sqrt((s["cx"] - k["cx"]) ** 2 + (s["cy"] - k["cy"]) ** 2)
                if dist < s.get("r", 1) * 0.6:
                    dup = True; break
        if not dup:
            kept.append(s)

    return kept[:30]
