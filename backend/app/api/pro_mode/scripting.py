"""Pro Mode Step 0 — Script Structuring (剧本结构化).

Converts raw story/novel text into a structured, shootable script.
This is the preprocessing step before resource extraction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .models import ScriptStructureRequest, TEMPLATES
from .prompt_engine import ai_analyze

router = APIRouter(prefix="/script", tags=["pro-mode-script"])

STRUCTURING_PROMPT = """你是专业的影视剧本结构化专家。将用户提供的原始故事/小说文本，转换为可用于 AI 视频生成的标准化短剧剧本。

## 输出格式（严格 JSON）
{
  "title": "短剧标题（15字以内）",
  "genre": "类型标签",
  "summary": "一句话剧情概述（50字以内）",
  "structured_script": "结构化后的标准剧本全文（保留所有关键情节、对白、动作，但转换为分场景格式，每个场景标注：场景描述 + 人物动作 + 对白。删除心理描写、内心独白、环境渲染等无法影视化的内容，转化为画面语言）",
  "characters": [
    {
      "name": "角色名",
      "description": "外貌和气质描述（80字以内，侧重可用于画图的视觉特征）",
      "traits": ["性格标签"],
      "image_prompt": "英文图片生成提示词，正面照，包含面部特征/发型/服装/光影风格"
    }
  ],
  "scenes": [
    {
      "name": "场景名",
      "description": "空间描述（80字以内，侧重视觉化细节）",
      "time_of_day": "白天/夜晚/黄昏/清晨",
      "image_prompt": "英文图片生成提示词，空镜，包含空间布局/光源/色调"
    }
  ],
  "props": [
    {
      "name": "道具名",
      "description": "外观描述（40字以内）",
      "image_prompt": "英文图片生成提示词，白底产品图"
    }
  ],
  "total_estimated_shots": 15,
  "estimated_duration_seconds": 60
}

## 铁律
1. 角色2-5个，场景2-5个，道具只提取反复出现的关键道具（0-3个）
2. structured_script 必须是可直接用于分镜拆解的标准格式
3. 删除所有心理描写、旁白、文学修辞，全部转为画面语言和动作描述
4. image_prompt 必须是英文，具体可直接用于 AI 生图
5. 角色描述侧重外貌特征（面部/发型/体型/服装），不写性格"""

TEMPLATE_HINT_PROMPT = """

## 使用模板：{template_name}
- 节奏风格：{pace}
- 表演风格：{performance_style}
- 色调：{color_tone}
- 镜头风格：{camera_style}
- 结构提示：{structure_hint}

请在结构化时融入以上风格参数。"""


@router.post("/structure")
async def structure_script(req: ScriptStructureRequest):
    """Step 0: 将原始故事/小说转化为标准短剧剧本。

    输入：原始故事文本（可以是不规范的文学描述）
    输出：结构化标准剧本 + 角色列表 + 场景列表 + 道具列表

    持久化：结果保存到 projects.json，后续步骤基于此结构化数据。
    """
    if len(req.story.strip()) < 10:
        raise HTTPException(status_code=400, detail="故事文本太短，至少需要 10 个字符")

    # Build prompt with optional template
    user_prompt = f"## 原始故事/小说\n{req.story}"

    template_name = req.template.strip()
    if template_name and template_name in TEMPLATES:
        t = TEMPLATES[template_name]
        user_prompt += TEMPLATE_HINT_PROMPT.format(
            template_name=template_name,
            pace=t.get("pace", ""),
            performance_style=t.get("performance_style", ""),
            color_tone=t.get("color_tone", ""),
            camera_style=t.get("camera_style", ""),
            structure_hint=t.get("structure_hint", ""),
        )

    try:
        result = await ai_analyze(STRUCTURING_PROMPT, user_prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    # Assign IDs and build project
    project_id = f"proj-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    characters = []
    for c in result.get("characters", []):
        c["id"] = f"char-{uuid.uuid4().hex[:6]}"
        c["generated_image_url"] = ""
        c["asset_id"] = ""
        c["status"] = "pending"
        characters.append(c)

    scenes = []
    for s in result.get("scenes", []):
        s["id"] = f"scene-{uuid.uuid4().hex[:6]}"
        s["generated_image_url"] = ""
        s["asset_id"] = ""
        s["status"] = "pending"
        scenes.append(s)

    props = []
    for p in result.get("props", []):
        p["id"] = f"prop-{uuid.uuid4().hex[:6]}"
        p["generated_image_url"] = ""
        p["asset_id"] = ""
        p["status"] = "pending"
        props.append(p)

    # Apply template defaults to director_config
    dir_defaults = {}
    if template_name and template_name in TEMPLATES:
        t = TEMPLATES[template_name]
        dir_defaults = {
            "pace": t.get("pace", ""),
            "performance_style": t.get("performance_style", ""),
            "color_tone": t.get("color_tone", ""),
            "transitions": t.get("transitions", ""),
            "overall_note": f"使用「{template_name}」模板：{t.get('structure_hint','')}",
        }

    project = {
        "id": project_id,
        "title": result.get("title", "未命名项目"),
        "genre": result.get("genre", template_name or ""),
        "summary": result.get("summary", ""),
        "script": result.get("structured_script", req.story),
        "raw_story": req.story,
        "structured_script": result.get("structured_script", ""),
        "characters": characters,
        "scenes": scenes,
        "props": props,
        "shots": [],
        "director_config": dir_defaults if dir_defaults else None,
        "current_step": 0,
        "template": template_name or "",
        "total_estimated_shots": result.get("total_estimated_shots", 15),
        "estimated_duration_seconds": result.get("estimated_duration_seconds", 60),
        "created_at": now,
        "updated_at": now,
    }

    # Persist
    from .projects import save_project
    save_project(project_id, project)

    return {"success": True, "project": project}


@router.get("/templates")
async def list_templates():
    """列出所有可用的短剧模板及其参数。"""
    return {"success": True, "templates": TEMPLATES}
