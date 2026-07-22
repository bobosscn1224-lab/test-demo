"""Stage: visual collage generation — 3 visual directions (A/B/C) + user choice."""

from __future__ import annotations

import os
import uuid

from app.skills.base import SkillContext, SkillResult
from app.services._paths import PUBLIC_DIR
from app.services.collage_prompt_spec import (
    build_collage_prompt,
    build_regen_prompt,
    strip_visual_suggestions,
    get_visual_direction,
    validate_prompt,
    validate_output,
)
from ..constants import IMAGE_TIMEOUT, CONFIRM_WORDS
from ..prompts import (
    STEP2_PROGRESS,
    COLLAGE_RESULT_TEMPLATE, COLLAGE_CHOICE_PROMPT,
)
from .. import image_gen


def _collage_validation_context(outline: str) -> dict:
    import re as _re
    page_count = len(_re.findall(r'第\s*(\d+)\s*页', outline))
    if page_count < 1:
        page_count = len(_re.findall(r'###\s+第?\d+', outline))
    return {
        "expected_pages": page_count or 8,
        "columns": 3,
        "outline": strip_visual_suggestions(outline),
    }


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

    # Check for single-plan regeneration with modifications
    # e.g. "方案A 重新生成，第3页背景改成深色" or "B重做，字体调大"
    target_label, mod_note = _parse_single_regenerate(msg)
    if target_label is not None and mod_note:
        # Store modification intent in session for streaming handler to pick up
        sessions[session_id] = {
            **session,
            "regenerate_target": target_label,
            "regenerate_modifications": mod_note,
            "stage": "collage_regenerating",
        }
        return SkillResult(
            success=True,
            message=f"收到修改意见，正在重新生成方案 {target_label}...",
            data={"skill": "ppt_maker", "stage": "collage_regenerating"},
        )

    # Parse choice BEFORE checking generic regeneration words
    choice = _parse_choice(msg)

    # Check for simple redo (no specific modifications, just "重新生成")
    if not choice and any(w in msg for w in ["不满意", "都不满意", "重新生成", "重做", "再生成"]):
        sessions[session_id]["stage"] = "collage_confirm"
        return SkillResult(
            success=True,
            message="好的，请告诉我你对大纲的修改意见，我将重新生成三版方案。\n\n也可以指定方案回复，如「方案 A 重新生成，第3页背景改成深色」。",
            data={"skill": "ppt_maker", "stage": "collage_confirm"},
        )

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
    briefing = session.get("briefing")
    all_prompts = _build_prompts(outline, briefing)

    for idx, (label, prompt) in enumerate(all_prompts, 1):
        if label in done_labels:
            continue  # skip already-done
        filename = f"ppt_maker_{session_id[:8]}_{run_id}_{label.lower()}.png"
        out_path = os.path.join(output_dir, filename)
        yield f"进度 4/4：正在生成方案 {label} 的完整 PPT 拼图（{len(done_labels)+1}/3）...\n"

        error = await image_gen.generate(
            prompt, out_path, interaction_name="ppt_collage",
            validation_context=_collage_validation_context(outline),
            timeout=IMAGE_TIMEOUT,
        )
        if error:
            yield SkillResult(success=False, message=f"方案 {label} 生成失败。\n\n{error}")
            return

        # Post-generation validation
        out_warnings = validate_output(out_path)
        if out_warnings:
            logger.warning("v2 collage %s output validation: %s", label, out_warnings)

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
    briefing = session.get("briefing")

    sessions[session_id] = {**session, "stage": "collage_generating"}

    for i, msg in enumerate(STEP2_PROGRESS):
        yield msg + "\n"

    for idx, (label, prompt) in enumerate(_build_prompts(outline, briefing), 1):
        filename = f"ppt_maker_{session_id[:8]}_{run_id}_{label.lower()}.png"
        out_path = os.path.join(output_dir, filename)
        yield f"进度 4/4：正在生成方案 {label} 的完整 PPT 拼图（{idx}/3）...\n"

        error = await image_gen.generate(
            prompt, out_path, interaction_name="ppt_collage",
            validation_context=_collage_validation_context(outline),
            timeout=IMAGE_TIMEOUT,
        )
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


def _build_prompts(outline: str, briefing: dict | None = None) -> list[tuple[str, str]]:
    """Build 3 collage prompts from the outline — uses persistent spec."""
    import re as _re

    # Count pages
    page_count = len(_re.findall(r'第\s*(\d+)\s*页', outline))
    if page_count < 1:
        page_count = len(_re.findall(r'###\s+第?\d+', outline))
    if page_count < 1:
        page_count = 8

    cleaned = strip_visual_suggestions(outline)
    project_context = _build_project_context(briefing)

    return [
        ("A", build_collage_prompt(
            total_pages=page_count, cleaned_outline=cleaned,
            variant_label="A", project_context=project_context,
        )),
        ("B", build_collage_prompt(
            total_pages=page_count, cleaned_outline=cleaned,
            variant_label="B", project_context=project_context,
        )),
        ("C", build_collage_prompt(
            total_pages=page_count, cleaned_outline=cleaned,
            variant_label="C", project_context=project_context,
        )),
    ]


