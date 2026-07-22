"""Digital Human Asset Management API — upload, list, and manage reference assets.

Only 数字真人 category goes through icover.ai for face review / asset:// ID.
场景/道具/其他 categories are stored locally (no API cost).
"""

from __future__ import annotations

import logging
import os
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.services.asset_library_service import (
    asset_library_service,
    ASSET_CATEGORIES,
    API_REQUIRED_CATEGORY,
    _LOCAL_ASSETS_DIR,
)

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assets", tags=["assets"])

# ── File constraints ───────────────────────────────────────────
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic"}


# ── Request / Response models ───────────────────────────────────

class AssetResponse(BaseModel):
    asset_id: str
    asset_url: str
    label: str
    category: str = "数字真人"
    group_id: str = ""
    public_url: str = ""
    status: str = ""
    filename: str = ""
    created_at: str = ""


class AssetListResponse(BaseModel):
    total: int
    assets: list[AssetResponse]


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="素材组名称")
    description: str = Field(default="", max_length=500)


class GroupResponse(BaseModel):
    group_id: str
    name: str


class APIResponse(BaseModel):
    success: bool
    message: str = ""
    data: dict | list | None = None


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/upload", response_model=AssetResponse)
async def upload_asset(
    file: UploadFile = File(...),
    label: str = Form(""),
    group_id: str = Form(""),
    category: str = Form("数字真人"),
):
    """Upload an image and register it as an asset.

    - **数字真人**: goes through icover.ai API → gets asset:// ID (face review required)
    - **场景/道具/其他**: stored locally, no API cost (use local URL directly in Seedance)

    Categories: 数字真人 (default), 场景, 道具, 其他
    """
    # Validate category
    if category not in ASSET_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的分类: {category}，可选: {ASSET_CATEGORIES}",
        )

    # Validate file extension
    if file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式 ({ext})，支持: {', '.join(ALLOWED_EXTENSIONS)}",
            )

    # Read file content
    file_data = await file.read()
    if len(file_data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"文件大小超过 {MAX_FILE_SIZE // 1024 // 1024}MB 限制")

    if len(file_data) == 0:
        raise HTTPException(status_code=400, detail="文件为空")

    needs_api = asset_library_service.needs_api(category)

    # ── Route A: 数字真人 → icover API ────────────────────────
    if needs_api:
        if not asset_library_service.is_configured:
            raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

        try:
            result = await asset_library_service.upload_and_register(
                file_data=file_data,
                filename=file.filename or "asset.jpg",
                label=label or (file.filename or "未命名素材"),
                group_id=group_id or None,
                category=category,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=f"素材库错误: {e}")
        except TimeoutError as e:
            raise HTTPException(status_code=504, detail=f"素材处理超时: {e}")
        except Exception as e:
            logger.exception("API asset upload failed")
            raise HTTPException(status_code=500, detail=f"上传失败: {e}")

        return AssetResponse(
            asset_id=result["asset_id"],
            asset_url=result["asset_url"],
            label=result["label"],
            category=result.get("category", category),
            group_id=result.get("group_id", ""),
            public_url=result.get("public_url", ""),
            status=result["status"],
            filename=file.filename or "",
        )

    # ── Route B: 场景/道具/其他 → 本地存储 ────────────────────
    try:
        result = asset_library_service.save_local_file(
            file_data=file_data,
            filename=file.filename or "asset.png",
            label=label or (file.filename or "未命名素材"),
            category=category,
        )
    except Exception as e:
        logger.exception("Local asset save failed")
        raise HTTPException(status_code=500, detail=f"本地保存失败: {e}")

    return AssetResponse(
        asset_id=result["asset_id"],
        asset_url=result["asset_url"],
        label=result["label"],
        category=result.get("category", category),
        group_id="",
        public_url=result.get("public_url", ""),
        status="Active",
        filename=file.filename or "",
    )


@router.get("", response_model=AssetListResponse)
async def list_assets(group_id: str = "", category: str = ""):
    """List all locally tracked assets. Optionally filter by group and/or category."""
    if not asset_library_service.is_configured:
        raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

    assets = asset_library_service.list_local_assets(
        group_id=group_id if group_id else None,
        category=category if category else None,
    )
    return AssetListResponse(
        total=len(assets),
        assets=[AssetResponse(**a) for a in assets],
    )


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str):
    """Get a single asset's metadata from local store."""
    if not asset_library_service.is_configured:
        raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

    asset = asset_library_service.get_local_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail=f"素材 {asset_id} 不存在")

    # Optionally refresh status from remote
    try:
        remote = await asset_library_service.get_asset(asset_id)
        remote_status = (remote.get("Result", {}) or {}).get("Status", "")
        if remote_status:
            asset["status"] = remote_status
    except Exception:
        pass  # Keep local status if remote query fails

    return AssetResponse(**asset)


