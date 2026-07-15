"""Batch image-to-PPTX conversion service.

Processes multiple images sequentially, then merges all slides
into a single combined PPTX file.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
PIPELINE_VERSION = "batch_v1"


async def batch_convert(
    image_paths: list[str],
    session_id: str = "",
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Convert multiple images to a single combined PPTX.

    Each image becomes one slide. Images are processed in order.
    Returns dict with combined pptx path, url, and per-page results.
    """
    if not image_paths:
        return {"error": "No images provided"}

    out_dir = Path(output_dir) if output_dir else Path("data/outputs")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sid = (session_id or uuid.uuid4().hex)[:8]
    run_id = uuid.uuid4().hex[:6]
    stem = f"ppt_batch_{sid}_{run_id}"

    from app.services.deckweaver_service import convert_image_to_pptx

    results = []
    errors = []
    individual_pptx: list[str] = []

    total = len(image_paths)
    for idx, img_path in enumerate(image_paths, start=1):
        if not os.path.exists(img_path):
            errors.append({"page": idx, "file": os.path.basename(img_path), "error": "File not found"})
            continue

        logger.info("Batch [%d/%d]: %s", idx, total, os.path.basename(img_path))
        try:
            r = await convert_image_to_pptx(img_path, session_id=f"{session_id}_p{idx}", output_dir=str(out_dir))
        except Exception as exc:
            errors.append({"page": idx, "file": os.path.basename(img_path), "error": str(exc)})
            continue

        if r.get("error"):
            errors.append({"page": idx, "file": os.path.basename(img_path), "error": r["error"]})
            continue

        individual_pptx.append(r["path"])
        results.append({
            "page": idx,
            "file": os.path.basename(img_path),
            "text_items": r.get("report", {}).get("text_items", 0),
            "success": True,
        })

    if not individual_pptx:
        return {
            "error": "All conversions failed",
            "errors": errors,
            "results": results,
        }

    # ── Merge all individual PPTX into one ──
    from app.services.batch_job_manager import _merge_pptx_files
    combined_path = out_dir / f"{stem}.pptx"
    try:
        await asyncio.to_thread(_merge_pptx_files, individual_pptx, str(combined_path))
    except Exception as exc:
        return {"error": f"Merge failed: {exc}", "results": results, "errors": errors}

    return {
        "filename": combined_path.name,
        "pipeline_version": PIPELINE_VERSION,
        "path": str(combined_path),
        "url": f"/api/skills/download/{combined_path.name}",
        "page_count": len(individual_pptx),
        "total_pages": total,
        "results": results,
        "errors": errors,
    }
