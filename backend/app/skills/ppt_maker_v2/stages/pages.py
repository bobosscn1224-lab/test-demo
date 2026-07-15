"""Stage: single-page high-res generation (step 3)."""

import os
import re
import uuid

from app.skills.base import SkillContext, SkillResult
from app.services._paths import PUBLIC_DIR
from ..constants import IMAGE_TIMEOUT, CONFIRM_WORDS
from ..prompts import SINGLE_PAGE_BASE, STEP3_INTRO, PAGE_GENERATED_TEMPLATE, PAGE_ALL_DONE
from .. import image_gen

# ── Visual system descriptions (from original visual_systems.py) ──

_STYLE_TEXT = {
    "A": "premium strategy consulting report, bright background, precise grid, restrained accent colors",
    "B": "advanced technology keynote, deep clean background, luminous data accents, high-end AI atmosphere",
    "C": "refined editorial business deck, sophisticated image use, generous whitespace, elegant information blocks",
    "REF": "user-provided collage master — faithfully replicate the exact visual style from the uploaded reference",
}

_VISUAL_SYSTEMS = {
    "A": "Background: white to light warm grey (#F8F7F4 to #FFFFFF). Font: Inter/Source Han Sans, titles 28-32px bold dark charcoal, body 10-12px. Colors: primary indigo (#3B5998), secondary warm grey, accent coral (#E8734A). Charts: flat design, thin grey gridlines, rounded bars. Cards: 1px border, 6px radius, 16px padding. Margins: 60/50/70px. Density: medium — 1 focal point + 3-5 content blocks per slide.",
    "B": "Background: deep dark (#0D1117 to #161B22), 3-5% grid dot pattern. Font: SF Pro Display/DIN, titles 30-38px bold white or electric blue (#58A6FF). Colors: dark bg, electric blue, cyan (#39D2C0), amber (#F0883E). Charts: dark surfaces + luminous data elements. Icons: thin glowing line icons. Cards: semi-transparent panels, 8-15% white overlay, 10px radius. Density: medium-high — 4-6 blocks per slide.",
    "C": "Background: warm off-white (#FAF9F6), 2% paper texture. Font: serif titles (Source Han Serif), sans-serif body; titles 24-28px dark brown. Colors: warm neutrals, dark brown (#2C2416), warm taupe (#8B7D6B), accent burgundy (#8B3A3A) or olive (#4A6741). Charts: refined minimal, hairline strokes. Margins: 72-80/60/80px — generous whitespace. Density: low-medium — max 3 content blocks per slide.",
    "REF": "Faithfully replicate the exact visual style, layout, color palette, font hierarchy, background treatment, chart styling, iconography, card design, spacing, margins, and page density from the user-provided reference collage. Do not introduce any new visual elements not present in the reference.",
}


