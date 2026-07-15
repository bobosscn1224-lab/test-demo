"""Phase 3: Quality calibration for DeckWeaver pipeline.

Ports render_pptx_to_png and compare_images from precise_reconstruction.py,
adapted for the LAYOUT pipeline without the CoordinateMapper abstraction.
"""
from __future__ import annotations

import logging
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SLIDE_W_IN = 13.333333
SLIDE_H_IN = 7.5
DEFAULT_RENDER_W = 1600
DEFAULT_RENDER_H = 900

POWERPOINT_PATHS = (
    r"C:\Program Files\Microsoft Office\Office15\POWERPNT.EXE",
    r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
    r"C:\Program Files (x86)\Microsoft Office\Office15\POWERPNT.EXE",
    r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
)


def _powerpoint_installed() -> bool:
    for path in POWERPOINT_PATHS:
        if os.path.exists(path):
            return True
    return False


def _powerpoint_process_ids() -> set[int]:
    import psutil
    ids: set[int] = set()
    try:
        for proc in psutil.process_iter(["pid", "name"]):
            name = proc.info["name"] or ""
            if "POWERPNT" in name.upper():
                ids.add(int(proc.info["pid"]))
    except Exception:
        pass
    return ids


def _terminate_process_tree(pid: int) -> None:
    import psutil
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.terminate()
            except Exception:
                pass
        parent.terminate()
        parent.wait(timeout=8)
    except Exception:
        pass


def _render_powerpoint_once(pptx_path: str, output_path: str, width: int, height: int) -> None:
    """Worker function run in a subprocess via python -c."""
    import pythoncom
    pythoncom.CoInitialize()
    try:
        app = None
        try:
            from win32com.client import Dispatch
            app = Dispatch("PowerPoint.Application")
            app.Visible = False
            app.DisplayAlerts = 0
            presentation = app.Presentations.Open(pptx_path, WithWindow=False)
            try:
                presentation.Slides(1).Export(output_path, "PNG", width, height)
            finally:
                presentation.Close()
        finally:
            if app is not None:
                try:
                    app.Quit()
                except Exception:
                    pass
    finally:
        pythoncom.CoUninitialize()


# ═══════════════════════════════════════════════════════════════════════════
# PPTX → PNG rendering
# ═══════════════════════════════════════════════════════════════════════════

def render_pptx_to_png(
    pptx_path: str, output_path: str,
    width: int = DEFAULT_RENDER_W, height: int = DEFAULT_RENDER_H,
) -> tuple[bool, str | None]:
    """Render slide 1 using local Microsoft PowerPoint with timeout."""
    if not _powerpoint_installed():
        return False, "PowerPoint not installed"

    existing_ppt = _powerpoint_process_ids()
    output = Path(output_path)
    output.unlink(missing_ok=True)

    code = (
        "from app.services.layout.quality import _render_powerpoint_once;"
        f"_render_powerpoint_once({pptx_path!r},{output_path!r},{int(width)},{int(height)})"
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        worker = subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parents[3]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=creation_flags,
        )
        deadline = time.monotonic() + 75
        last_size = -1
        stable_since = None
        while time.monotonic() < deadline:
            return_code = worker.poll()
            if output.exists() and output.stat().st_size > 1000:
                size = output.stat().st_size
                if size == last_size:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= 1.0:
                        break
                else:
                    last_size = size
                    stable_since = None
            if return_code is not None:
                break
            time.sleep(0.25)

        if worker.poll() is None:
            _terminate_process_tree(worker.pid)
        try:
            worker.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(worker.pid)

        new_ppt = _powerpoint_process_ids() - existing_ppt
        for pid in new_ppt:
            _terminate_process_tree(pid)

        if output.exists() and output.stat().st_size > 1000:
            return True, None
        return False, "PowerPoint render produced no valid output"
    except Exception as exc:
        logger.warning("PowerPoint rendering failed: %s", exc)
        return False, f"{exc.__class__.__name__}: {exc}"


# ═══════════════════════════════════════════════════════════════════════════
# SSIM comparison
# ═══════════════════════════════════════════════════════════════════════════

