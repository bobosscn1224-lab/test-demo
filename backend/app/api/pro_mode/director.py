"""Pro Mode Step 3 — Director Desk (导演台)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .models import DirectorSuggestRequest
from .prompt_engine import ai_analyze, build_consistency_bible
from .projects import load_project, save_project
from .shot_state import init_shot_state

router = APIRouter(prefix="/director", tags=["pro-mode-director"])

# 影响视觉风格的导演字段：变了会导致所有分镜图/视频失效
VISUAL_DIRECTOR_FIELDS = ("color_tone", "performance_style", "transitions")

DIRECTOR_PROMPT = """你是资深的影视导演。根据角色、场景和分镜，提供导演建议。

## 输出格式（严格 JSON）
{
  "pace": "节奏（快节奏/慢节奏/张弛交替，选一项并解释，50字以内）",
  "performance_style": "表演风格（自然/夸张/克制，选一项并解释，50字以内）",
  "color_tone": "色调（暖色调/冷色调/高对比/柔和，选一项并详细说明）",
  "transitions": "转场（硬切/淡入淡出/匹配剪辑，选一项并解释）",
  "overall_note": "整体导演思路概述（200字以内）"
}"""


@router.post("/suggest")
async def suggest_director(req: DirectorSuggestRequest):
    """Step 3: AI 导演建议。"""
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    char_desc = "\n".join(f"- {c['name']}: {c.get('description','')[:80]}" for c in project.get("characters", []))
    scene_desc = "\n".join(f"- {s['name']}: {s.get('description','')[:80]}" for s in project.get("scenes", []))
    shot_desc = "\n".join(f"Shot {s.get('shot_number','?')}: {s.get('description','')[:80]} [{s.get('mood','')}]" for s in project.get("shots", []))

    user_prompt = f"""## 角色\n{char_desc or '未指定'}\n\n## 场景\n{scene_desc or '未指定'}\n\n## 分镜\n{shot_desc or '未拆解'}\n\n请给出导演建议。"""

    try:
        result = await ai_analyze(DIRECTOR_PROMPT, user_prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    config = {
        "pace": result.get("pace", ""),
        "performance_style": result.get("performance_style", ""),
        "color_tone": result.get("color_tone", ""),
        "transitions": result.get("transitions", ""),
        "overall_note": result.get("overall_note", ""),
    }

    # 失效传播：视觉风格字段变化 → 所有已生成的分镜图/视频标 stale
    old_cfg = project.get("director_config") or {}
    visual_changed = any(config.get(f) != old_cfg.get(f) for f in VISUAL_DIRECTOR_FIELDS)
    affected_shots: list[int] = []
    if visual_changed:
        for shot in project.get("shots", []):
            init_shot_state(shot)
            if shot.get("frame_status") not in ("pending",):
                shot["frame_status"] = "stale"
            if shot.get("video_status") not in ("pending",):
                shot["video_status"] = "stale"
            affected_shots.append(shot.get("shot_number"))

    # 重新生成一致性圣经（导演风格变了，bible 也要更新）
    project["director_config"] = config
    project["consistency_bible"] = build_consistency_bible(project)
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_project(req.project_id, project)  # 整体保存（含失效传播后的 shots）

    return {"success": True, "director_config": config,
            "stale_shots": affected_shots, "visual_style_changed": visual_changed}
