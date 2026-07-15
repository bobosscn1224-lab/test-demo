"""Stage: visual collage generation — 3 visual directions (A/B/C) + user choice."""

import os
import uuid

from app.skills.base import SkillContext, SkillResult
from app.services._paths import PUBLIC_DIR
from ..constants import IMAGE_TIMEOUT, CONFIRM_WORDS
from ..prompts import (
    COLLAGE_BASE, VISUAL_DIRECTIONS, STEP2_PROGRESS,
    COLLAGE_RESULT_TEMPLATE, COLLAGE_CHOICE_PROMPT,
)
from .. import image_gen


async def handle_collage_confirm(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """User confirmed — start generating collages."""
    msg = context.user_message.strip()
    if not _is_start(msg):
        return SkillResult(
            success=True,
            message="请回复「开始」或「继续」，我将生成三版 PPT 视觉缩略图。",
            data={"skill": "ppt_maker", "stage": "collage_confirm"},
        )
    return await _run_collage_generation(session, sessions, session_id)


async def handle_visual_choice(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """User selects a visual direction (A/B/C) or requests regeneration."""
    msg = context.user_message.strip()

    # Check for regeneration request
    if any(w in msg for w in ["不满意", "都不满意", "重新生成", "重做", "再生成"]):
        sessions[session_id]["stage"] = "outline_confirm"  # Go back to outline
        return SkillResult(
            success=True,
            message="好的，请告诉我大纲需要如何调整，我将重新生成。",
            data={"skill": "ppt_maker", "stage": "outline_confirm"},
        )

    # Parse choice
    choice = _parse_choice(msg)
    if not choice:
        return _show_current_collages(session)

    # Store choice and move to step 3
    sessions[session_id]["selected_visual"] = choice
    sessions[session_id]["stage"] = "pages_confirm"
    return SkillResult(
        success=True,
        message=f"已选择方案 {choice}。请回复「开始」，我将逐页生成高清 16:9 单页 PPT 视觉稿。",
        data={"skill": "ppt_maker", "stage": "pages_confirm"},
    )


def _show_current_collages(session: dict) -> SkillResult:
    """Show the generated collages and ask for choice."""
    collages = session.get("visual_collages", [])
    if not collages:
        return SkillResult(success=True, message="暂无生成的方案。")
    lines = ["当前已生成的 PPT 拼图方案如下：\n"]
    for c in collages:
        lines.append(f"![方案 {c['label']}](/api/skills/download/{c['filename']})")
        lines.append(f"[下载方案 {c['label']} 拼图](/api/skills/download/{c['filename']})\n")
    lines.append("请选择方案 A / B / C，或回复「重新生成」重做。")
    return SkillResult(success=True, message="\n".join(lines))


# ── Collage generation (called from execute_stream) ───────────────

async def resume_stream(session: dict, sessions: dict, session_id: str):
    """Resume collage generation after interruption — skip already-done variants."""
    existing = session.get("visual_collages", [])
    done_labels = {c["label"] for c in existing}
    outline = str(session.get("outline", "")).strip()
    if not outline:
        yield SkillResult(success=False, message="未找到已确认的大纲内容。请重新提供大纲。")
        return

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    all_prompts = _build_prompts(outline)

    for idx, (label, prompt) in enumerate(all_prompts, 1):
        if label in done_labels:
            continue  # skip already-done
        filename = f"ppt_maker_{session_id[:8]}_{run_id}_{label.lower()}.png"
        out_path = os.path.join(output_dir, filename)
        yield f"进度 4/4：正在生成方案 {label} 的完整 PPT 拼图（{len(done_labels)+1}/3）...\n"

        error = await image_gen.generate(prompt, out_path, timeout=IMAGE_TIMEOUT)
        if error:
            yield SkillResult(success=False, message=f"方案 {label} 生成失败。\n\n{error}")
            return

        existing.append({"label": label, "filename": filename, "path": out_path})
        sessions[session_id] = {**sessions.get(session_id, {}), "visual_collages": existing}

        all_done = [c["label"] for c in existing]
        filler = "\n\n请选择方案 A / B / C，或回复「重新生成」重做。" if len(all_done) == 3 else ""
        yield SkillResult(
            success=True,
            message=COLLAGE_RESULT_TEMPLATE.format(label=label, filename=filename, filler=filler),
            data={"skill": "ppt_maker"},
        )

    sessions[session_id]["stage"] = "collage_choice"
    yield SkillResult(
        success=True,
        message=f"三版方案已全部生成！请选择方案 A / B / C，或回复「重新生成」重做。",
        data={"skill": "ppt_maker", "stage": "collage_choice"},
    )


async def generate_stream(session: dict, sessions: dict, session_id: str):
    """Async generator: run step 2 collage generation with progress updates."""
    outline = str(session.get("outline", "")).strip()
    if not outline:
        yield SkillResult(success=False, message="未找到已确认的大纲内容。请重新提供大纲。")
        return

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    generated = []

    sessions[session_id] = {**session, "stage": "collage_generating"}

    for i, msg in enumerate(STEP2_PROGRESS):
        yield msg + "\n"

    for idx, (label, prompt) in enumerate(_build_prompts(outline), 1):
        filename = f"ppt_maker_{session_id[:8]}_{run_id}_{label.lower()}.png"
        out_path = os.path.join(output_dir, filename)
        yield f"进度 4/4：正在生成方案 {label} 的完整 PPT 拼图（{idx}/3）...\n"

        error = await image_gen.generate(prompt, out_path, timeout=IMAGE_TIMEOUT)
        if error:
            yield SkillResult(
                success=False,
                message=f"方案 {label} 生成失败。\n\n{error}",
            )
            return

        generated.append({"label": label, "filename": filename, "path": out_path})
        sessions[session_id] = {**sessions.get(session_id, {}), "visual_collages": generated}

        filler = "\n\n" + COLLAGE_CHOICE_PROMPT if idx == 3 else ""
        yield SkillResult(
            success=True,
            message=COLLAGE_RESULT_TEMPLATE.format(label=label, filename=filename, filler=filler),
            data={"skill": "ppt_maker"},
        )

    sessions[session_id]["stage"] = "collage_choice"
    yield SkillResult(
        success=True,
        message=f"三版方案已全部生成！" + COLLAGE_CHOICE_PROMPT,
        data={"skill": "ppt_maker", "stage": "collage_choice"},
    )


async def _run_collage_generation(session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Non-streaming version — returns immediately, caller should use generate_stream for stream."""
    return SkillResult(
        success=True,
        message="正在生成三版 PPT 视觉缩略图...",
        data={"skill": "ppt_maker", "stage": "collage_generating"},
    )


def _build_prompts(outline: str) -> list[tuple[str, str]]:
    """Build 3 collage prompts from the outline."""
    compact = outline[:9000]
    base = COLLAGE_BASE.format(outline=compact)
    return [
        ("A", base + "\n\n" + VISUAL_DIRECTIONS["A"]),
        ("B", base + "\n\n" + VISUAL_DIRECTIONS["B"]),
        ("C", base + "\n\n" + VISUAL_DIRECTIONS["C"]),
    ]


def _is_start(msg: str) -> bool:
    """Check if message means 'start'. More specific than general confirm."""
    m = msg.strip().lower().replace(" ", "")
    if len(m) > 10:
        return False
    return any(w in m for w in ["开始", "继续", "确认", "可以", "ok", "yes", "好", "行", "确定", "好的"])


def _parse_choice(msg: str) -> str | None:
    """Parse A/B/C visual choice."""
    m = msg.strip().upper().replace(" ", "")
    m = m.replace("方案", "").replace("选择", "").replace("我选", "").replace("选", "")
    m = m.strip("。.!！,，：:")
    if m in {"A", "B", "C"}:
        return m
    import re
    match = re.search(r"方案\s*([ABC])", msg, re.IGNORECASE)
    return match.group(1).upper() if match else None
