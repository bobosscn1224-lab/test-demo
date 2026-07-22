"""PPT Maker Feature API — Collage generation endpoints.

All image generation is delegated to ImageGenerationService.
This module handles: routing, state persistence, response formatting.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services._paths import PUBLIC_DIR
from app.services.collage_generation_state import (
    is_complete_collage_batch,
    load_generation_state,
    save_generation_state,
)
from app.services.image_generation import (
    ImageGenerationService,
    GenerationResult,
    CollageBatchResult,
    build_collage_prompts,
)
from app.api.ppt_maker.projects import _load, _save, _now
from app.api.ppt_maker.models import (
    CollageGenerateResponse, CollageItem, CollageSelectRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-maker"], redirect_slashes=False)


# ── Helpers ──────────────────────────────────────────────────────────────

def _download_url(filename: str) -> str:
    return f"/api/skills/download/{filename}"


def _result_to_collage_item(result: GenerationResult) -> dict:
    return {
        "label": result.label,
        "filename": result.filename,
        "path": result.path,
        "download_url": result.download_url,
    }


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/image-backends")
async def list_image_backends() -> list[dict]:
    """List ALL available image generation backends."""
    from app.services.image_gen_service import list_configured_backends
    return list_configured_backends()


@router.get("/projects/{project_id}/collages/preview")
async def preview_collage_prompts(project_id: str) -> dict:
    """Preview the 3 collage generation prompts WITHOUT generating images."""
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲。")

    prompt = build_collage_prompts(project)

    return {
        "success": True,
        "project_id": project_id,
        "prompts": [
            {"label": "all", "prompt": prompt, "char_count": len(prompt)},
        ],
    }


@router.post("/projects/{project_id}/collages", response_model=CollageGenerateResponse)
async def generate_collages(project_id: str) -> CollageGenerateResponse:
    """Generate 3 visual collage variants (A/B/C) concurrently.

    Partial success is supported: succeeded variants are saved immediately,
    failed ones can be regenerated individually.
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲后再生成拼图。")

    os.makedirs(str(PUBLIC_DIR), exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    started_at = _now()

    save_generation_state(project_id, {
        "run_id": run_id, "status": "generating", "started_at": started_at,
        "message": "正在并发生成三套风格方案...",
    })

    def on_batch_progress(event: dict) -> None:
        # Save completed collages immediately so frontend polling can see them
        completed = event.get("completed", [])
        if completed:
            existing = {c.get("label", ""): c for c in project.get("collages", [])}
            for item in completed:
                existing[item["label"]] = item
            project["collages"] = sorted(existing.values(), key=lambda c: c["label"])
            project["updated_at"] = _now()
            project["status"] = "collages_generated"
            _save(project_id, project)
        save_generation_state(project_id, {
            "run_id": run_id, "status": event.get("status", "generating"),
            "started_at": started_at,
            "message": event.get("message", ""),
        })

    def on_variant_progress(event: dict) -> None:
        save_generation_state(project_id, {
            "run_id": run_id,
            "status": "generating",
            "current_label": event.get("label", ""),
            "attempt": int(event.get("attempt") or 1),
            "completed_labels": [],
            "started_at": started_at,
            "message": event.get("message", ""),
            "variants": {
                event.get("label", ""): {
                    "status": event.get("status", "generating"),
                    "attempt": int(event.get("attempt") or 1),
                    "message": event.get("message", ""),
                }
            },
        })

    try:
        batch: CollageBatchResult = await ImageGenerationService.generate_collage_variants(
            project,
            project_id=project_id,
            on_batch_progress=on_batch_progress,
            on_variant_progress=on_variant_progress,
        )
    except Exception as exc:
        state = load_generation_state(project_id)
        save_generation_state(project_id, {**state, "status": "failed", "error": str(exc)})
        logger.error("Collage batch failed for project %s: %s", project_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    if not batch.success:
        save_generation_state(project_id, {
            "run_id": batch.run_id, "status": "failed",
            "error": "; ".join(batch.errors.values()),
            "message": "风格方案生成失败",
        })
        raise HTTPException(status_code=500, detail="风格方案生成失败：" + "; ".join(batch.errors.values()))

    # Single image containing all 3 variants
    collages_response = [
        CollageItem(label=r.label, filename=r.filename, download_url=r.download_url)
        for r in batch.collages
    ]

    project["collages"] = [_result_to_collage_item(r) for r in batch.collages]
    project["collage_run_id"] = batch.run_id
    project["collage_visual_directions"] = batch.visual_directions
    project["status"] = "collages_generated"
    project["updated_at"] = _now()
    _save(project_id, project)

    save_generation_state(project_id, {
        "run_id": batch.run_id, "status": "completed",
        "message": "三套风格方案已生成（在同一张图上）",
    })
    logger.info("Collage generated for project %s", project_id)
    return CollageGenerateResponse(
        success=True,
        project_id=project_id,
        collages=collages_response,
        message="三版拼图已生成在同一张图上，请横滑查看并选择方案 A / B / C。",
    )


@router.get("/projects/{project_id}/collages/progress")
async def get_collage_progress(project_id: str) -> dict:
    try:
        _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return load_generation_state(project_id)


@router.put("/projects/{project_id}/collages/select", response_model=CollageGenerateResponse)
async def select_collage(project_id: str, data: CollageSelectRequest) -> CollageGenerateResponse:
    """Select which collage variant (A/B/C) to use as the design master."""
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    selected = data.selected_collage.upper().strip()

    if not is_complete_collage_batch(
        project.get("collages", []), str(project.get("collage_run_id") or "")
    ):
        raise HTTPException(status_code=400, detail="当前风格方案批次不完整，请重新生成 A/B/C。")

    existing_labels = {c.get("label", "") for c in project.get("collages", [])}
    if selected not in existing_labels:
        raise HTTPException(
            status_code=400,
            detail=f"方案 {selected} 不在已生成的拼图中。可用方案：{sorted(existing_labels)}",
        )

    project["selected_collage"] = selected
    project["updated_at"] = _now()
    _save(project_id, project)

    logger.info("Selected collage %s for project %s", selected, project_id)

    collages_response = [
        CollageItem(
            label=c.get("label", ""), filename=c.get("filename", ""),
            download_url=_download_url(c.get("filename", "")),
        )
        for c in project.get("collages", [])
    ]
    return CollageGenerateResponse(
        success=True, project_id=project_id, collages=collages_response,
        message=f"已选择方案 {selected}，可以进入逐页生成阶段。",
    )


class SingleCollageRequest(BaseModel):
    feedback: str = ""


@router.post("/projects/{project_id}/collages/{label}", response_model=CollageGenerateResponse)
async def generate_single_collage(project_id: str, label: str) -> CollageGenerateResponse:
    """Generate (or regenerate) a SINGLE collage variant (A, B, or C)."""
    label = label.upper().strip()
    if label not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail=f"方案标签必须是 A/B/C，收到：{label}")

    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲后再生成拼图。")

    os.makedirs(str(PUBLIC_DIR), exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    save_generation_state(project_id, {
        "run_id": run_id, "status": "generating", "current_label": label,
        "message": f"正在生成方案 {label}",
    })

    def on_progress(event: dict) -> None:
        save_generation_state(project_id, {
            "run_id": run_id, "status": event.get("status", "generating"),
            "current_label": label,
            "attempt": int(event.get("attempt") or 1),
            "message": event.get("message", ""),
        })

    result: GenerationResult = await ImageGenerationService.generate_collage_single(
        project, label, project_id=project_id, on_progress=on_progress,
    )

    if not result.success:
        save_generation_state(project_id, {
            "run_id": run_id, "status": "failed",
            "error": result.error, "message": f"方案 {label} 生成失败",
        })
        raise HTTPException(status_code=500, detail=f"方案 {label} 生成失败：{result.error}")

    # Merge with existing collages
    existing = {c.get("label", ""): c for c in project.get("collages", [])}
    existing[label] = _result_to_collage_item(result)
    project["collages"] = sorted(existing.values(), key=lambda c: c["label"])
    project["updated_at"] = _now()
    _save(project_id, project)

    save_generation_state(project_id, {
        "run_id": run_id, "status": "completed",
        "completed_labels": [label],
        "message": f"方案 {label} 已生成",
    })

    collages_response = [
        CollageItem(label=c["label"], filename=c["filename"], download_url=_download_url(c["filename"]))
        for c in project["collages"]
    ]
    return CollageGenerateResponse(
        success=True, project_id=project_id, collages=collages_response,
        message=f"方案 {label} 已生成。",
    )


@router.put("/projects/{project_id}/collages/{label}", response_model=CollageGenerateResponse)
async def regenerate_single_collage(
    project_id: str, label: str, data: SingleCollageRequest = SingleCollageRequest()
) -> CollageGenerateResponse:
    """Regenerate a single collage with user feedback."""
    label = label.upper().strip()
    if label not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail=f"方案标签必须是 A/B/C，收到：{label}")

    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲后再生成拼图。")

    os.makedirs(str(PUBLIC_DIR), exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    save_generation_state(project_id, {
        "run_id": run_id, "status": "generating", "current_label": label,
        "message": f"正在重新生成方案 {label}",
    })

    def on_progress(event: dict) -> None:
        save_generation_state(project_id, {
            "run_id": run_id, "status": event.get("status", "generating"),
            "current_label": label,
            "attempt": int(event.get("attempt") or 1),
            "message": event.get("message", ""),
        })

    result: GenerationResult = await ImageGenerationService.generate_collage_single(
        project, label,
        feedback=data.feedback.strip(),
        project_id=project_id,
        on_progress=on_progress,
    )

    if not result.success:
        save_generation_state(project_id, {
            "run_id": run_id, "status": "failed",
            "error": result.error, "message": f"方案 {label} 重新生成失败",
        })
        raise HTTPException(status_code=500, detail=f"方案 {label} 重新生成失败：{result.error}")

    # Merge
    existing = {c.get("label", ""): c for c in project.get("collages", [])}
    existing[label] = _result_to_collage_item(result)
    project["collages"] = sorted(existing.values(), key=lambda c: c["label"])
    project["updated_at"] = _now()
    _save(project_id, project)

    save_generation_state(project_id, {
        "run_id": run_id, "status": "completed",
        "completed_labels": [label],
        "message": f"方案 {label} 已重新生成",
    })

    collages_response = [
        CollageItem(label=c["label"], filename=c["filename"], download_url=_download_url(c["filename"]))
        for c in project["collages"]
    ]
    return CollageGenerateResponse(
        success=True, project_id=project_id, collages=collages_response,
        message=f"方案 {label} 已重新生成。",
    )