def _build_project_context(briefing: dict | None) -> str:
    """Build project context section for the collage prompt."""
    if not briefing:
        return ""

    parts = []
    purpose = briefing.get("purpose", "").strip()
    audience = briefing.get("audience", "").strip()
    style = briefing.get("style", "").strip()
    key_msg = briefing.get("key_message", "").strip()

    if purpose:
        parts.append(f"**Purpose**: {purpose}")
    if audience:
        parts.append(f"**Audience**: {audience}")
    if style:
        parts.append(f"**Preferred Style**: {style}")
    if key_msg:
        parts.append(f"**Key Message**: {key_msg}")

    if not parts:
        return ""

    return "PROJECT CONTEXT:\n" + "\n".join(parts) + "\n"


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


def _parse_single_regenerate(msg: str) -> tuple[str | None, str]:
    """Parse single-plan regeneration request with modifications.
    Returns (label, modifications_text) or (None, "").
    Examples:
      - "方案A重新生成，第3页背景改成深色" → ("A", "第3页背景改成深色")
      - "B重做，字体调大，配色改成暖色" → ("B", "字体调大，配色改成暖色")
      - "重新生成" → (None, "")
    """
    import re as _re
    targets = [("A", r'方案\s*A'), ("B", r'方案\s*B'), ("C", r'方案\s*C'),
               ("A", r'\bA\b'), ("B", r'\bB\b'), ("C", r'\bC\b')]
    regen_words = r'(?:重新生成|重做|重生成|再生成|重新画|重新做|重画)'

    for label, tpat in targets:
        pat = rf'{tpat}\s*[，,；;]?\s*{regen_words}\s*[，,；;]?\s*(.+)'
        m = _re.search(pat, msg, _re.IGNORECASE)
        if m:
            return label, m.group(1).strip().rstrip("。.!！")
        # Also try reversed order: "重新生成方案A，修改意见"
        pat2 = rf'{regen_words}\s*{tpat}\s*[，,；;]?\s*(.+)'
        m2 = _re.search(pat2, msg, _re.IGNORECASE)
        if m2:
            return label, m2.group(1).strip().rstrip("。.!！")

    return None, ""


async def regenerate_single_stream(session: dict, sessions: dict, session_id: str):
    """Streaming generator: regenerate a single collage plan with modifications."""
    target_label = session.get("regenerate_target", "")
    modifications = session.get("regenerate_modifications", "")
    outline = str(session.get("outline", "")).strip()

    if not target_label or not modifications:
        yield SkillResult(success=False, message="缺少重新生成的目标方案或修改意见。")
        return
    if not outline:
        yield SkillResult(success=False, message="未找到已确认的大纲内容。请重新提供大纲。")
        return

    # Clean up session state
    session.pop("regenerate_target", None)
    session.pop("regenerate_modifications", None)

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    # Build modified prompt for this specific plan
    briefing = session.get("briefing")
    prompt = _build_single_prompt(outline, target_label, modifications, briefing)

    filename = f"ppt_maker_{session_id[:8]}_{run_id}_{target_label.lower()}.png"
    out_path = os.path.join(output_dir, filename)

    yield f"正在根据修改意见重新生成方案 {target_label}：{modifications}\n"

    error = await image_gen.generate(
        prompt, out_path, interaction_name="ppt_collage",
        validation_context=_collage_validation_context(outline),
        timeout=IMAGE_TIMEOUT,
    )
    if error:
        yield SkillResult(success=False, message=f"方案 {target_label} 重新生成失败。\n\n{error}")
        return

    # Replace the old collage with the new one
    existing = session.get("visual_collages", [])
    replaced = False
    for c in existing:
        if c["label"] == target_label:
            # Clean up old file if different
            old_path = c.get("path", "")
            if old_path and old_path != out_path and os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except Exception:
                    pass
            c["filename"] = filename
            c["path"] = out_path
            replaced = True
            break
    if not replaced:
        existing.append({"label": target_label, "filename": filename, "path": out_path})

    sessions[session_id] = {**session, "visual_collages": existing, "stage": "collage_choice"}

    # Show the updated collage with other plans still available
    lines = [f"✅ 方案 {target_label} 已按修改意见重新生成：\n"]
    lines.append(f"![方案 {target_label}](/api/skills/download/{filename})")
    lines.append(f"[下载方案 {target_label}](/api/skills/download/{filename})\n")
    lines.append("---\n")
    lines.append("当前所有方案：")
    for c in existing:
        status = "🆕" if c["label"] == target_label else ""
        lines.append(f"- 方案 {c['label']} {status}")
    lines.append("\n请选择方案 A / B / C 进入下一步，或继续提供修改意见（如「方案 A 重新生成，xxx」）。")

    yield SkillResult(
        success=True,
        message="\n".join(lines),
        data={"skill": "ppt_maker", "stage": "collage_choice"},
    )


def _build_single_prompt(outline: str, label: str, modifications: str, briefing: dict | None = None) -> str:
    """Build a single collage prompt with modifications — uses persistent spec."""
    import re as _re
    page_count = len(_re.findall(r'第\s*(\d+)\s*页', outline))
    if page_count < 1:
        page_count = len(_re.findall(r'###\s+第?\d+', outline))
    if page_count < 1:
        page_count = 8

    cleaned = strip_visual_suggestions(outline)
    project_context = _build_project_context(briefing)

    return build_regen_prompt(
        total_pages=page_count,
        cleaned_outline=cleaned,
        label=label,
        modifications=modifications,
        project_context=project_context,
    )
