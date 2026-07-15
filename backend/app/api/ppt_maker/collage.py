"""PPT Maker Feature API — Collage generation endpoint (3 visual variants)."""

from __future__ import annotations

import logging
import os
import re
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services._paths import PUBLIC_DIR
from app.skills.ppt_maker_v2 import image_gen
from app.skills.ppt_maker_v2.constants import IMAGE_TIMEOUT
from app.api.ppt_maker.projects import _load, _save, _now
from app.api.ppt_maker.models import (
    CollageGenerateResponse, CollageItem, CollageSelectRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-maker"], redirect_slashes=False)


# ── Label maps (mirrored from models.py) ──────────────────────────────

_PURPOSE_LABEL: dict[str, str] = {
    "business_report": "业务汇报", "project_proposal": "项目方案",
    "product_launch": "产品宣讲", "training": "培训辅导",
    "review": "复盘总结", "story_pitch": "故事路演", "other": "其他",
}
_AUDIENCE_LABEL: dict[str, str] = {
    "executives": "老板/管理层", "clients": "客户/合作方",
    "team": "一线团队", "investors": "投资人", "mixed": "混合受众",
}
_SCALE_RANGE: dict[str, str] = {
    "compact_8_12": "8-12页", "standard_15_20": "15-20页", "full_25_35": "25-35页",
}
_STYLE_LABEL: dict[str, str] = {
    "professional": "专业严谨", "tech": "科技感", "minimal": "简约商务",
    "creative": "创意活泼", "bold": "高端大气",
}

# Detailed visual system descriptions per style — used to customize A/B/C directions
_STYLE_VISUAL: dict[str, str] = {
    "professional": (
        "专业严谨风格：白色/浅灰背景，精确网格对齐，克制的强调色（深蓝#1a365d、藏青#2c5282），"
        "扁平化图表，细灰线网格，圆角条形图。字体使用思源黑体，标题28-32px加粗深炭色，正文10-12px。"
        "边距60/50/70px。整体密度中等，传递权威、可信、专业的咨询报告质感。"
    ),
    "tech": (
        "科技感风格：深色背景（#0D1117至#161B22），3-5%网格点阵图案。"
        "字体使用SF Pro Display/DIN，标题30-38px加粗白色或电光蓝（#58A6FF）。"
        "色彩：深色底+电光蓝+青绿（#39D2C0）+琥珀色（#F0883E）数据强调。"
        "图表使用深色表面+发光数据元素。卡片使用半透明面板，8-15%白色叠加，10px圆角。"
        "整体密度中高，传递前沿、智能、高科技的未来感。"
    ),
    "minimal": (
        "简约商务风格：温暖米白背景（#FAF9F6），2%纸张纹理。"
        "字体标题使用思源宋体，正文使用思源黑体；标题24-28px深棕色。"
        "色彩：暖中性色，深棕（#2C2416），暖灰褐（#8B7D6B），强调色酒红（#8B3A3A）。"
        "图表精致极简，发丝级细线。边距72-80/60/80px，大量留白。"
        "整体密度低-中，传递精致、优雅、高级的编辑级商务质感。"
    ),
    "creative": (
        "创意活泼风格：明亮活泼的色彩搭配，可以使用渐变色背景。"
        "字体大胆有表现力，标题24-30px，可以使用圆体或手写风格。"
        "色彩：高饱和度的强调色（珊瑚橙、柠檬黄、薄荷绿），白色或浅灰底。"
        "图表灵活多变，可以使用插画风格图标、不规则形状。卡片可以有彩色边框或阴影。"
        "整体密度中等，传递创新、活力、年轻、与众不同的品牌个性。"
    ),
    "bold": (
        "高端大气风格：深色或纯黑背景为主，金色/玫瑰金强调色。"
        "字体大而有力，标题32-40px，可以使用衬线体增加奢华感。"
        "色彩：黑底+金色（#C9A96E）+白色文字+暗红强调。"
        "图表简洁有力，大面积色块，粗线条。留白慷慨但不失气势。"
        "整体密度低-中，传递高端、奢侈、权威、大气的品牌气场。"
    ),
}


def _extract_page_titles(outline: str) -> list[str]:
    """Extract just the page titles from outline text for compact collage prompts."""
    import re
    titles = []
    for m in re.finditer(r'第\s*(\d+)\s*页[：:]\s*(.*?)(?:\n|$)', outline):
        title = m.group(2).strip()
        if title:
            titles.append(title[:60])
    if not titles:
        # Fallback: try ### markers
        for m in re.finditer(r'###\s*第\s*(\d+)\s*页\s*\n\*\*标题\*\*[：:]\s*(.*?)(?:\n|$)', outline):
            titles.append(m.group(2).strip()[:60])
    return titles


def _narrative_label(v: str) -> str:
    return {"narrative":"📖 叙事故事型","data_report":"📊 数据汇报型","business_proposal":"💼 商业方案型","technical":"🔧 技术拆解型","auto":"🤖 自动"}.get(v, v or "自动")

def _framework_label(v: str) -> str:
    return {"conflict_driven":"⚡ 冲突驱动型","scr":"📋 SCR型","problem_driven":"🔍 问题驱动型","opportunity_driven":"🚀 机会驱动型","abt":"🎬 ABT型","hook_progressive":"🪝 钩子递进型","auto":"🤖 自动"}.get(v, v or "自动")

def _objective_label(v: str) -> str:
    return {"drive_decision":"✅ 促成决策/批准","show_results":"📊 展示成果/复盘","secure_resources":"💰 争取资源/预算","build_consensus":"🤝 建立共识/对齐","transfer_knowledge":"📖 传递认知/培训","auto":"🤖 自动"}.get(v, v or "自动")

def _tone_label(v: str) -> str:
    return {"professional":"👔 专业严谨","storytelling":"📖 生动故事化","inspirational":"🔥 激励人心","concise":"⚡ 简洁有力","humorous":"😄 幽默风趣","auto":"🤖 自动"}.get(v, v or "自动")

def _clean_for_image(text: str) -> str:
    """Strip AI markers that would pollute image generation prompts."""
    return re.sub(r'\s*\[(AI增强|参考补充)\]\s*', ' ', text)


def _download_url(filename: str) -> str:
    """Build a download URL for an image file in PUBLIC_DIR (relative path)."""
    return f"/api/skills/download/{filename}"


def _build_briefing_context(project: dict) -> str:
    """Build a structured briefing section from all persisted project data.

    This is the key fix: the collage prompt MUST include everything the user
    confirmed in steps 1-3 — not just the outline text.
    """
    parts: list[str] = []

    # Scene / purpose
    purpose_key = project.get("purpose", "")
    purpose_label = _PURPOSE_LABEL.get(purpose_key, purpose_key) if purpose_key else "未指定"
    parts.append(f"**应用场景**：{purpose_label}")

    # Audience
    audience_key = project.get("audience", "")
    audience_label = _AUDIENCE_LABEL.get(audience_key, audience_key) if audience_key else "未指定"
    parts.append(f"**目标受众**：{audience_label}")

    # Page count constraint (from scale — HARD constraint)
    scale_key = project.get("scale", "")
    scale_range = _SCALE_RANGE.get(scale_key, "15-20页") if scale_key else "15-20页"
    parts.append(f"**页数要求**：必须恰好生成 {scale_range} 的幻灯片缩略图，不得多也不得少")

    # Key message / theme
    key_msg = project.get("key_message", "").strip()
    if key_msg:
        parts.append(f"**核心主题**：{key_msg[:200]}")

    # Visual styles (画风) — what the user selected
    styles = project.get("styles", [])
    if styles:
        style_labels = [_STYLE_LABEL.get(s, s) for s in styles]
        parts.append(f"**选定视觉风格**：{' + '.join(style_labels)}")
        # Add detailed visual guidance for each selected style
        for s in styles:
            if s in _STYLE_VISUAL:
                parts.append(f"  - {_STYLE_VISUAL[s]}")

    # User's raw content text
    content_text = project.get("content_text", "").strip()
    if content_text:
        parts.append(f"**用户素材摘要**：{_clean_for_image(content_text)[:500]}")

    return "\n".join(parts)


def _build_collage_prompts(project: dict) -> list[tuple[str, str]]:
    """Build 3 collage prompts (A/B/C) following the exact specification.

    Each prompt includes: task objective, output requirements, content
    requirements, visual requirements, project context, confirmed outline,
    and variant-specific visual direction.
    """
    outline = _clean_for_image(project.get("outline", "").strip())

    # ── Project context ──────────────────────────────────────────────
    purpose_key = project.get("purpose", "")
    purpose_label = _PURPOSE_LABEL.get(purpose_key, purpose_key)
    audience_key = project.get("audience", "")
    audience_label = _AUDIENCE_LABEL.get(audience_key, audience_key)
    scale_key = project.get("scale", "")
    scale_range = _SCALE_RANGE.get(scale_key, "15-20页") if scale_key else "15-20页"
    key_msg = project.get("key_message", "").strip()
    content_text = project.get("content_text", "").strip()
    styles = project.get("styles", [])

    # Collect user-selected style labels
    style_labels = [_STYLE_LABEL.get(s, s) for s in styles] if styles else ["专业严谨"]
    style_label_str = "、".join(style_labels)

    # ── Extract page titles from outline for compact collage prompt ──
    page_titles = _extract_page_titles(outline)

    # ── Count actual pages from outline ──
    total_pages = len(page_titles)

    # ── Build the spec template — full detail + hard page/content constraints ──
    def _build_spec(variant_label: str, visual_direction: str) -> str:
        title_list = "\n".join(f"  {i}. {t}" for i, t in enumerate(page_titles, 1))
        return (
            f"生成一张方案{variant_label}的完整PPT拼图。\n\n"

            f"━━━ 强制约束（不可违反）━━━\n"
            f"1. 拼图必须恰好包含{total_pages}个缩略图——不能多也不能少。当前大纲共{total_pages}页。\n"
            f"2. 每个缩略图的内容必须严格对应下面大纲中该页的标题和要点，不得编造、不得替换。\n"
            f"3. 页序必须正确：第1页在左上角，从左到右、从上到下排列。\n\n"

            f"━━━ 排版约束 ━━━\n"
            f"1. 每行固定3个16:9横版缩略图。共{total_pages}个缩略图，{((total_pages + 2) // 3)}行。\n"
            f"2. 最后一行的缩略图尺寸与前几行完全一致，不满时右侧留空——不得拉伸、裁切或缩小。\n"
            f"3. 所有缩略图尺寸统一、网格对齐。行间距和列间距均为10-15px。\n\n"

            f"━━━ 视觉方向 ━━━\n"
            f"{visual_direction}\n\n"

            f"━━━ 项目信息 ━━━\n"
            f"应用场景：{purpose_label}\n"
            f"目标受众：{audience_label}\n"
            f"视觉风格：{style_label_str}\n"
            f"核心主题：{key_msg[:500] if key_msg else '（未指定）'}\n"
            f"叙事风格：{_narrative_label(project.get('narrative_style',''))}\n"
            f"叙事框架：{_framework_label(project.get('narrative_framework',''))}\n"
            f"汇报目标：{_objective_label(project.get('objective',''))}\n"
            f"语调风格：{_tone_label(project.get('tone',''))}\n"
            f"用户素材：{_clean_for_image(content_text)[:500] if content_text else '（未提供文字素材）'}\n\n"

            f"━━━ 已确认大纲（每个缩略图必须严格对应此内容）━━━\n"
            f"{outline}\n\n"

            f"输出：方案{variant_label}完整PPT拼图（一张图，{total_pages}个16:9缩略图，{((total_pages + 2) // 3)}行×3列网格）"
        )

    # ── Build 3 visual directions from user's styles ──────────────────
    directions = _build_visual_directions(styles)

    prompts: list[tuple[str, str]] = []
    for label in ("A", "B", "C"):
        prompt = _build_spec(label, directions[label])
        prompts.append((label, prompt))

    return prompts



def _build_visual_directions(styles: list[str]) -> dict[str, str]:
    """Build 3 distinct visual directions (A/B/C) from user's selected styles.

    Each direction is a detailed visual brief covering: layout temperament,
    information density, chart language, image usage, background treatment,
    visual focus, and title typography. The 3 directions must be clearly
    differentiated, not just color swaps.
    """
    selected = styles if styles else ["professional"]

    # Select 3 distinct flavors from user's styles (with fallbacks)
    primary = selected[0]
    secondary = selected[1] if len(selected) > 1 else ("tech" if primary != "tech" else "minimal")
    tertiary = selected[2] if len(selected) > 2 else (
        "bold" if "bold" not in [primary, secondary]
        else "creative" if "creative" not in [primary, secondary]
        else "minimal"
    )

    primary_label = _STYLE_LABEL.get(primary, primary)
    secondary_label = _STYLE_LABEL.get(secondary, secondary)
    tertiary_label = _STYLE_LABEL.get(tertiary, tertiary)

    primary_spec = _STYLE_VISUAL.get(primary, "")
    secondary_spec = _STYLE_VISUAL.get(secondary, "")
    tertiary_spec = _STYLE_VISUAL.get(tertiary, "")

    # ── Direction A: primary style, restrained, trust-building ─────
    dir_a = (
        f"{primary_label} · 克制权威型\n\n"
        f"版式气质：严谨、可信、有分量的{primary_label}调性，传递专业判断力。\n"
        f"信息密度：中高——数据驱动，关键数字突出，但留白充足，不拥挤。\n"
        f"图表语言：扁平化、精确网格对齐、细灰线辅助线、圆角条形/柱状图。\n"
        f"图片使用：克制——仅在封面和关键过渡页使用高质量真实感摄影。\n"
        f"背景处理：浅色系为主（白/米白/浅灰），干净、明亮、无纹理。\n"
        f"视觉重心：每页一个明确的视觉焦点——或是大数字、或是核心图表、或是结论式标题。\n"
        f"标题排版：观点式标题，28-32px加粗深色字体，正文10-12px。\n\n"
        f"具体规范：{primary_spec}\n\n"
        f"这是最贴近「{primary_label}」的设计方案，适合需要建立信任和权威感的正式场合。"
    )

    # ── Direction B: blended style, modern, forward-looking ─────────
    dir_b = (
        f"{primary_label}×{secondary_label} · 前瞻创新型\n\n"
        f"版式气质：以{primary_label}为骨架，融入{secondary_label}的视觉张力，"
        f"在专业感中注入现代感和前瞻性。\n"
        f"信息密度：中等——每页聚焦一个核心洞察，辅以2-3个支撑点，节奏明快。\n"
        f"图表语言：数据可视化更灵动——发光数据点、渐变面积图、半透明叠加层。\n"
        f"图片使用：适度——在关键页面使用高对比度、有情绪感染力的商业摄影或抽象科技插画。\n"
        f"背景处理：浅色与深色区域交替使用，形成视觉节奏变化，但整体色调统一。\n"
        f"视觉重心：通过色彩对比和尺寸差异制造视觉层次，引导视线从标题→数据→结论。\n"
        f"标题排版：标题可稍大（30-36px），使用更现代的字体权重组合。\n\n"
        f"具体规范：{secondary_spec}\n\n"
        f"这是一个在保持专业可信的同时融入{secondary_label}元素的创新方案。"
    )

    # ── Direction C: tertiary accent, distinctive, memorable ────────
    dir_c = (
        f"{primary_label}·{tertiary_label} · 品质差异型\n\n"
        f"版式气质：以{primary_label}的能力为底盘，{tertiary_label}的特质做差异化点缀，"
        f"打造一套有辨识度、有记忆点的方案。\n"
        f"信息密度：中低——大量留白，每页内容精简到极致，让每一处设计都有呼吸感。\n"
        f"图表语言：极简化——只用最必要的数据标记，大面积色块替代繁复图表，强调「少即是多」。\n"
        f"图片使用：精选——全页出血大图或大面积色彩区域，图片本身成为页面结构的一部分。\n"
        f"背景处理：大胆——可使用深色全幅背景、渐变过渡、或大面积品牌色块。\n"
        f"视觉重心：强烈的图文对比——大字标题+精致小字正文的张力组合。\n"
        f"标题排版：大而有力，32-40px，可探索衬线字体或更具个性的排版方式。\n\n"
        f"具体规范：{tertiary_spec}\n\n"
        f"这是一个在「{primary_label}」基础上最大胆的创意演绎，适合需要留下深刻印象的场合。"
    )

    return {"A": dir_a, "B": dir_b, "C": dir_c}


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/image-backends")
async def list_image_backends() -> list[dict]:
    """List ALL available image generation backends (checks API key config)."""
    from app.config import settings as _s
    all_backends = [
        ("tutujin",     _s.tutujin_api_key,     "Tutujin",      "gpt-image-2",       "api.tutujin.com chat/completions"),
        ("tutujin_vip", _s.tutujin_api_key,     "Tutujin VIP",  "gpt-image-2-vip",    "api.tutujin.com chat/completions"),
        ("api0029",     _s.api0029_key,         "0029 API",     "gpt-image-2",        "api.0029.org"),
        ("lovart",      _s.lovart_api_key,      "Lovart",       "gpt-image-2:stable", "CatRouter"),
        ("shiyun",      _s.shiyun_api_key,      "诗云API",      "gpt-image-2",        "shiyunapi.com"),
        ("agnes",       _s.agnes_api_key,       "Agnes",        "agnes-2.0-flash",    "Agnes AI Hub"),
        ("openai",      _s.openai_api_key,      "OpenAI",       "dall-e-3/gpt-image-2", "api.openai.com"),
        ("ruizhi",      _s.ruizhi_api_key,      "锐智",         "ruizhi-imagegen",    "锐智本地/云端"),
    ]
    return [
        {"key": k, "label": l, "model": m, "desc": d}
        for k, available, l, m, d in all_backends if available
    ]


@router.get("/projects/{project_id}/collages/preview")
async def preview_collage_prompts(project_id: str) -> dict:
    """Preview the 3 collage generation prompts WITHOUT generating images.

    Returns the exact prompts that would be sent to the image generation model,
    along with the project data used to build them. Useful for debugging.
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲。")

    prompts = _build_collage_prompts(project)

    return {
        "success": True,
        "project_id": project_id,
        "project_context": {
            "purpose": project.get("purpose", ""),
            "audience": project.get("audience", ""),
            "scale": project.get("scale", ""),
            "styles": project.get("styles", []),
            "key_message": project.get("key_message", ""),
            "content_text_length": len(project.get("content_text", "")),
            "content_files_count": len(project.get("content_files", [])),
            "outline_length": len(outline),
        },
        "prompts": [
            {"label": label, "prompt": prompt, "char_count": len(prompt)}
            for label, prompt in prompts
        ],
    }


@router.post("/projects/{project_id}/collages", response_model=CollageGenerateResponse)
async def generate_collages(project_id: str) -> CollageGenerateResponse:
    """Generate 3 visual collage variants (A/B/C) based on ALL persisted project data.

    Uses: purpose, audience, scale, styles, key_message, content_text, AND outline.
    Each variant applies a different visual direction customized to the user's
    selected visual styles.

    This is a long-running operation (up to ~21 minutes total for 3 variants).
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲后再生成拼图。")

    # Validate required project data
    styles = project.get("styles", [])
    if not styles:
        logger.warning("Project %s has no styles configured — using default 'professional'", project_id)

    # Ensure public output directory exists
    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)

    run_id = uuid.uuid4().hex[:10]
    collages: list[dict] = []
    collages_response: list[CollageItem] = []

    prompts = _build_collage_prompts(project)

    for label, prompt in prompts:
        filename = f"ppt_maker_{project_id[:8]}_{run_id}_{label.lower()}.png"
        out_path = os.path.join(output_dir, filename)

        logger.info(
            "Generating collage %s for project %s (styles=%s, scale=%s, purpose=%s)",
            label, project_id, project.get("styles"), project.get("scale"), project.get("purpose"),
        )

        error = await image_gen.generate(prompt, out_path, timeout=IMAGE_TIMEOUT, backend=project.get("image_backend", ""))
        if error:
            logger.error("Collage %s generation failed for project %s: %s", label, project_id, error)
            # Save whatever we have so far before raising error
            if collages:
                project["collages"] = collages
                project["updated_at"] = _now()
                _save(project_id, project)
                logger.info("Saved %d partial collages before failure", len(collages))
            raise HTTPException(
                status_code=500,
                detail=f"方案 {label} 拼图生成失败（已保存前 {len(collages)} 张）：{error}",
            )

        collages.append({
            "label": label, "filename": filename, "path": out_path,
            "prompt": prompt,  # persisted for future reference / regeneration
        })
        collages_response.append(CollageItem(
            label=label,
            filename=filename,
            download_url=_download_url(filename),
        ))

        # Incremental save after each successful collage
        project["collages"] = collages
        project["updated_at"] = _now()
        _save(project_id, project)
        logger.info("Saved collage %s (%d/3) for project %s", label, len(collages), project_id)

    # Final save with status update
    project["collages"] = collages
    project["status"] = "collages_generated"
    project["updated_at"] = _now()
    _save(project_id, project)

    logger.info("All 3 collages generated for project %s", project_id)

    return CollageGenerateResponse(
        success=True,
        project_id=project_id,
        collages=collages_response,
        message="三版拼图已生成，请选择方案 A / B / C。",
    )


