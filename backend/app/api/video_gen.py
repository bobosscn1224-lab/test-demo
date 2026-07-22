"""Video Generation API — Seedance-powered short video creation.

Provides REST endpoints for text-to-video and image-reference video generation
using the api.apiyi.com Seedance 2.0 API, integrated with the Asset Library.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.seedance_service import (
    seedance_service,
    MODELS,
    RESOLUTIONS,
    RATIOS,
    DURATION_RANGE,
    _VIDEO_OUTPUT_DIR,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video-gen", tags=["video-gen"])


# ── Request / Response models ───────────────────────────────────

class VideoGenRequest(BaseModel):
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="视频描述提示词，中文建议不超过500字。支持 @素材名 引用已入库素材",
    )
    mode: str = Field(
        default="reference",
        description="生成模式: text (纯文本), reference (参考图), first_frame (首帧), first_last_frame (首尾帧)",
    )
    reference_assets: list[str] = Field(
        default_factory=list,
        max_length=9,
        description="参考素材的 asset:// ID 或本地 URL 列表（0-9个），用于 reference 模式",
    )
    first_frame_asset: str = Field(
        default="",
        description="首帧图片的 URL，用于 first_frame/first_last_frame 模式",
    )
    last_frame_asset: str = Field(
        default="",
        description="尾帧图片的 URL，用于 first_last_frame 模式",
    )
    model: str = Field(
        default="fast",
        description="模型: standard / fast / mini",
    )
    resolution: str = Field(
        default="720p",
        description="分辨率: 480p / 720p / 1080p",
    )
    ratio: str = Field(
        default="16:9",
        description="画面比例: 16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 21:9 / adaptive",
    )
    duration: int = Field(
        default=5,
        ge=4,
        le=15,
        description="视频时长（秒），4-15",
    )
    generate_audio: bool = Field(
        default=False,
        description="是否生成音频",
    )
    return_last_frame: bool = Field(
        default=False,
        description="是否返回视频尾帧图片",
    )
    seed: int = Field(
        default=-1,
        ge=-1,
        description="随机种子，-1 为随机",
    )
    auto_download: bool = Field(
        default=True,
        description="是否自动后台轮询并下载视频",
    )


class VideoGenResponse(BaseModel):
    success: bool
    task_id: str = ""
    status: str = ""
    model: str = ""
    resolution: str = ""
    ratio: str = ""
    duration: int = 5
    error: str = ""
    video_url: str = ""
    last_frame_url: str = ""
    local_path: str = ""
    tokens: int = 0


class PromptOptimizeRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000, description="原始提示词")
    reference_assets: list[dict] = Field(
        default_factory=list,
        description="引用的素材列表 [{\"label\": \"...\", \"category\": \"...\", \"asset_url\": \"...\"}]",
    )


class PromptOptimizeResponse(BaseModel):
    success: bool
    original: str = ""
    optimized: str = ""
    changes: str = ""
    error: str = ""


class TaskListResponse(BaseModel):
    total: int
    tasks: list[dict]


class VideoInfo(BaseModel):
    task_id: str
    status: str
    prompt: str
    model: str
    video_url: str
    local_path: str
    created_at: str


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/generate", response_model=VideoGenResponse)
async def generate_video(req: VideoGenRequest, background_tasks: BackgroundTasks):
    """Create a Seedance video generation task.

    Supports text-to-video (no reference_assets) and
    image-reference video (with asset:// IDs from the Asset Library).

    If auto_download=True (default), the server will poll the task
    in the background and download the video when ready.
    """
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置 (APIYI_API_KEY)")

    # Validate model
    if req.model not in MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的模型: {req.model}，可选: {list(MODELS.keys())}",
        )

    # Validate resolution
    if req.resolution not in RESOLUTIONS:
        raise HTTPException(status_code=400, detail=f"不支持的分辨率: {req.resolution}")

    # 1080p only for standard model
    if req.resolution == "1080p" and req.model != "standard":
        raise HTTPException(
            status_code=400,
            detail="1080p 仅支持 standard 模型",
        )

    # Validate ratio
    if req.ratio not in RATIOS:
        raise HTTPException(status_code=400, detail=f"不支持的比例: {req.ratio}")

    # Validate reference assets format
    for asset_url in req.reference_assets:
        if not asset_url.startswith("asset://"):
            raise HTTPException(
                status_code=400,
                detail=f"参考素材必须使用 asset:// 格式: {asset_url}",
            )

    try:
        result = await seedance_service.create_task(
            prompt=req.prompt,
            reference_assets=req.reference_assets if req.mode == "reference" and req.reference_assets else None,
            first_frame_asset=req.first_frame_asset if req.mode in ("first_frame", "first_last_frame") and req.first_frame_asset else None,
            last_frame_asset=req.last_frame_asset if req.mode == "first_last_frame" and req.last_frame_asset else None,
            model=req.model,
            resolution=req.resolution,
            ratio=req.ratio,
            duration=req.duration,
            generate_audio=req.generate_audio,
            return_last_frame=req.return_last_frame,
            seed=req.seed,
        )
    except Exception as e:
        logger.exception("Failed to create video task")
        raise HTTPException(status_code=502, detail=f"创建视频任务失败: {e}")

    task_id = result["task_id"]

    # Auto poll & download in background
    if req.auto_download:
        background_tasks.add_task(_auto_poll_and_download, task_id)

    return VideoGenResponse(
        success=True,
        task_id=task_id,
        status="queued",
        model=req.model,
        resolution=req.resolution,
        ratio=req.ratio,
        duration=req.duration,
    )


# ── Prompt Optimization ─────────────────────────────────────────
@router.post("/optimize-prompt", response_model=PromptOptimizeResponse)
async def optimize_prompt(req: PromptOptimizeRequest):
    """Optimize the user's video generation prompt for best Seedance results.

    Takes a raw prompt (which may include @asset_name references) and
    returns an enhanced version optimized for video generation quality.
    The user should review and confirm before generating.
    """
    try:
        from app.services.llm_service import llm_service
        from app.config import settings

        # Build context about referenced assets with usage roles
        asset_context = ""
        if req.reference_assets:
            asset_context = "\n\n## 参考素材（用户已选择，含用途标注）\n"
            usage_hints = {
                "character": "角色素材 — 必须用 \"The person in image N\" 锚定面部特征，保持一致性",
                "scene": "场景背景素材 — 用 \"Set in image N\" 描述空间环境",
                "prop": "道具素材 — 用 \"The object shown in image N\" 引用",
                "style": "风格参考素材 — 用 \"Match the lighting and palette of image N\" 锁定色调",
            }
            for i, a in enumerate(req.reference_assets):
                label = a.get("label", f"素材{i+1}")
                usage = a.get("usage", "style")
                idx = i + 1
                hint = usage_hints.get(usage, usage_hints["style"])
                asset_context += f"- image {idx} (@{label})：{hint}\n"

        system_prompt = """你是 Seedance 2.0 视频生成提示词优化专家。

你的任务是将用户的原始提示词优化为最佳视频生成效果的英文提示词。

## 铁律（违反即不合格）
1. **绝不画质词**：不要添加 4K、8K、HD、Ultra HD、high resolution 等画质词
2. **保留对白**：如果用户原文中有台词/对白/对话/旁白，必须完整保留并翻译为英文
3. **@素材名 是主角**：提示词中必须使用 @素材名（如 @人物02）来引用素材，不要用 "image N" 替换 @素材名。每个引用的素材前面都要加 @

## 优化原则
1. **人物锚定**：对于标注为"角色素材"的 @素材名，描述时必须用 @素材名 来指代这个人物（如 @人物02 stands firmly...）。不要编造新的人物名字或特征
2. **场景道具引用**：场景和道具素材用 @素材名 指代（如 @办公室背景 as the setting）
3. **转换为英文**
4. **丰富视觉细节**：补充光影、色彩、构图、氛围等视觉描述
5. **添加摄像机运动**
6. **控制长度**：不超过 1000 个英文单词
7. **不要编造**：只能基于用户提供的信息优化

## 输出格式
返回 JSON：
{
  "optimized_prompt": "完整的优化后英文提示词",
  "changes": "用中文简述你做了哪些优化（3-5条要点）"
}"""

        user_prompt = f"""原始提示词：
{req.prompt}
{asset_context}

请优化这个提示词，返回 JSON 格式。"""

        # Use raw chat to bypass quality gate for this interactive feature
        import anthropic
        user_msg = user_prompt

        response = await llm_service._chat_raw(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            model=settings.claude_model,
            max_tokens=2000,
            temperature=0.7,
        )

        # Parse JSON from response
        import json
        content = ""
        if hasattr(response, 'content'):
            for block in response.content:
                if hasattr(block, 'text'):
                    content += block.text
        else:
            content = str(response)

        # Try to extract JSON block
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        optimized = result.get("optimized_prompt", "")
        changes = result.get("changes", "")

        return PromptOptimizeResponse(
            success=True,
            original=req.prompt,
            optimized=optimized,
            changes=changes,
        )

    except Exception as e:
        logger.exception("Prompt optimization failed")
        return PromptOptimizeResponse(
            success=False,
            original=req.prompt,
            optimized="",
            changes="",
            error=str(e),
        )


@router.get("/tasks/{task_id}", response_model=VideoGenResponse)
async def get_task(task_id: str):
    """Query a video generation task's status.

    Returns video_url when status=succeeded (link valid ~24h).
    """
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置")

    try:
        record = await seedance_service.get_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询任务失败: {e}")

    if not record:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    return VideoGenResponse(
        success=True,
        task_id=record.get("task_id", task_id),
        status=record.get("status", "unknown"),
        model=record.get("model", ""),
        resolution=record.get("resolution", ""),
        ratio=record.get("ratio", ""),
        duration=record.get("duration", 5),
        video_url=record.get("video_url", ""),
        last_frame_url=record.get("last_frame_url", ""),
        local_path=record.get("local_path", ""),
        tokens=record.get("tokens", 0),
        error=record.get("error", ""),
    )


@router.get("/tasks/{task_id}/poll", response_model=VideoGenResponse)
async def poll_task(task_id: str):
    """Poll a task until completion (may take 15+ minutes).

    This is a synchronous wait — use /generate with auto_download=True
    for non-blocking behavior, and /tasks/{id} to check status.
    """
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置")

    try:
        record = await seedance_service.poll_task(
            task_id,
            poll_interval=15.0,
            max_wait=900.0,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail=f"任务 {task_id} 轮询超时（15分钟），请稍后查询")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"轮询失败: {e}")

    video_url = record.get("video_url", "")
    status = record.get("status", "")

    # Auto-download if succeeded and has URL
    local_path = ""
    if status == "succeeded" and video_url:
        try:
            local_path = await seedance_service.download_video(task_id, video_url)
        except Exception as e:
            logger.warning("Auto-download failed for %s: %s", task_id, e)

    return VideoGenResponse(
        success=status == "succeeded",
        task_id=task_id,
        status=status,
        model=record.get("model", ""),
        video_url=video_url,
        last_frame_url=record.get("last_frame_url", ""),
        local_path=local_path,
        tokens=record.get("tokens", 0),
        error=record.get("error", ""),
    )


@router.get("/tasks")
async def list_tasks(limit: int = 30):
    """List recent video generation tasks."""
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置")

    tasks = seedance_service.list_tasks(limit=limit)
    return {"total": len(tasks), "tasks": tasks}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task record and its cached video."""
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置")

    existed = seedance_service.delete_task_record(task_id)
    if not existed:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")

    return {"success": True, "message": f"任务 {task_id} 已删除"}


@router.get("/videos/{task_id}")
async def get_video_file(task_id: str):
    """Serve a cached video file for playback/download."""
    video_path = _VIDEO_OUTPUT_DIR / f"{task_id}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在或尚未下载")

    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"{task_id}.mp4",
    )


