"""Pro Mode Step 4 — Shot Generation (逐镜生成).

关键设计：
- 每个镜头的 task_id / video_status / video_path 全部持久化到项目，
  后端是状态的唯一权威来源（刷新不丢、可断点续做）。
- 分镜关键帧存在时，自动作为 Seedance 首帧锚定（图生视频），
  一致性从 prompt 级提升到图像级。
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.seedance_service import seedance_service, _VIDEO_OUTPUT_DIR
from app.services.asset_library_service import asset_library_service

from .models import ShotGenerateRequest, BatchGenerateRequest, PortraitRequest
from .prompt_engine import build_shot_prompt
from .projects import load_project, save_project
from .shot_state import init_shot_state, shot_is_actionable

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["pro-mode-generation"])

_BACKEND_ROOT = Path(__file__).parent.parent.parent.parent
_LOCAL_ASSETS_DIR = _BACKEND_ROOT / "data" / "local_assets"


# ── helpers ──────────────────────────────────────────────────────

def _get_shot(project: dict, shot_number: int) -> dict | None:
    return next((s for s in project.get("shots", []) if s.get("shot_number") == shot_number), None)


def _frame_url_to_data_uri(frame_image_url: str) -> str | None:
    """把 /api/v1/assets/local-files/xxx.png 形式的本地 URL 转成 base64 data URI。

    Seedance API 无法访问 localhost，首帧图必须内联上传。
    """
    prefix = "/api/v1/assets/local-files/"
    if not frame_image_url or prefix not in frame_image_url:
        return None
    filename = frame_image_url.split(prefix, 1)[1]
    # 防目录穿越
    if "/" in filename or ".." in filename:
        return None
    path = _LOCAL_ASSETS_DIR / filename
    if not path.exists():
        logger.warning("Frame image not found on disk: %s", path)
        return None
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


async def _submit_shot_task(project: dict, shot: dict, *, model: str, resolution: str,
                            ratio: str, generate_audio: bool, return_last_frame: bool) -> dict:
    """组装 prompt + 首帧，提交 Seedance，回写镜头状态。返回 create_task 结果。"""
    full_prompt = build_shot_prompt(project, shot)
    if not full_prompt.strip():
        raise HTTPException(status_code=400, detail=f"Shot {shot.get('shot_number')} 无有效 prompt 内容")

    char_map = {c["id"]: c for c in project.get("characters", [])}
    reference_assets = []
    for cid in shot.get("character_ids", []):
        c = char_map.get(cid)
        if c and c.get("asset_id") and str(c["asset_id"]).startswith("asset-"):
            reference_assets.append(f"asset://{c['asset_id']}")

    # 分镜关键帧 → 首帧锚定（图生视频）；有首帧时不再叠加参考图，避免模态冲突
    first_frame_data_uri = _frame_url_to_data_uri(shot.get("frame_image_url", ""))
    if first_frame_data_uri:
        reference_assets = None

    result = await seedance_service.create_task(
        prompt=full_prompt[:2000],
        reference_assets=reference_assets,
        first_frame_asset=first_frame_data_uri,
        model=model, resolution=resolution, ratio=ratio,
        duration=shot.get("duration", 5),
        generate_audio=generate_audio,
        return_last_frame=return_last_frame,
    )

    shot["task_id"] = result["task_id"]
    shot["video_status"] = "queued"
    shot["error"] = ""
    return result


# ── endpoints ────────────────────────────────────────────────────

@router.get("/shot-prompt/{project_id}/{shot_number}")
async def preview_shot_prompt(project_id: str, shot_number: int):
    """Step 4a: 预览某个镜头的完整 Seedance prompt。"""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shot = _get_shot(project, shot_number)
    if not shot:
        raise HTTPException(status_code=404, detail=f"Shot {shot_number} 不存在")

    full_prompt = build_shot_prompt(project, shot)
    return {
        "success": True, "shot_number": shot_number,
        "prompt": full_prompt, "duration": shot.get("duration", 5),
        "prompt_length": len(full_prompt),
        "has_first_frame": bool(shot.get("frame_image_url")),
    }


@router.post("/shot")
async def generate_single_shot(req: ShotGenerateRequest):
    """Step 4b: 提交单个镜头到 Seedance（首帧锚定 + asset:// 引用 + 状态持久化）。"""
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置")

    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shot = _get_shot(project, req.shot_number)
    if not shot:
        raise HTTPException(status_code=404, detail=f"Shot {req.shot_number} 不存在")

    init_shot_state(shot)
    if shot.get("video_status") == "queued" and shot.get("task_id"):
        return {
            "success": True, "shot_number": req.shot_number,
            "task_id": shot["task_id"], "status": "queued",
            "message": "该镜头已在生成队列中",
        }

    try:
        result = await _submit_shot_task(
            project, shot, model=req.model, resolution=req.resolution,
            ratio=req.ratio, generate_audio=req.generate_audio,
            return_last_frame=req.return_last_frame,
        )
        save_project(req.project_id, project)
        return {
            "success": True, "shot_number": req.shot_number,
            "task_id": result["task_id"], "status": "queued",
            "used_first_frame": bool(shot.get("frame_image_url")),
        }
    except HTTPException:
        raise
    except Exception as e:
        shot["video_status"] = "failed"
        shot["error"] = str(e)
        save_project(req.project_id, project)
        raise HTTPException(status_code=502, detail=f"创建任务失败: {e}")