async def handle_pages_confirm(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """User confirmed step 3 — start generating single pages."""
    msg = context.user_message.strip()
    if not _is_confirm(msg):
        choice = session.get("selected_visual", "?")
        return SkillResult(
            success=True,
            message=f"已选择方案 {choice}。请回复「开始」逐页生成高清视觉稿。",
            data={"skill": "ppt_maker", "stage": "pages_confirm"},
        )
    return await _start_generation(session, sessions, session_id)


async def handle_collage_upload(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Entry 3: user uploads collage + provides page info."""
    source = await _collect_text(context)

    # Need both: uploaded file + page info
    has_file = bool(context.uploaded_files)
    if not has_file:
        return SkillResult(
            success=True,
            message="请上传 PPT 整体详细缩略图（PNG/JPG）。",
            data={"skill": "ppt_maker", "stage": "collage_upload"},
        )
    if not source or len(source) < 20:
        return SkillResult(
            success=True,
            message="请同时告诉我总页数和每页标题。\n\n格式示例：\n共 5 页\n第 1 页：封面\n第 2 页：项目背景\n...",
            data={"skill": "ppt_maker", "stage": "collage_upload"},
        )

    # Build outline from page info
    outline = _parse_page_info(source)
    sessions[session_id] = {
        "stage": "pages_confirm", "entry": "3",
        "outline": outline, "selected_visual": "REF",
        "visual_collages": [{"label": "REF", "filename": os.path.basename(context.uploaded_files[0].get("path", "")), "path": context.uploaded_files[0].get("path", "")}],
    }
    return SkillResult(
        success=True,
        message=f"已解析 {outline.count('第')} 页。请回复「开始」逐页生成高清图。",
        data={"skill": "ppt_maker", "stage": "pages_confirm"},
    )


async def handle_pptx_direct(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Entry 4: direct single-page image → PPTX."""
    if not context.uploaded_files:
        return SkillResult(
            success=True,
            message="请上传一张高清 PPT 风格图（PNG/JPG），我将直接生成可编辑 PPTX。",
            data={"skill": "ppt_maker", "stage": "pptx_direct"},
        )

    # Store the image and go straight to PPTX generation
    img_path = context.uploaded_files[0].get("path", "")
    sessions[session_id]["single_pages"] = [{"index": 1, "title": "第1页", "path": img_path, "filename": os.path.basename(img_path)}]
    sessions[session_id]["stage"] = "pptx_scope"

    return SkillResult(
        success=True,
        message="已收到图片。请回复「全部」生成整套 PPTX，或指定页码范围如「1-3」。",
        data={"skill": "ppt_maker", "stage": "pptx_scope"},
    )


# ── Page generation stream ────────────────────────────────────────

async def resume_stream(session: dict, sessions: dict, session_id: str):
    """Resume page generation after interruption — skip already-done pages."""
    outline = str(session.get("outline", "")).strip()
    choice = session.get("selected_visual", "A")
    existing = session.get("single_pages", [])
    done_indices = {p["index"] for p in existing}

    slides = _extract_slides(outline)
    if not slides:
        yield SkillResult(success=False, message="无法从大纲中解析页码。")
        return

    remaining = [s for s in slides if s["index"] not in done_indices]
    if not remaining:
        sessions[session_id]["stage"] = "pptx_scope"
        yield SkillResult(
            success=True,
            message=PAGE_ALL_DONE.format(total=len(slides)),
            data={"skill": "ppt_maker", "stage": "pptx_scope"},
        )
        return

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    total = len(slides)

    style_text = _STYLE_TEXT.get(choice, _STYLE_TEXT["A"])
    visual_system = _VISUAL_SYSTEMS.get(choice, _VISUAL_SYSTEMS["A"])
    collage_filename = ""
    for c in session.get("visual_collages", []):
        if c.get("label") == choice:
            collage_filename = c.get("filename", "")
            break

    sessions[session_id] = {**session, "stage": "pages_generating"}

    for slide in remaining:
        idx = slide["index"]
        filename = f"ppt_maker_{session_id[:8]}_{run_id}_page_{idx:02d}.png"
        out_path = os.path.join(output_dir, filename)
        layout_type = _detect_layout(slide.get("content", ""))

        prompt = SINGLE_PAGE_BASE.format(
            page_num=idx, total_pages=total,
            choice_label=choice, collage_filename=collage_filename,
            style_text=style_text, layout_type=layout_type,
            slide_content=slide.get("content", "")[:2000],
        )

        yield f"正在生成第 {idx}/{total} 页单页 PPT 视觉稿...\n"
        error = await image_gen.generate(prompt, out_path, timeout=IMAGE_TIMEOUT)
        if error:
            yield SkillResult(success=False, message=f"第 {idx} 页生成失败：{error}")
            return

        existing.append({"index": idx, "title": slide.get("title", ""), "filename": filename, "path": out_path})
        existing.sort(key=lambda p: p["index"])
        sessions[session_id]["single_pages"] = existing

        yield SkillResult(
            success=True,
            message=PAGE_GENERATED_TEMPLATE.format(idx=idx, total=total, title=slide.get("title", f"第{idx}页"), filename=filename),
            data={"skill": "ppt_maker"},
        )

    sessions[session_id]["stage"] = "pptx_scope"
    yield SkillResult(
        success=True,
        message=PAGE_ALL_DONE.format(total=total),
        data={"skill": "ppt_maker", "stage": "pptx_scope"},
    )


async def generate_stream(session: dict, sessions: dict, session_id: str):
    """Async generator: run step 3 single-page generation."""
    outline = str(session.get("outline", "")).strip()
    choice = session.get("selected_visual", "A")
    if not outline:
        yield SkillResult(success=False, message="未找到已确认的大纲。请重新生成大纲。")
        return

    slides = _extract_slides(outline)
    if not slides:
        yield SkillResult(success=False, message="无法从大纲中解析页码。请确保每页有「第X页：标题」格式。")
        return

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    total = len(slides)

    sessions[session_id] = {**session, "stage": "pages_generating"}
    page_images = []

    yield STEP3_INTRO

    style_text = _STYLE_TEXT.get(choice, _STYLE_TEXT["A"])
    visual_system = _VISUAL_SYSTEMS.get(choice, _VISUAL_SYSTEMS["A"])
    collage_filename = ""
    for c in session.get("visual_collages", []):
        if c.get("label") == choice:
            collage_filename = c.get("filename", "")
            break

    for slide in slides:
        idx = slide["index"]
        filename = f"ppt_maker_{session_id[:8]}_{run_id}_page_{idx:02d}.png"
        out_path = os.path.join(output_dir, filename)

        layout_type = _detect_layout(slide.get("content", ""))
        prompt = SINGLE_PAGE_BASE.format(
            page_num=idx, total_pages=total,
            choice_label=choice, collage_filename=collage_filename,
            style_text=style_text, layout_type=layout_type,
            slide_content=slide.get("content", "")[:2000],
        )

        yield f"正在生成第 {idx}/{total} 页单页 PPT 视觉稿...\n"
        error = await image_gen.generate(prompt, out_path, timeout=IMAGE_TIMEOUT)
        if error:
            yield SkillResult(success=False, message=f"第 {idx} 页生成失败：{error}")
            return

        page_images.append({
            "index": idx, "title": slide.get("title", ""),
            "filename": filename, "path": out_path,
        })
        sessions[session_id]["single_pages"] = page_images

        yield SkillResult(
            success=True,
            message=PAGE_GENERATED_TEMPLATE.format(idx=idx, total=total, title=slide.get("title", f"第{idx}页"), filename=filename),
            data={"skill": "ppt_maker"},
        )

    sessions[session_id]["stage"] = "pptx_scope"
    yield SkillResult(
        success=True,
        message=PAGE_ALL_DONE.format(total=total),
        data={"skill": "ppt_maker", "stage": "pptx_scope"},
    )


# ── Helpers ───────────────────────────────────────────────────────

def _extract_slides(outline: str) -> list[dict]:
    """Parse slide sections from outline text."""
    matches = list(re.finditer(r"(第\s*\d+\s*页[:：]?.*?)(?=第\s*\d+\s*页[:：]?|\Z)", outline, re.S))
    slides = []
    for i, m in enumerate(matches, 1):
        text = m.group(1).strip()
        title = text.split("\n")[0].strip() if "\n" in text else text[:80]
        title = re.sub(r"^第\s*\d+\s*页[:：]?\s*", "", title)
        slides.append({"index": i, "title": title, "content": text[:3000]})

    if not slides:
        chunks = [c.strip() for c in outline.split("\n\n") if c.strip()][:20]
        for i, c in enumerate(chunks, 1):
            title = c.split("\n")[0][:80] if "\n" in c else c[:80]
            slides.append({"index": i, "title": title, "content": c[:3000]})
    return slides


def _detect_layout(content: str) -> str:
    """Detect page layout type from content keywords."""
    c = content.lower()
    if any(w in c for w in ["封面", "title", "标题页", "cover"]): return "COVER — centered title + subtitle, org/date at bottom"
    if any(w in c for w in ["目录", "agenda", "contents"]): return "AGENDA/TOC — numbered list layout"
    if any(w in c for w in ["图表", "chart", "数据", "趋势", "对比", "占比", "%"]): return "DATA/CHART — chart-focused with 2-3 insight callouts"
    if any(w in c for w in ["对比", "比较", "vs", "方案", "优劣"]): return "COMPARISON — multi-column comparison layout"
    if any(w in c for w in ["流程", "步骤", "阶段", "process", "step", "timeline"]): return "PROCESS/TIMELINE — horizontal or vertical flow"
    if any(w in c for w in ["总结", "下一步", "感谢", "summary", "conclusion"]): return "SUMMARY/CLOSING — key takeaways or call-to-action"
    if any(w in c for w in ["概述", "背景", "目标", "现状"]): return "OVERVIEW — title + 2-4 text blocks"
    return "CONTENT — standard business slide"


def _parse_page_info(text: str) -> str:
    """Build a minimal outline from user-provided page list."""
    lines = text.strip().split("\n")
    outline_parts = []
    for line in lines:
        line = line.strip()
        if re.match(r"第?\s*\d+\s*页?", line) or re.match(r"\d+[\.\、\s]", line):
            outline_parts.append(line)
    if not outline_parts:
        return f"PPT 内容：\n{text[:3000]}"
    return "PPT 大纲：\n" + "\n".join(outline_parts)


async def _start_generation(session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Mark ready for generation — caller uses generate_stream for actual work."""
    sessions[session_id]["stage"] = "pages_generating"
    return SkillResult(
        success=True,
        message="开始逐页生成高清视觉稿...",
        data={"skill": "ppt_maker", "stage": "pages_generating"},
    )


async def _collect_text(context: SkillContext) -> str:
    """Collect text from message and files."""
    parts = [context.user_message.strip()]
    for f in (context.uploaded_files or []):
        try:
            from app.utils.file_parser import parse_file_sync
            text = await parse_file_sync(f.get("path", ""))
            if text:
                parts.append(text[:30000])
        except Exception:
            pass
    return "\n\n".join(p for p in parts if p)


def _is_confirm(msg: str) -> bool:
    m = msg.strip().lower()
    if len(m) > 15:
        return False
    return any(w in m for w in CONFIRM_WORDS)