# ── Frame to Asset Library ─────────────────────────────────────

class FrameToAssetRequest(BaseModel):
    image_url: str = Field(..., description="尾帧或其他图片的 URL")
    label: str = Field(default="", description="素材标签")
    category: str = Field(default="数字真人", description="入库分类: 数字真人/场景/道具/其他")


@router.post("/frames/import")
async def import_frame_to_asset(req: FrameToAssetRequest):
    """Download a frame from URL and add it to the asset library.

    - If category is 数字真人, goes through icover API (face review).
    - Other categories are stored locally.
    """
    from app.services.asset_library_service import asset_library_service
    import httpx

    if not req.image_url:
        raise HTTPException(status_code=400, detail="image_url is required")

    # Download the image
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.get(req.image_url)
            resp.raise_for_status()
            image_data = resp.content
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"下载图片失败: {e}")

    if len(image_data) == 0:
        raise HTTPException(status_code=400, detail="下载的图片为空")

    # Determine filename from URL or default
    filename = req.label or "frame_import"
    if not filename.endswith(('.png', '.jpg', '.jpeg', '.webp')):
        filename += '.png'

    needs_api = asset_library_service.needs_api(req.category)

    if needs_api:
        if not asset_library_service.is_configured:
            raise HTTPException(status_code=503, detail="素材库 API Key 未配置")
        try:
            result = await asset_library_service.upload_and_register(
                file_data=image_data, filename=filename,
                label=req.label or "视频尾帧", category=req.category,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"入库失败: {e}")
    else:
        try:
            result = asset_library_service.save_local_file(
                file_data=image_data, filename=filename,
                label=req.label or "视频尾帧", category=req.category,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"本地保存失败: {e}")

    from app.api.assets import AssetResponse
    return {
        "success": True,
        "asset_id": result["asset_id"],
        "asset_url": result["asset_url"],
        "label": result["label"],
        "category": result.get("category", req.category),
        "status": result.get("status", "Active"),
    }


@router.get("/config")
async def get_config():
    """Return available model options and configuration."""
    return {
        "models": [
            {"key": k, "id": v, "max_resolution": "1080p" if k == "standard" else "720p"}
            for k, v in MODELS.items()
        ],
        "resolutions": RESOLUTIONS,
        "ratios": [
            {"value": r, "label": r}
            for r in RATIOS
        ],
        "duration_range": list(DURATION_RANGE),
        "configured": seedance_service.is_configured,
    }


# ── Background task ─────────────────────────────────────────────

async def _auto_poll_and_download(task_id: str) -> None:
    """Background task: poll until done, then download video."""
    try:
        logger.info("Background: polling task %s...", task_id)
        record = await seedance_service.poll_task(
            task_id,
            poll_interval=15.0,
            max_wait=900.0,  # 15 minutes
        )

        status = record.get("status", "")
        video_url = record.get("video_url", "")

        if status == "succeeded" and video_url:
            logger.info("Background: downloading video for %s...", task_id)
            local_path = await seedance_service.download_video(task_id, video_url)
            logger.info("Background: video saved to %s", local_path)
        else:
            logger.warning("Background: task %s ended with status=%s", task_id, status)

    except Exception as e:
        logger.exception("Background task failed for %s: %s", task_id, e)