@router.put("/projects/{project_id}/collages/select", response_model=CollageGenerateResponse)
async def select_collage(project_id: str, data: CollageSelectRequest) -> CollageGenerateResponse:
    """Select which collage variant (A/B/C) to use as the design master."""
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    selected = data.selected_collage.upper().strip()

    # Verify the selected collage exists in the project
    existing_labels = {c.get("label", "") for c in project.get("collages", [])}
    if selected not in existing_labels:
        raise HTTPException(
            status_code=400,
            detail=f"方案 {selected} 不在已生成的拼图中。可用方案：{sorted(existing_labels)}",
        )

    project["selected_collage"] = selected
    project["updated_at"] = _now()
    _save(project_id, project)

    logger.info("Selected collage %s for project %s", selected, project_id)

    # Build response with existing collage data
    collages_response: list[CollageItem] = []
    for c in project.get("collages", []):
        collages_response.append(CollageItem(
            label=c.get("label", ""),
            filename=c.get("filename", ""),
            download_url=_download_url(c.get("filename", "")),
        ))

    return CollageGenerateResponse(
        success=True,
        project_id=project_id,
        collages=collages_response,
        message=f"已选择方案 {selected}，可以进入逐页生成阶段。",
    )


class SingleCollageRequest(BaseModel):
    feedback: str = ""


