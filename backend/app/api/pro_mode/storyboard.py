"""Pro Mode Step 2 — Storyboard (分镜计划 + 分镜关键帧)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .models import StoryboardUpdateRequest, FrameGenerateRequest, FrameBatchRequest
from .prompt_engine import ai_analyze, build_consistency_bible
from .projects import load_project, save_project, update_project
from .shot_state import init_shot_state, diff_storyboard_shots

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storyboard", tags=["pro-mode-storyboard"])

_FRAMES_DIR = Path(__file__).parent.parent.parent.parent / "data" / "local_assets"

STORYBOARD_PROMPT = """你是专业的影视分镜师。根据剧本和已确定的角色/场景/道具，拆解分镜表。

## 输出格式（严格 JSON）
{
  "shots": [
    {
      "shot_number": 1,
      "description": "画面描述（中文，50字以内）",
      "character_ids": ["char-xxx"],
      "scene_id": "scene-xxx",
      "prop_ids": ["prop-xxx"],
      "camera": "镜头运动（英文，如 medium shot slow push-in）",
      "duration": 5,
      "dialogue": "对白（中文，无则留空）",
      "mood": "情绪关键词（1-3个词）"
    }
  ]
}

## 铁律
1. character_ids/scene_id/prop_ids 必须从下方列表中选择，不要编造 ID
2. 每个镜头描述具体可执行，像写给摄影指导的指令
3. camera 必须是英文
4. duration 在 4-15 秒之间
5. 根据剧本决定镜头数（3-15）"""


class StoryboardCreateRequest(BaseModel):
    project_id: str = Field(..., description="项目 ID")


@router.post("/create")
async def create_storyboard(req: StoryboardCreateRequest):
    """Step 2: AI 拆解分镜，关联已确定的资源。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    char_list = "\n".join(f"- {c['id']}: {c['name']} — {c.get('description','')[:60]}" for c in project.get("characters", []))
    scene_list = "\n".join(f"- {s['id']}: {s['name']} — {s.get('description','')[:60]}" for s in project.get("scenes", []))
    prop_list = "\n".join(f"- {p['id']}: {p['name']}" for p in project.get("props", []))

    user_prompt = f"""## 剧本\n{project.get('script','')}\n\n## 可用角色\n{char_list or '无'}\n\n## 可用场景\n{scene_list or '无'}\n\n## 可用道具\n{prop_list or '无'}\n\n请拆解分镜表。"""

    try:
        result = await ai_analyze(STORYBOARD_PROMPT, user_prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    shots = result.get("shots", [])
    for i, shot in enumerate(shots):
        shot["shot_number"] = i + 1
        init_shot_state(shot)

    bible = build_consistency_bible(project)
    update_project(req.project_id, {
        "shots": shots,
        "consistency_bible": bible,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"success": True, "project": load_project(req.project_id)}


@router.put("/{project_id}")
async def update_storyboard(project_id: str, req: StoryboardUpdateRequest):
    """手动调整分镜表（自动失效传播：改视觉字段的镜头，分镜图和视频标 stale）。"""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    updates: dict = {}
    stale_stats: dict | None = None
    if req.script is not None:
        updates["script"] = req.script
    if req.shots is not None:
        new_shots = [s.model_dump() for s in req.shots]
        stale_stats = diff_storyboard_shots(project.get("shots", []), new_shots)
        updates["shots"] = new_shots

    update_project(project_id, updates)
    resp: dict = {"success": True, "project": load_project(project_id)}
    if stale_stats:
        resp["stale_stats"] = stale_stats
    return resp


# ── 分镜关键帧（首帧图） ──────────────────────────────────────────

def build_frame_prompt(project: dict, shot: dict) -> str:
    """组装分镜关键帧的生图 prompt（场景风格 + 角色外观 + 镜头画面）。"""
    char_map = {c["id"]: c for c in project.get("characters", [])}
    scene_map = {s["id"]: s for s in project.get("scenes", [])}
    dir_cfg = project.get("director_config") or {}

    parts: list[str] = []

    scene = scene_map.get(shot.get("scene_id", ""))
    if scene and scene.get("image_prompt"):
        parts.append(scene["image_prompt"])
    elif scene:
        parts.append(scene.get("description", ""))

    char_descs = []
    for cid in shot.get("character_ids", []):
        c = char_map.get(cid)
        if c:
            char_descs.append(c.get("image_prompt") or c.get("description", ""))
    if char_descs:
        parts.append("Characters: " + " | ".join(char_descs))

    if shot.get("description"):
        parts.append(f"Action: {shot['description']}")
    if shot.get("camera"):
        parts.append(f"Camera: {shot['camera']}")

    style_bits = []
    if dir_cfg.get("color_tone"):
        style_bits.append(str(dir_cfg["color_tone"]))
    style_bits.append("cinematic film still, consistent character appearance, high detail")
    parts.append("Style: " + ", ".join(style_bits))

    return "\n".join(p for p in parts if p)


async def _generate_frame_for_shot(project: dict, shot: dict) -> dict:
    """为单个镜头生成关键帧，返回 {"success", "frame_image_url" | "error"}。"""
    from app.services.image_generation.service import ImageGenerationService

    project_id = project["id"]
    sn = shot["shot_number"]
    frame_prompt = build_frame_prompt(project, shot)

    _FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"frame-{project_id}-shot{sn}-{uuid.uuid4().hex[:6]}.png"
    output_path = str(_FRAMES_DIR / filename)

    try:
        result = await ImageGenerationService.text_to_image(
            prompt=frame_prompt, output_path=output_path,
            backend="apiyi", timeout=180.0,
        )
    except Exception as e:
        logger.exception("Frame generation failed for shot %s", sn)
        return {"success": False, "error": str(e), "prompt_used": frame_prompt}

    if result and result.success:
        return {
            "success": True,
            "frame_image_url": f"/api/v1/assets/local-files/{filename}",
            "prompt_used": frame_prompt,
        }
    return {"success": False, "error": "生图失败", "prompt_used": frame_prompt}


@router.post("/frame")
async def generate_shot_frame(req: FrameGenerateRequest):
    """Step 2.5a: 为单个镜头生成分镜关键帧（后续作为视频首帧锚定）。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shot = next((s for s in project.get("shots", []) if s.get("shot_number") == req.shot_number), None)
    if not shot:
        raise HTTPException(status_code=404, detail=f"Shot {req.shot_number} 不存在")

    init_shot_state(shot)
    shot["frame_status"] = "generating"
    save_project(req.project_id, project)

    result = await _generate_frame_for_shot(project, shot)

    # 重新加载，避免覆盖生成期间的其他写入
    project = load_project(req.project_id) or project
    shot = next((s for s in project.get("shots", []) if s.get("shot_number") == req.shot_number), shot)
    init_shot_state(shot)
    if result["success"]:
        shot["frame_image_url"] = result["frame_image_url"]
        shot["frame_status"] = "done"
        # 画面变了，旧视频失效
        if shot.get("video_status") not in ("pending",):
            shot["video_status"] = "stale"
    else:
        shot["frame_status"] = "failed"
        shot["error"] = result.get("error", "")
    save_project(req.project_id, project)

    return {**result, "shot_number": req.shot_number, "frame_status": shot["frame_status"]}


@router.post("/frame-all")
async def generate_all_frames(req: FrameBatchRequest):
    """Step 2.5b: 批量为 pending/failed/stale 的镜头生成关键帧。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shots = project.get("shots", [])
    if not shots:
        raise HTTPException(status_code=400, detail="项目还没有分镜")

    results = []
    for shot in shots:
        init_shot_state(shot)
        if shot.get("frame_status") not in ("pending", "failed", "stale"):
            results.append({"shot_number": shot["shot_number"], "status": "skipped"})
            continue

        shot["frame_status"] = "generating"
        save_project(req.project_id, project)

        result = await _generate_frame_for_shot(project, shot)

        project = load_project(req.project_id) or project
        shot = next((s for s in project.get("shots", []) if s.get("shot_number") == shot["shot_number"]), shot)
        init_shot_state(shot)
        if result["success"]:
            shot["frame_image_url"] = result["frame_image_url"]
            shot["frame_status"] = "done"
            if shot.get("video_status") not in ("pending",):
                shot["video_status"] = "stale"
            results.append({"shot_number": shot["shot_number"], "status": "done"})
        else:
            shot["frame_status"] = "failed"
            shot["error"] = result.get("error", "")
            results.append({"shot_number": shot["shot_number"], "status": "failed", "error": result.get("error", "")})
        save_project(req.project_id, project)

    done = sum(1 for r in results if r["status"] == "done")
    return {"success": True, "total": len(results), "done": done, "results": results,
            "project": load_project(req.project_id)}