@router.post("/batch")
async def generate_batch(req: BatchGenerateRequest):
    """Step 4c: 批量为所有待生成/失败/过期的镜头创建任务。"""
    if not seedance_service.is_configured:
        raise HTTPException(status_code=503, detail="Seedance API Key 未配置")

    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shots = project.get("shots", [])
    if not shots:
        raise HTTPException(status_code=400, detail="项目还没有分镜")

    submitted, skipped, failed = [], [], []
    for shot in shots:
        init_shot_state(shot)
        sn = shot["shot_number"]
        if not shot_is_actionable(shot, include_failed=req.include_failed):
            skipped.append(sn)
            continue
        try:
            result = await _submit_shot_task(
                project, shot, model=req.model, resolution=req.resolution,
                ratio=req.ratio, generate_audio=req.generate_audio,
                return_last_frame=True,
            )
            submitted.append({"shot_number": sn, "task_id": result["task_id"]})
        except Exception as e:
            logger.exception("Batch submit failed for shot %s", sn)
            shot["video_status"] = "failed"
            shot["error"] = str(e)
            failed.append({"shot_number": sn, "error": str(e)})
        save_project(req.project_id, project)

    return {
        "success": True,
        "submitted": submitted, "skipped": skipped, "failed": failed,
        "submitted_count": len(submitted),
    }


@router.get("/shot-status/{project_id}/{shot_number}")
async def get_shot_status(project_id: str, shot_number: int):
    """Step 4d: 查询镜头状态（服务端轮询 Seedance，成功后自动下载归档视频）。

    前端只需调这一个端点，不需要知道 task_id，状态全部以项目文件为准。
    """
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shot = _get_shot(project, shot_number)
    if not shot:
        raise HTTPException(status_code=404, detail=f"Shot {shot_number} 不存在")

    init_shot_state(shot)

    # 已在终态：直接返回
    if shot.get("video_status") in ("succeeded", "failed", "stale", "pending"):
        return {"success": True, "shot_number": shot_number,
                "video_status": shot["video_status"], "video_url": shot.get("video_url", ""),
                "last_frame_url": shot.get("last_frame_url", ""), "error": shot.get("error", "")}

    task_id = shot.get("task_id", "")
    if not task_id:
        shot["video_status"] = "pending"
        save_project(project_id, project)
        return {"success": True, "shot_number": shot_number, "video_status": "pending"}

    try:
        record = await seedance_service.get_task(task_id)
    except Exception as e:
        logger.warning("Poll task %s failed: %s", task_id, e)
        return {"success": True, "shot_number": shot_number,
                "video_status": "queued", "error": f"状态查询失败(将重试): {e}"}

    status = record.get("status", "")
    if status == "succeeded":
        video_url = record.get("video_url", "")
        shot["video_url"] = video_url
        shot["last_frame_url"] = record.get("last_frame_url", "")
        # 下载归档（24h 后 CDN 链接会过期，必须落盘）
        if video_url and not shot.get("video_path"):
            try:
                local_path = await seedance_service.download_video(task_id, video_url)
                # 归档为 shot 专属文件名，便于追溯
                archived = _VIDEO_OUTPUT_DIR / f"shot-{project_id}-{shot_number}.mp4"
                if str(archived) != local_path:
                    shutil.copy2(local_path, archived)
                shot["video_path"] = str(archived)
            except Exception as e:
                logger.exception("Download video failed for shot %s", shot_number)
                shot["error"] = f"视频下载失败: {e}"
        shot["video_status"] = "succeeded" if shot.get("video_path") or video_url else "failed"
        if not shot.get("video_path") and not video_url:
            shot["error"] = "任务成功但未返回视频地址"
    elif status in ("failed", "expired"):
        shot["video_status"] = "failed"
        shot["error"] = record.get("error", "") or status
    else:
        shot["video_status"] = "queued"

    save_project(project_id, project)
    return {
        "success": True, "shot_number": shot_number,
        "video_status": shot["video_status"],
        "video_url": shot.get("video_url", ""),
        "video_path": shot.get("video_path", ""),
        "last_frame_url": shot.get("last_frame_url", ""),
        "error": shot.get("error", ""),
    }