@router.post("/projects/{project_id}/collages/{label}", response_model=CollageGenerateResponse)
async def generate_single_collage(project_id: str, label: str) -> CollageGenerateResponse:
    """Generate (or regenerate) a SINGLE collage variant (A, B, or C)."""
    label = label.upper().strip()
    if label not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail=f"方案标签必须是 A/B/C，收到：{label}")

    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲后再生成拼图。")

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    prompts = _build_collage_prompts(project)
    label_prompt = next((p for l, p in prompts if l == label), None)
    if not label_prompt:
        raise HTTPException(status_code=400, detail=f"无法构建方案 {label} 的提示词")

    filename = f"ppt_maker_{project_id[:8]}_{run_id}_{label.lower()}.png"
    out_path = os.path.join(output_dir, filename)

    collages_backend = project.get("image_backend", "") or ""

    logger.info("Generating single collage %s for project %s (backend=%s)", label, project_id, collages_backend or "auto")

    error = await image_gen.generate(label_prompt, out_path, timeout=IMAGE_TIMEOUT, backend=collages_backend)
    if error:
        logger.error("Single collage %s failed for project %s: %s", label, project_id, error)
        raise HTTPException(status_code=500, detail=f"方案 {label} 生成失败：{error}")

    # Merge with existing collages
    existing = {c.get("label", ""): c for c in project.get("collages", [])}
    existing[label] = {"label": label, "filename": filename, "path": out_path, "prompt": label_prompt}
    project["collages"] = sorted(existing.values(), key=lambda c: c["label"])
    project["updated_at"] = _now()
    _save(project_id, project)

    collages_response = [
        CollageItem(label=c["label"], filename=c["filename"], download_url=_download_url(c["filename"]))
        for c in project["collages"]
    ]
    return CollageGenerateResponse(
        success=True, project_id=project_id, collages=collages_response,
        message=f"方案 {label} 已生成。",
    )


