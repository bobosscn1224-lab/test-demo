"""Stage: entry menu — choose how to start making the PPT."""

from app.skills.base import SkillContext, SkillResult
from ..constants import ENTRY_MENU


async def handle(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Parse entry choice and set the appropriate next stage."""
    msg = context.user_message.strip()

    choice = _parse_choice(msg)
    if not choice:
        return SkillResult(
            success=True,
            message=f"请选择一个入口：\n\n{ENTRY_MENU}",
            data={"skill": "ppt_maker", "stage": "menu"},
        )

    # Entry 1: briefing → upload docs → generate outline → full pipeline
    if choice == "1":
        sessions[session_id] = {"stage": "briefing", "entry": "1", "briefing": {}}
        from .briefing import BRIEFING_PROMPT
        return SkillResult(
            success=True,
            message=BRIEFING_PROMPT,
            data={"skill": "ppt_maker", "stage": "briefing"},
        )

    # Entry 2: provide outline → start from step 2
    if choice == "2":
        sessions[session_id] = {"stage": "outline_direct", "entry": "2"}
        return SkillResult(
            success=True,
            message="请粘贴已确认的 PPT 大纲和逐页内容。收到后我将从第 2 步开始生成缩略图。",
            data={"skill": "ppt_maker", "stage": "outline_direct"},
        )

    # Entry 3: upload collage → start from step 3
    if choice == "3":
        sessions[session_id] = {"stage": "collage_upload", "entry": "3"}
        return SkillResult(
            success=True,
            message="请上传 PPT 整体详细缩略图，并告诉我总页数和每页标题。\n\n格式示例：\n共 5 页\n第 1 页：封面\n第 2 页：项目背景\n...",
            data={"skill": "ppt_maker", "stage": "collage_upload"},
        )

    # Entry 4: upload single page image → direct to PPTX
    if choice == "4":
        sessions[session_id] = {"stage": "pptx_direct", "entry": "4"}
        return SkillResult(
            success=True,
            message="请上传一张高清 PPT 风格图（PNG/JPG），我将直接生成可编辑 PPTX。",
            data={"skill": "ppt_maker", "stage": "pptx_direct"},
        )

    return SkillResult(success=True, message=f"请选择 1-4：\n\n{ENTRY_MENU}")


def _parse_choice(msg: str) -> str | None:
    """Parse natural language entry choice into '1'/'2'/'3'/'4'."""
    m = msg.strip()

    # Direct number match
    for num in ["1", "2", "3", "4"]:
        if m == num or m.startswith(f"选{num}") or m.startswith(f"第{num}"):
            return num

    # Semantic match
    if any(kw in m for kw in ["上传文档", "生成大纲", "输入内容", "入口1", "第一步", "第1步", "完整流程"]):
        return "1"
    if any(kw in m for kw in ["ppt大纲", "ppt的大纲", "提供大纲", "入口2", "第二步", "第2步", "直接给大纲"]):
        return "2"
    if any(kw in m for kw in ["缩略图", "整体详细缩略图", "入口3", "第三步", "第3步", "分页高清"]):
        return "3"
    if any(kw in m for kw in ["可编辑ppt", "可编辑 PPT", "入口4", "第四步", "第4步", "单页高清", "某一页"]):
        return "4"

    return None