def compare_images(
    source_path: str,
    rendered_path: str,
    text_regions: list[dict[str, Any]] | None = None,
    image_width: int = 1920,
    image_height: int = 1080,
    heatmap_path: str | None = None,
    comparison_path: str | None = None,
) -> dict[str, Any]:
    """Compare source image with rendered PPTX preview using SSIM."""
    from skimage.metrics import structural_similarity

    try:
        source = _read_cv_image(source_path)
        rendered = _read_cv_image(rendered_path)
    except (ValueError, OSError):
        return {"error": "Cannot read images for comparison"}

    # Match dimensions
    if source.shape != rendered.shape:
        rendered = cv2.resize(rendered, (source.shape[1], source.shape[0]))

    gray_source = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
    gray_rendered = cv2.cvtColor(rendered, cv2.COLOR_BGR2GRAY)

    full_ssim, ssim_map = structural_similarity(gray_source, gray_rendered, full=True, data_range=255)

    edge_source = cv2.Canny(gray_source, 60, 150)
    edge_rendered = cv2.Canny(gray_rendered, 60, 150)
    edge_ssim = structural_similarity(edge_source, edge_rendered, data_range=255)

    diff = cv2.absdiff(source, rendered)
    mean_diff = float(np.mean(cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)))

    # Per-text-region SSIM
    height, width = source.shape[:2]
    text_scores: list[float] = []
    for region in (text_regions or []):
        sx = width / max(image_width, 1)
        sy = height / max(image_height, 1)
        x = int(region["x"] * sx)
        y = int(region["y"] * sy)
        w = int(region["w"] * sx)
        h = int(region["h"] * sy)
        padding = max(3, round(h * 0.35))
        x1, y1 = max(0, x - padding), max(0, y - padding)
        x2, y2 = min(width, x + w + padding), min(height, y + h + padding)
        a = gray_source[y1:y2, x1:x2]
        b = gray_rendered[y1:y2, x1:x2]
        if min(a.shape[:2]) < 7:
            continue
        try:
            text_scores.append(float(structural_similarity(a, b, data_range=255)))
        except ValueError:
            continue

    text_ssim = float(np.mean(text_scores)) if text_scores else float(full_ssim)
    composite = (
        float(full_ssim) * 0.42
        + float(edge_ssim) * 0.22
        + text_ssim * 0.30
        + max(0.0, 1.0 - mean_diff / 255.0) * 0.06
    )

    if heatmap_path:
        error = np.clip((1.0 - ssim_map) * 255 * 2.2, 0, 255).astype(np.uint8)
        heatmap = cv2.applyColorMap(error, cv2.COLORMAP_JET)
        overlay = cv2.addWeighted(rendered, 0.58, heatmap, 0.42, 0)
        cv2.imencode(".png", overlay)[1].tofile(heatmap_path)

    if comparison_path:
        label_h = 44
        comp = np.full((height + label_h, width * 2 + 16, 3), 238, dtype=np.uint8)
        comp[label_h:, :width] = source
        comp[label_h:, width + 16:] = rendered
        cv2.putText(comp, "ORIGINAL", (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (8, 118, 111), 2, cv2.LINE_AA)
        cv2.putText(comp, "PPTX RENDER", (width + 32, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (8, 118, 111), 2, cv2.LINE_AA)
        cv2.imencode(".png", comp)[1].tofile(comparison_path)

    return {
        "ssim": round(float(full_ssim), 4),
        "edge_ssim": round(float(edge_ssim), 4),
        "text_ssim": round(text_ssim, 4),
        "mean_diff": round(mean_diff, 2),
        "score": round(float(composite), 4),
        "quality": (
            "strong" if composite >= 0.86
            else "good" if composite >= 0.76
            else "fair" if composite >= 0.64
            else "needs_review"
        ),
    }


def _read_cv_image(path: str) -> np.ndarray:
    buf = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Cannot decode: {path}")
    return img


# ═══════════════════════════════════════════════════════════════════════════
# Calibration loop
# ═══════════════════════════════════════════════════════════════════════════

async def calibrate(
    pptx_path: str,
    source_image_path: str,
    text_items: list[dict[str, Any]],
    work_dir: Path,
    max_passes: int = 2,
    target_score: float = 0.76,
) -> dict[str, Any]:
    """Run quality calibration: render → compare → adjust → repeat.

    Returns calibration report with best score and adjustments made.
    """
    import asyncio

    if not _powerpoint_installed():
        return {"method": "skipped", "reason": "PowerPoint not installed"}

    calibrations = []
    current_pptx = pptx_path
    best_score = 0.0
    best_pass = 0

    for pass_num in range(max_passes + 1):
        render_path = str(work_dir / f"calibrate_pass{pass_num}.png")

        ok, err = await asyncio.to_thread(
            render_pptx_to_png, current_pptx, render_path,
        )
        if not ok:
            calibrations.append({"pass": pass_num, "render_error": err})
            break

        result = await asyncio.to_thread(
            compare_images,
            source_image_path, render_path, text_items,
            heatmap_path=str(work_dir / f"heatmap_pass{pass_num}.png") if pass_num == 0 else None,
            comparison_path=str(work_dir / f"comparison_pass{pass_num}.png") if pass_num <= 1 else None,
        )
        score = result.get("score", 0)
        calibrations.append({"pass": pass_num, **result})

        if score > best_score:
            best_score = score
            best_pass = pass_num

        if score >= target_score:
            break

        # If score is fair/poor, adjust font scaling for text items
        if pass_num < max_passes and score < target_score:
            adjustment = _compute_font_adjustment(result, pass_num)
            if adjustment != 1.0:
                for ti in text_items:
                    current_size = ti.get("font_size", 13)
                    ti["font_size"] = max(6, min(48, current_size * adjustment))

    return {
        "passes": calibrations,
        "best_score": best_score,
        "best_pass": best_pass,
        "calibrated": best_score >= target_score,
    }


def _compute_font_adjustment(result: dict[str, Any], pass_num: int) -> float:
    """Compute font size adjustment based on SSIM results."""
    text_ssim = result.get("text_ssim", 0.8)
    mean_diff = result.get("mean_diff", 20)

    if text_ssim >= 0.85:
        return 1.0
    if text_ssim < 0.65:
        # Text isn't matching well — try smaller font
        return 0.92 if pass_num == 0 else 0.95
    if mean_diff > 30:
        return 0.94
    return 0.97 if pass_num == 0 else 1.0