@router.put("/projects/{project_id}/collages/{label}", response_model=CollageGenerateResponse)
async def regenerate_single_collage(
    project_id: str, label: str, data: SingleCollageRequest = SingleCollageRequest()
) -> CollageGenerateResponse:
    """Regenerate a single collage with user feedback."""
    label = label.upper().strip()
    if label not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail=f"方案标签必须是 A/B/C，收到：{label}")

    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = project.get("outline", "").strip()
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲后再生成拼图。")

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    prompts = _build_collage_prompts(project)
    label_prompt = next((p for l, p in prompts if l == label), None)
    if not label_prompt:
        raise HTTPException(status_code=400, detail=f"无法构建方案 {label} 的提示词")

    # Append feedback to prompt
    if data.feedback.strip():
        label_prompt += f"\n\n用户修改意见：{data.feedback.strip()[:500]}"

    filename = f"ppt_maker_{project_id[:8]}_{run_id}_{label.lower()}.png"
    out_path = os.path.join(output_dir, filename)

    collages_backend = project.get("image_backend", "") or ""

    logger.info("Regenerating single collage %s for project %s (backend=%s)", label, project_id, collages_backend or "auto")

    error = await image_gen.generate(label_prompt, out_path, timeout=IMAGE_TIMEOUT, backend=collages_backend)
    if error:
        logger.error("Single collage %s regen failed for project %s: %s", label, project_id, error)
        raise HTTPException(status_code=500, detail=f"方案 {label} 重新生成失败：{error}")

    # Merge
    existing = {c.get("label", ""): c for c in project.get("collages", [])}
    existing[label] = {"label": label, "filename": filename, "path": out_path, "prompt": label_prompt}
    project["collages"] = sorted(existing.values(), key=lambda c: c["label"])
    project["updated_at"] = _now()
    _save(project_id, project)

    collages_response = [
        CollageItem(label=c["label"], filename=c["filename"], download_url=_download_url(c["filename"]))
        for c in project["collages"]
    ]
    return CollageGenerateResponse(
        success=True, project_id=project_id, collages=collages_response,
        message=f"方案 {label} 已重新生成。",
    )
