"""Stage: outline generation, confirmation, and direct outline input."""

from app.skills.base import SkillContext, SkillResult
from app.services.llm_service import llm_service
from app.utils.file_parser import parse_file_sync
from ..constants import CONFIRM_WORDS
from ..prompts import OUTLINE_SYSTEM, OUTLINE_USER
from . import collage, briefing as briefing_stage


async def handle_briefing_confirm(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """User confirmed/rejected the briefing summary."""
    msg = context.user_message.strip()

    if _is_confirm(msg):
        # Move to content collection
        sessions[session_id] = {**session, "stage": "outline"}
        return SkillResult(
            success=True,
            message="需求已确认！请上传文档或输入内容，我将基于你的需求生成专业大纲。",
            data={"skill": "ppt_maker", "stage": "outline"},
        )

    # Not confirm — go back to briefing for modification
    sessions[session_id] = {**session, "stage": "briefing"}
    return SkillResult(
        success=True,
        message=f"好的，请说明需要修改的部分。\n\n{briefing_stage.QUESTIONS[0][1]}",
        data={"skill": "ppt_maker", "stage": "briefing"},
    )


async def handle_outline(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Entry 1: collect content → generate outline → await confirmation."""
    source = await _collect_text(context)
    msg = context.user_message.strip()

    # Not enough content yet — ask for more
    if not source or (len(source) < 80 and _is_trigger_only(msg)):
        return SkillResult(
            success=True,
            message="请上传文档或输入内容，内容越详细，大纲质量越高。",
            data={"skill": "ppt_maker", "stage": "outline"},
        )

    return await _generate_outline(session_id, source, sessions, briefing=session.get("briefing"))


async def handle_outline_direct(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Entry 2: user provides outline directly → go to collage step."""
    source = await _collect_text(context)
    msg = context.user_message.strip()

    if not source or len(source) < 80:
        return SkillResult(
            success=True,
            message="请粘贴完整的 PPT 大纲和逐页内容（至少 80 字）。",
            data={"skill": "ppt_maker", "stage": "outline_direct"},
        )

    sessions[session_id] = {"stage": "collage_confirm", "entry": "2", "outline": source}
    return SkillResult(
        success=True,
        message="已收到大纲。请回复「开始」或「确认」，我将生成三版 PPT 视觉缩略图。",
        data={"skill": "ppt_maker", "stage": "collage_confirm"},
    )


async def handle_confirm(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Handle outline confirmation or revision request."""
    msg = context.user_message.strip()

    if _is_confirm(msg):
        sessions[session_id]["stage"] = "collage_confirm"
        return SkillResult(
            success=True,
            message="收到确认。请回复「开始」，我将进入第 2 步生成三版 PPT 缩略图。",
            data={"skill": "ppt_maker", "stage": "collage_confirm"},
        )

    # Not confirm — treat as revision
    source = await _collect_text(context)
    if source or len(msg) > 10:
        return await _generate_outline(session_id, source, sessions, revision=msg, briefing=session.get("briefing"))

    return SkillResult(
        success=True,
        message="请确认大纲是否可以进入下一步，或直接告诉我需要修改的地方。",
        data={"skill": "ppt_maker", "stage": "outline_confirm"},
    )


async def _generate_outline(session_id: str, source: str, sessions: dict, revision: str = "", briefing: dict | None = None) -> SkillResult:
    """Call LLM to generate PPT outline with strategic briefing context."""
    revision_text = f"\n\n用户修改要求：\n{revision}" if revision else ""

    # Build briefing context
    briefing_text = ""
    if briefing:
        briefing_text = f"""
## 用户需求简报（必须严格遵守）

- **演示目的**：{briefing.get('purpose', '未指定')}
- **目标受众**：{briefing.get('audience', '未指定')}
- **期望规模**：{briefing.get('scope', '未指定')}
- **风格偏好**：{briefing.get('style', '未指定')}
- **核心信息**：{briefing.get('key_message', '未指定')}

请根据以上需求简报调整大纲的侧重点、深度、语言风格和叙事节奏。
"""
    prompt = OUTLINE_USER.format(
        briefing_text=briefing_text,
        source_text=source[:8000],
        revision_text=revision_text,
    )

    try:
        resp = await llm_service.chat(
            system_prompt=OUTLINE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192, temperature=0.3, timeout=180,
            thinking={"type": "disabled"},
        )
        outline = ""
        if resp.content:
            for block in resp.content:
                if hasattr(block, "text"):
                    outline += block.text
    except Exception as exc:
        return SkillResult(success=False, message=f"生成 PPT 大纲时出错：{exc}")

    outline = outline.strip()
    if "确认" not in outline:
        outline += "\n\n请确认以上 PPT 大纲和逐页内容是否可以进入下一步。"

    sessions[session_id] = {"stage": "outline_confirm", "entry": "1", "outline": outline}
    return SkillResult(
        success=True,
        message=outline,
        data={"skill": "ppt_maker", "stage": "outline_confirm"},
    )


async def _collect_text(context: SkillContext) -> str:
    """Collect text from user message and uploaded files."""
    parts = [context.user_message.strip()]
    for f in (context.uploaded_files or []):
        try:
            text = await parse_file_sync(f.get("path", ""))
            if text:
                parts.append(text[:30000])
        except Exception:
            pass
    return "\n\n---\n\n".join(p for p in parts if p)


def _is_confirm(msg: str) -> bool:
    """Check if message is a confirmation."""
    m = msg.strip().lower()
    if len(m) > 15:
        return False
    return any(w in m for w in CONFIRM_WORDS)


def _is_trigger_only(msg: str) -> bool:
    """Check if message is just a trigger word with no real content."""
    from ..constants import TRIGGERS, KEYWORDS
    clean = msg.strip().lower().replace(" ", "")
    for t in TRIGGERS + KEYWORDS:
        if clean == t.lower().replace(" ", ""):
            return True
    return False
