"""Image Generation Feature API — direct prompt-to-image with settings.

Provides REST endpoints for image generation without going through
the conversational skill system.
"""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.image_gen_service import generate_image, list_configured_backends
from app.services._paths import PUBLIC_DIR, ensure_dirs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/images", tags=["images"])


# ── Request / Response models ───────────────────────────────────

VALID_SIZES = {"1024x1024", "1792x1024", "1024x1792"}
VALID_RATIOS = {"1:1": "1024x1024", "16:9": "1792x1024", "9:16": "1024x1792"}


class ImageGenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000, description="图片描述词")
    size: str = Field(default="1024x1024", description="像素尺寸，如 1024x1024")
    ratio: str = Field(default="16:9", description="快捷比例: 1:1, 16:9, 9:16")
    session_id: str | None = Field(default=None)


class ImageGenResponse(BaseModel):
    success: bool
    image_url: str = ""
    download_url: str = ""
    prompt: str = ""
    error: str = ""
    backend: str = ""
    path: str = ""
    filename: str = ""


class ImageHistoryItem(BaseModel):
    filename: str
    url: str
    prompt: str


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/generate", response_model=ImageGenResponse)
async def generate(req: ImageGenRequest):
    """Generate an image from a text prompt via the configured backend.

    Supports ratio presets (1:1, 16:9, 9:16) and explicit pixel sizes.
    """
    if not list_configured_backends():
        raise HTTPException(status_code=503, detail="未配置任何图片生成服务。")

    # Resolve size from ratio if specified
    size = req.size
    if req.ratio in VALID_RATIOS:
        size = VALID_RATIOS[req.ratio]
    elif size not in VALID_SIZES:
        size = "1024x1024"  # fallback

    filename = f"gen_{uuid.uuid4().hex[:8]}.png"
    ensure_dirs()
    out_dir = str(PUBLIC_DIR)
    output_path = os.path.join(out_dir, filename)

    result = await generate_image(
        req.prompt, output_path, interaction_name="general_image", size=size,
    )

    if not result.success:
        return ImageGenResponse(
            success=False,
            error=result.error,
            prompt=req.prompt,
            backend=result.backend,
        )

    download_url = f"/api/skills/download/{filename}"

    return ImageGenResponse(
        success=True,
        image_url=download_url,
        download_url=download_url,
        prompt=req.prompt,
        backend=result.backend,
        path=result.path,
        filename=filename,
    )


@router.get("/backends")
async def list_backends():
    """Return configured image generation backends."""
    backends = [
        {"name": item["key"], "model": item["model"], "status": item["status"]}
        for item in list_configured_backends()
    ]
    if not backends:
        backends.append({"name": "none", "status": "unavailable"})
    return {"backends": backends}