@router.get("/shots-status/{project_id}")
async def get_all_shots_status(project_id: str):
    """Step 4e: 一次性拉取项目所有镜头的状态（不触发 Seedance 查询）。"""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shots = []
    for shot in project.get("shots", []):
        init_shot_state(shot)
        shots.append({
            "shot_number": shot["shot_number"],
            "frame_status": shot.get("frame_status", "pending"),
            "frame_image_url": shot.get("frame_image_url", ""),
            "video_status": shot.get("video_status", "pending"),
            "video_url": shot.get("video_url", ""),
            "last_frame_url": shot.get("last_frame_url", ""),
            "error": shot.get("error", ""),
        })
    save_project(project_id, project)  # 持久化补齐的状态字段
    return {"success": True, "shots": shots}


@router.post("/portrait")
async def generate_character_portrait(req: PortraitRequest):
    """生成人物定妆照：白色背景、全身、多人并肩、面部清晰。

    自动走 icover API 获取 asset:// ID（真人角色）。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    char_map = {c["id"]: c for c in project.get("characters", [])}
    chars = [char_map[cid] for cid in req.character_ids if cid in char_map]
    if not chars:
        raise HTTPException(status_code=400, detail="至少需要 1 个有效角色")

    names = " & ".join(c["name"] for c in chars)
    char_descs = [f"{c['name']}: {c.get('description','')[:120]}" for c in chars]
    style_extra = req.style_note or "white background, full body, standing side by side, sharp facial features, studio lighting, professional fashion photography"

    portrait_prompt = (
        f"Full-body portrait of {names}, standing side by side, facing camera. "
        f"Clean white background. {style_extra}. "
        f"{' | '.join(char_descs)}. "
        f"High detail, full body visible from head to toe, neutral pose."
    )

    try:
        from app.services.image_generation.service import ImageGenerationService

        output_dir = _LOCAL_ASSETS_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        portrait_id = f"portrait-{uuid.uuid4().hex[:8]}"
        output_filename = f"{portrait_id}.png"
        output_path = str(output_dir / output_filename)

        result = await ImageGenerationService.text_to_image(
            prompt=portrait_prompt, output_path=output_path,
            backend="apiyi", timeout=180.0,
        )

        public_url = ""
        asset_id = ""

        if result and result.success:
            image_data = Path(output_path).read_bytes()
            needs_api = asset_library_service.needs_api("数字真人")

            if needs_api and asset_library_service.is_configured:
                try:
                    asset_result = await asset_library_service.upload_and_register(
                        file_data=image_data, filename=output_filename,
                        label=f"定妆照-{names}", category="数字真人",
                    )
                    asset_id = asset_result.get("asset_id", "")
                    public_url = asset_result.get("public_url", "")
                except Exception as e:
                    logger.warning("icover upload failed, falling back to local: %s", e)

            if not asset_id:
                asset_result = asset_library_service.save_local_file(
                    file_data=image_data, filename=output_filename,
                    label=f"定妆照-{names}", category="数字真人",
                )
                asset_id = asset_result.get("asset_id", "")
                public_url = asset_result.get("public_url", "")

            if asset_id:
                for c in chars:
                    c["generated_image_url"] = public_url or f"/api/v1/assets/local-files/{output_filename}"
                    c["asset_id"] = asset_id
                    c["status"] = "done"
                save_project(req.project_id, project)

            return {
                "success": True,
                "portrait_url": public_url or f"/api/v1/assets/local-files/{output_filename}",
                "asset_id": asset_id,
                "prompt_used": portrait_prompt,
            }
        return {"success": False, "error": "生图失败", "prompt_used": portrait_prompt}
    except Exception as e:
        logger.exception("Portrait generation failed")
        raise HTTPException(status_code=502, detail=f"定妆照生成失败: {e}")
