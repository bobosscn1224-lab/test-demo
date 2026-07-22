"""Pro Mode Step 1 — Resource Generation (资源生成).

Extracts characters/scenes/props from structured script, generates images.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.asset_library_service import asset_library_service

from .models import (
    ScriptAnalyzeRequest,
    ResourceGenerateRequest,
    ResourceGenerateAllRequest,
    ResourceUploadAssetRequest,
)
from .prompt_engine import ai_analyze
from .projects import load_project, save_project, update_project
from .shot_state import invalidate_shots_using_resource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resource", tags=["pro-mode-resource"])

RESOURCE_ANALYSIS_PROMPT = """你是专业的影视资源分析师。从标准剧本中提取所有角色、场景和关键道具的视觉描述。

## 输出格式（严格 JSON）
{
  "characters": [
    {
      "name": "角色名",
      "description": "外貌描述（80字以内，具体到可用于画图）",
      "traits": ["性格标签"],
      "image_prompt": "英文图片生成提示词，正面照，含面部特征/发型/服装/光影"
    }
  ],
  "scenes": [
    {
      "name": "场景名",
      "description": "空间描述（80字以内）",
      "time_of_day": "白天/夜晚/黄昏/清晨",
      "image_prompt": "英文图片生成提示词，空镜，含空间布局/光源/色调"
    }
  ],
  "props": [
    {
      "name": "道具名",
      "description": "外观描述（40字以内）",
      "image_prompt": "英文图片生成提示词，白底产品图"
    }
  ]
}

## 铁律
1. 角色2-5个，场景2-5个
2. 道具只提取反复出现的关键道具（0-3个），普通物品不要提取
3. image_prompt 必须是英文，可直接用于生图"""


@router.post("/extract")
async def extract_resources(req: ScriptAnalyzeRequest):
    """Step 1a: 从结构化剧本中提取角色/场景/道具的视觉描述。

    输入：结构化剧本（由 Step 0 产出）
    输出：带视觉描述和生图 prompt 的角色/场景/道具列表
    """
    if len(req.script.strip()) < 10:
        raise HTTPException(status_code=400, detail="剧本内容太短")

    try:
        result = await ai_analyze(RESOURCE_ANALYSIS_PROMPT, f"## 剧本\n{req.script}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    project_id = f"proj-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    characters = []
    for c in result.get("characters", []):
        c["id"] = f"char-{uuid.uuid4().hex[:6]}"
        c["generated_image_url"] = c["asset_id"] = ""
        c["status"] = "pending"
        characters.append(c)

    scenes = []
    for s in result.get("scenes", []):
        s["id"] = f"scene-{uuid.uuid4().hex[:6]}"
        s["generated_image_url"] = s["asset_id"] = ""
        s["status"] = "pending"
        scenes.append(s)

    props = []
    for p in result.get("props", []):
        p["id"] = f"prop-{uuid.uuid4().hex[:6]}"
        p["generated_image_url"] = p["asset_id"] = ""
        p["status"] = "pending"
        props.append(p)

    project = {
        "id": project_id, "title": "未命名", "genre": "", "summary": "",
        "script": req.script, "characters": characters, "scenes": scenes,
        "props": props, "shots": [], "director_config": None,
        "current_step": 1, "template": "",
        "created_at": now, "updated_at": now,
    }
    save_project(project_id, project)
    return {"success": True, "project": project}


@router.post("/generate")
async def generate_resource(req: ResourceGenerateRequest):
    """Step 1b: 为单个资源生图，存入素材库。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    collection = project.get(req.resource_type, [])
    resource = next((r for r in collection if r.get("id") == req.resource_id), None)
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")
    if not resource.get("image_prompt"):
        raise HTTPException(status_code=400, detail="该资源没有 image_prompt")

    resource["status"] = "generating"
    save_project(req.project_id, project)

    try:
        from app.services.image_generation.service import ImageGenerationService

        output_dir = Path(__file__).parent.parent.parent.parent / "data" / "local_assets"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"pro-{req.resource_id}.png"
        output_path = str(output_dir / output_filename)

        result = await ImageGenerationService.text_to_image(
            prompt=resource["image_prompt"],
            output_path=output_path,
            backend="apiyi",
            timeout=180.0,
        )

        if result and result.success:
            public_url = f"/api/v1/assets/local-files/{output_filename}"
            asset_result = asset_library_service.save_local_file(
                file_data=Path(output_path).read_bytes(),
                filename=output_filename,
                label=resource.get("name", "resource"),
                category="数字真人" if req.resource_type == "characters" else "场景" if req.resource_type == "scenes" else "道具",
            )
            resource["generated_image_url"] = public_url
            resource["asset_id"] = asset_result.get("asset_id", "")
            resource["status"] = "done"
            # 失效传播：资源图更新后，引用该资源的分镜图/视频标 stale
            affected = invalidate_shots_using_resource(project, req.resource_type, req.resource_id)
            if affected:
                logger.info("Resource %s updated, invalidated shots: %s", req.resource_id, affected)
        else:
            resource["status"] = "failed"
    except Exception as e:
        logger.exception("Image generation failed")
        resource["status"] = "failed"

    save_project(req.project_id, project)
    return {"success": resource["status"] == "done", "resource": resource}


