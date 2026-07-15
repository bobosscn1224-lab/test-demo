"""PPT Conversion Feature API — image-to-PPTX with multiple backends.

Provides REST endpoints for PPT conversion without going through
the conversational ppt_maker skill system.
"""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.services._paths import PUBLIC_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pptx", tags=["pptx"])


# ── Models ────────────────────────────────────────────────────────

class ConvertResponse(BaseModel):
    success: bool
    message: str = ""
    filename: str = ""
    download_url: str = ""
    path: str = ""
    page_count: int = 0
    pipeline: str = ""


class PageResult(BaseModel):
    page: int
    file: str = ""
    text_items: int = 0
    status: str = "done"


class PageError(BaseModel):
    page: int
    file: str = ""
    error: str = ""


class JobStatus(BaseModel):
    """Full job status — mirrors batch_job_manager's job dict exactly.

    Status lifecycle: queued → processing → merging → completed | failed
    """
    job_id: str
    status: str  # queued | processing | merging | completed | failed
    total: int = 0
    current: int = 0
    current_file: str = ""
    progress: int = 0  # 0-100
    results: list[PageResult] = Field(default_factory=list)
    errors: list[PageError] = Field(default_factory=list)
    combined_pptx_path: str | None = None
    combined_pptx_url: str | None = None
    combined_pptx_filename: str | None = None
    download_url: str = ""
    created_at: str = ""


# ── Helpers ───────────────────────────────────────────────────────

def _output_dir() -> str:
    d = str(PUBLIC_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def _download_url(filename: str) -> str:
    return f"/api/skills/download/{filename}"


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/convert", response_model=ConvertResponse)
async def convert_images_to_pptx(
    images: list[UploadFile] = File(..., description="PPT page images (PNG/JPG)"),
    mode: str = Form(default="layout", description="Conversion mode: layout | batch"),
):
    """Convert uploaded page images into a downloadable PPTX file.

    - **layout**: DeckWeaver layout-aware reconstruction (~30s per image)
    - **batch**: Simple image placement as full-slide backgrounds (fast)
    """
    if not images:
        raise HTTPException(status_code=400, detail="请至少上传一张图片")

    saved_paths: list[str] = []
    for img in images:
        ext = os.path.splitext(img.filename or "image.png")[1] or ".png"
        dest = os.path.join(_output_dir(), f"pptx_upload_{uuid.uuid4().hex[:8]}{ext}")
        content = await img.read()
        with open(dest, "wb") as f:
            f.write(content)
        saved_paths.append(dest)

    if mode == "batch":
        return await _batch_convert(saved_paths)
    else:
        return await _layout_convert(saved_paths)


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Check status of an async batch conversion job.

    Returns the full job dict from batch_job_manager, including:
    progress, current page, per-page results, errors, and download info.
    Frontend polls this every 1.5s during conversion.
    """
    from app.services.batch_job_manager import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Build download_url for convenience
    download_url = ""
    if job.get("combined_pptx_filename"):
        download_url = _download_url(job["combined_pptx_filename"])

    return JobStatus(
        job_id=job.get("job_id", job_id),
        status=job.get("status", "unknown"),
        total=job.get("total", 0),
        current=job.get("current", 0),
        current_file=job.get("current_file", ""),
        progress=job.get("progress", 0),
        results=[PageResult(**r) for r in job.get("results", [])],
        errors=[PageError(**e) for e in job.get("errors", [])],
        combined_pptx_path=job.get("combined_pptx_path"),
        combined_pptx_url=job.get("combined_pptx_url"),
        combined_pptx_filename=job.get("combined_pptx_filename"),
        download_url=download_url,
        created_at=job.get("created_at", ""),
    )


@router.post("/convert-async", response_model=dict)
async def convert_async(data: dict):
    """Start async batch conversion. Returns job_id immediately.
    Poll GET /api/v1/pptx/jobs/{job_id} for progress.
    """
    from app.services.batch_job_manager import create_job

    images = data.get("images", [])
    if not images:
        raise HTTPException(status_code=400, detail="At least 1 image required")

    job_id = create_job(images, _output_dir())
    return {"job_id": job_id, "status": "queued", "total": len(images)}


# ── Conversion backends ──────────────────────────────────────────

async def _batch_convert(image_paths: list[str]) -> ConvertResponse:
    """Batch convert: simple image placement as full-slide backgrounds."""
    try:
        from app.services.batch_pptx_service import batch_convert

        sorted_paths = sorted(image_paths, key=lambda p: os.path.basename(p))
        result = await batch_convert(sorted_paths, output_dir=_output_dir())

        if result.get("error") and not result.get("page_count"):
            return ConvertResponse(success=False, message=result["error"])

        filename = result.get("filename", "output.pptx")
        return ConvertResponse(
            success=True,
            message="批量转换完成",
            filename=filename,
            download_url=_download_url(filename),
            path=result.get("path", ""),
            page_count=result.get("page_count", 0),
            pipeline="batch",
        )
    except Exception as exc:
        logger.error("Batch PPTX conversion failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量转换失败：{exc}")


async def _layout_convert(image_paths: list[str]) -> ConvertResponse:
    """Layout-aware reconstruction using DeckWeaver."""
    try:
        from app.services.layout_reconstructor import reconstruct as run_layout

        r = await run_layout(
            image_paths[0],
            output_dir=_output_dir(),
            session_id="feature_pptx",
            enable_shapes=True,
        )
        if not r:
            return ConvertResponse(success=False, message="Layout 重建失败")

        filename = r.get("filename", "output.pptx")
        return ConvertResponse(
            success=True,
            message="Layout 重建完成",
            filename=filename,
            download_url=_download_url(filename),
            path=r.get("path", ""),
            page_count=1,
            pipeline="layout",
        )
    except Exception as exc:
        logger.error("Layout PPTX conversion failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Layout 转换失败：{exc}")