@router.delete("/{asset_id}", response_model=APIResponse)
async def delete_asset(asset_id: str):
    """Delete an asset. For API assets (数字真人), also deletes from icover.ai. For local assets, deletes the file."""
    if not asset_library_service.is_configured and asset_id.startswith("asset-"):
        raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

    # For API assets, delete from remote first
    if asset_id.startswith("asset-"):
        try:
            await asset_library_service.delete_asset(asset_id)
        except Exception as e:
            logger.warning("Remote delete failed for %s: %s", asset_id, e)

    # Delete from local (handles both API and local assets, including file cleanup for local)
    existed = asset_library_service.delete_local_file(asset_id)
    if not existed:
        raise HTTPException(status_code=404, detail=f"素材 {asset_id} 不存在")

    return APIResponse(success=True, message=f"素材 {asset_id} 已删除")


# ── Local file serving ─────────────────────────────────────────

@router.get("/local-files/{filename}")
async def serve_local_file(filename: str):
    """Serve a locally-stored asset file (场景/道具/其他)."""
    filepath = _LOCAL_ASSETS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = os.path.splitext(filename)[1].lower()
    media_type_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    }
    return FileResponse(str(filepath), media_type=media_type_map.get(ext, "image/png"))


# ── Categories ─────────────────────────────────────────────────

@router.get("/categories/list")
async def list_categories():
    """Return available asset categories."""
    return {
        "categories": [
            {"value": c, "label": c, "needs_api": c == API_REQUIRED_CATEGORY,
             "icon": {"数字真人": "🧑", "场景": "🏞", "道具": "🎯", "其他": "📦"}.get(c, "📦")}
            for c in ASSET_CATEGORIES
        ]
    }


@router.patch("/{asset_id}", response_model=APIResponse)
async def update_asset_label(asset_id: str, label: str = ""):
    """Update an asset's label."""
    if not asset_library_service.is_configured:
        raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

    # Update remotely
    try:
        await asset_library_service.update_asset_label(asset_id, label)
    except Exception as e:
        logger.warning("Remote label update failed for %s: %s", asset_id, e)

    # Update locally
    updated = asset_library_service.update_local_asset_label(asset_id, label)
    if not updated:
        raise HTTPException(status_code=404, detail=f"素材 {asset_id} 不存在")

    return APIResponse(success=True, message="标签已更新")


# ── Group endpoints ─────────────────────────────────────────────

@router.get("/groups/list", response_model=APIResponse)
async def list_groups():
    """List all asset groups from icover.ai."""
    if not asset_library_service.is_configured:
        raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

    try:
        result = await asset_library_service.list_groups()
        items = (result.get("Result", {}) or {}).get("Items", [])
        groups = [
            {"group_id": g.get("Id", ""), "name": g.get("Name", g.get("Label", ""))}
            for g in items
        ]
        return APIResponse(success=True, data=groups)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取素材组列表失败: {e}")


@router.post("/groups/create", response_model=APIResponse)
async def create_group(req: CreateGroupRequest):
    """Create a new asset group."""
    if not asset_library_service.is_configured:
        raise HTTPException(status_code=503, detail="素材库 API Key 未配置 (ICOVER_API_KEY)")

    try:
        result = await asset_library_service.create_group(req.name, req.description)
        group_id = (result.get("Result", {}) or {}).get("Id", "")
        return APIResponse(success=True, message=f"素材组 '{req.name}' 已创建", data={"group_id": group_id})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"创建素材组失败: {e}")


# ── Status check ────────────────────────────────────────────────

@router.get("/system/status", response_model=APIResponse)
async def system_status():
    """Check if the asset library is configured and reachable."""
    if not asset_library_service.is_configured:
        return APIResponse(success=False, message="ICOVER_API_KEY 未配置")

    try:
        result = await asset_library_service.list_groups()
        return APIResponse(
            success=True,
            message="素材库已连接",
            data={"configured": True, "reachable": True},
        )
    except Exception as e:
        return APIResponse(
            success=False,
            message=f"素材库连接失败: {e}",
            data={"configured": True, "reachable": False},
        )
