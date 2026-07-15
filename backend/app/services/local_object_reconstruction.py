"""Local object-first image-to-PPTX reconstruction.

This is the stable Step-4 entry point for screenshot/mockup -> editable PPTX.
It deliberately does not call an LLM.  The implementation reuses the mature
measurement/building primitives in ``precise_reconstruction`` but freezes the
runtime policy to the mode that best matches the product requirement:

* native slide background instead of a full-slide bitmap;
* native PowerPoint shapes for cards, pills, rules and simple geometry;
* independently movable PNG crops for icons/logos/complex marks;
* editable PowerPoint text boxes for main OCR text;
* render/compare calibration when the local rendering backend is available.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.services import precise_reconstruction as precise


PIPELINE_VERSION = "local_object_verified_v1"


async def reconstruct(
    image_path: str,
    session_id: str = "",
    output_dir: str | None = None,
    *,
    render_preview: bool = True,
    max_calibration_passes: int = 3,
) -> dict[str, Any]:
    """Run the local object-first reconstruction policy.

    ``precise_reconstruction`` still exposes optional LLM metadata refinement
    and tiled background fallbacks.  This wrapper disables both by default so
    the PPT Maker skill has one deterministic, local, object-oriented path.
    """
    previous_bg_mode = os.environ.get("PPT_PRECISE_BACKGROUND_MODE")
    os.environ["PPT_PRECISE_BACKGROUND_MODE"] = "native"
    try:
        result = await precise.reconstruct(
            image_path,
            session_id=session_id or "object",
            output_dir=output_dir,
            refine_with_llm=False,
            render_preview=render_preview,
            max_calibration_passes=max_calibration_passes,
        )
    finally:
        if previous_bg_mode is None:
            os.environ.pop("PPT_PRECISE_BACKGROUND_MODE", None)
        else:
            os.environ["PPT_PRECISE_BACKGROUND_MODE"] = previous_bg_mode

    if not isinstance(result, dict) or result.get("error"):
        return result

    result["pipeline_version"] = PIPELINE_VERSION
    report = result.get("report")
    if isinstance(report, dict):
        report["pipeline_version"] = PIPELINE_VERSION
        report["model_backend"] = "none: local OCR + OpenCV + python-pptx only"
        report["llm_refinement"] = {
            "used": False,
            "reason": "disabled_by_local_object_reconstruction",
        }
        report["wrapper"] = {
            "name": PIPELINE_VERSION,
            "base_pipeline": precise.PIPELINE_VERSION,
            "policy": "native background + native shapes + movable icon crops + editable text",
        }
        report_path = result.get("report_path")
        if report_path:
            try:
                Path(report_path).write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
    return result