@router.post("/generate-all")
async def generate_all_resources(req: ResourceGenerateAllRequest):
    """Step 1b: 批量生成所有未完成的资源图。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    results = {"characters": [], "scenes": [], "props": []}
    from app.services.image_generation.service import ImageGenerationService

    output_dir = Path(__file__).parent.parent.parent.parent / "data" / "local_assets"
    output_dir.mkdir(parents=True, exist_ok=True)

    for rtype in ["characters", "scenes", "props"]:
        for resource in project.get(rtype, []):
            if resource.get("status") == "done":
                results[rtype].append({"id": resource["id"], "name": resource["name"], "status": "skipped"})
                continue
            if not resource.get("image_prompt"):
                results[rtype].append({"id": resource["id"], "name": resource["name"], "status": "no_prompt"})
                continue

            try:
                resource["status"] = "generating"
                save_project(req.project_id, project)

                output_filename = f"pro-{resource['id']}.png"
                output_path = str(output_dir / output_filename)
                result = await ImageGenerationService.text_to_image(
                    prompt=resource["image_prompt"], output_path=output_path,
                    backend="apiyi", timeout=180.0,
                )

                if result and result.success:
                    public_url = f"/api/v1/assets/local-files/{output_filename}"
                    asset_library_service.save_local_file(
                        file_data=Path(output_path).read_bytes(),
                        filename=output_filename,
                        label=resource.get("name", "resource"),
                        category="数字真人" if rtype == "characters" else "场景" if rtype == "scenes" else "道具",
                    )
                    resource["generated_image_url"] = public_url
                    resource["status"] = "done"
                    # 失效传播：资源图更新后，引用该资源的分镜标 stale
                    affected = invalidate_shots_using_resource(project, rtype, resource["id"])
                    if affected:
                        logger.info("Resource %s updated, invalidated shots: %s", resource["id"], affected)
                    results[rtype].append({"id": resource["id"], "name": resource["name"], "status": "done"})
                else:
                    resource["status"] = "failed"
                    results[rtype].append({"id": resource["id"], "name": resource["name"], "status": "failed"})
            except Exception as e:
                logger.exception("Batch generation failed")
                resource["status"] = "failed"
                results[rtype].append({"id": resource["id"], "name": resource["name"], "status": "failed", "error": str(e)})

    save_project(req.project_id, project)
    return {"success": True, "results": results}


@router.post("/upload-asset")
async def upload_resource_to_asset_library(req: ResourceUploadAssetRequest):
    """将已有资源图上传到 icover 素材库，获取 asset:// ID。

    用于已生成本地图但还没有 icover asset:// ID 的资源。
    数字真人角色必须有 asset:// ID 才能在 Seedance 视频生成中作为参考素材。
    """
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    collection = project.get(req.resource_type, [])
    resource = next((r for r in collection if r.get("id") == req.resource_id), None)
    if not resource:
        raise HTTPException(status_code=404, detail="资源不存在")

    # 必须已有生成图
    image_url = resource.get("generated_image_url", "")
    if not image_url:
        raise HTTPException(status_code=400, detail="该资源还没有生成图片，请先生成")

    # 已经有 asset:// ID 就不用再上传
    existing_asset_id = resource.get("asset_id", "")
    if existing_asset_id and existing_asset_id.startswith("asset-"):
        return {"success": True, "asset_id": existing_asset_id,
                "message": "该资源已有 asset:// ID，无需重复上传"}

    # 从本地磁盘读取图片文件
    prefix = "/api/v1/assets/local-files/"
    if prefix not in image_url:
        raise HTTPException(status_code=400, detail="图片 URL 格式不支持上传，请重新生成图片")

    filename = image_url.split(prefix, 1)[1]
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="文件名不合法")

    local_path = Path(__file__).parent.parent.parent.parent / "data" / "local_assets" / filename
    if not local_path.exists():
        raise HTTPException(status_code=404, detail=f"本地图片文件不存在: {filename}")

    cat_map = {"characters": "数字真人", "scenes": "场景", "props": "道具"}
    category = cat_map.get(req.resource_type, "其他")
    label = resource.get("name", "resource")

    try:
        image_data = local_path.read_bytes()

        needs_api = asset_library_service.needs_api(category)
        asset_id = ""
        public_url = ""

        if needs_api and asset_library_service.is_configured:
            try:
                asset_result = await asset_library_service.upload_and_register(
                    file_data=image_data, filename=filename,
                    label=label, category=category,
                )
                asset_id = asset_result.get("asset_id", "")
                public_url = asset_result.get("public_url", "")
            except Exception as e:
                logger.warning("icover upload failed, falling back to local: %s", e)

        if not asset_id:
            # 非 API 必需类别或 API 失败时，走本地存储
            asset_result = asset_library_service.save_local_file(
                file_data=image_data, filename=filename,
                label=label, category=category,
            )
            asset_id = asset_result.get("asset_id", "")
            public_url = asset_result.get("public_url", "")

        if asset_id:
            resource["asset_id"] = asset_id
            if public_url:
                resource["generated_image_url"] = public_url
            # 失效传播：资源图/asset_id 变更 → 引用该资源的分镜标 stale
            affected = invalidate_shots_using_resource(project, req.resource_type, req.resource_id)
            if affected:
                logger.info("Resource %s asset updated, invalidated shots: %s", req.resource_id, affected)
            save_project(req.project_id, project)
            return {
                "success": True,
                "asset_id": asset_id,
                "asset_url": f"asset://{asset_id}" if asset_id.startswith("asset-") else public_url,
                "is_icover": asset_id.startswith("asset-"),
                "resource": resource,
            }
        raise HTTPException(status_code=500, detail="上传素材库失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload to asset library failed")
        raise HTTPException(status_code=502, detail=f"上传素材库失败: {e}")
