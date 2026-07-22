"""Collage prompt building.

All prompt construction for PPT collage generation lives here.
"""

from __future__ import annotations

import re

from app.services.collage_prompt_spec import strip_visual_suggestions

from .layout import calculate_grid_layout


# ── Label maps ───────────────────────────────────────────────────────────

_PURPOSE_LABEL: dict[str, str] = {
    "business_report": "业务汇报", "project_proposal": "项目方案",
    "product_launch": "产品宣讲", "training": "培训辅导",
    "review": "复盘总结", "story_pitch": "故事路演", "other": "其他",
}
_AUDIENCE_LABEL: dict[str, str] = {
    "executives": "老板/管理层", "clients": "客户/合作方",
    "team": "一线团队", "investors": "投资人", "mixed": "混合受众",
}
_STYLE_LABEL: dict[str, str] = {
    "professional": "专业严谨", "tech": "科技感", "minimal": "简约商务",
    "creative": "创意活泼", "bold": "高端大气",
}
_NARRATIVE_LABEL: dict[str, str] = {
    "narrative": "📖 叙事故事型", "data_report": "📊 数据汇报型",
    "business_proposal": "💼 商业方案型", "technical": "🔧 技术拆解型", "auto": "🤖 自动",
}
_FRAMEWORK_LABEL: dict[str, str] = {
    "conflict_driven": "⚡ 冲突驱动型", "scr": "📋 SCR型",
    "problem_driven": "🔍 问题驱动型", "opportunity_driven": "🚀 机会驱动型",
    "abt": "🎬 ABT型", "hook_progressive": "🪝 钩子递进型", "auto": "🤖 自动",
}
_OBJECTIVE_LABEL: dict[str, str] = {
    "drive_decision": "✅ 促成决策/批准", "show_results": "📊 展示成果/复盘",
    "secure_resources": "💰 争取资源/预算", "build_consensus": "🤝 建立共识/对齐",
    "transfer_knowledge": "📖 传递认知/培训", "auto": "🤖 自动",
}
_TONE_LABEL: dict[str, str] = {
    "professional": "👔 专业严谨", "storytelling": "📖 生动故事化",
    "inspirational": "🔥 激励人心", "concise": "⚡ 简洁有力",
    "humorous": "😄 幽默风趣", "auto": "🤖 自动",
}


# ── Public API ───────────────────────────────────────────────────────────

def build_collage_prompts(project: dict) -> list[tuple[str, str]]:
    """Build ONE prompt that generates all 3 collage variants in one image."""
    outline_raw = _clean_for_image(project.get("outline", "").strip())
    outline = strip_visual_suggestions(outline_raw)

    context = build_briefing_context(project)

    return f"""请基于已确认的PPT大纲和逐页内容，生成3版不同视觉风格的PPT拼图方案，放在同一张图上。

━━━ 项目信息 ━━━
{context}

━━━ 任务目标 ━━━
当前阶段只做视觉方向探索，不生成pptx，也不生成逐页单图。请根据这套PPT的主题、行业属性、内容密度、受众场景和叙事风格，自行选择3种最合适的视觉方向，并分别生成一张完整拼图在同一张画布上，方便我比较整体风格、页面节奏和高级感。

━━━ 输出要求 ━━━
1、在同一张图中生成3张PPT拼图：方案A、方案B、方案C，从左到右或从上到下排列，每个方案标注清晰的标签（方案A / 方案B / 方案C）。
2、每张拼图都必须包含整套PPT的所有页面缩略图，并保持正确页序。
3、每个缩略图应是16:9横版PPT页面。
4、三版风格必须明显不同，不要只是换颜色。
5、每一版内部必须使用统一视觉系统，包括字体层级、色彩系统、背景风格、图标样式、卡片/模块样式、页脚和页码样式。
6、每一版都要像一套完整、正式、可落地的商业PPT方案，而不是零散的页面草稿。
7、拼图用于选择方向，文字可以适当缩小，但关键数字、核心图表和页面结构必须能看清楚。

━━━ 内容要求 ━━━
1、严格使用已确认大纲和逐页内容。
2、不要重新编写故事线。
3、不要随意删页、加页、改页序。
4、不要新增未经确认的数据、品牌、logo、人物、产品或来源。

━━━ 视觉要求 ━━━
1、请先理解内容，再判断哪3种方向最合适。
2、三版差异应该体现在版式气质、信息密度、图表语言、图片使用方式、背景处理、视觉重心和标题排版上。
3、所有方案都要保持专业、高级、清晰，不要使用默认PPT模版感。
4、如果需要图标，请保持统一风格。
5、如果需要图表，请保持清晰、可理解、有商业报告质感。
6、如果需要图片，请使用与主题相关的高质量真实感图片或高级商业插图。
7、不要伪造品牌logo、品牌标识、人物肖像、产品UI或未经确认的视觉资产。
8、如果内容属于严肃商业、金融、研究或战略汇报，请优先保证可信度、清晰度和高级感，不要追求夸张视觉效果。

不要输出过多解释文字。不要生成pptx。不要生成逐页单图。

━━━ 已确认大纲与逐页内容 ━━━
{outline}

━━━ 特别强调 ━━━
这一步的目标是替我选择视觉方向，请优先保证三版风格差异明显、每版都适配内容主题、整体观感高级、页面节奏完整，并且后续可以基于其中一版继续生成逐页高清单页图。"""


def build_collage_regen_prompt(
    project: dict, label: str, feedback: str,
) -> str:
    """Build regeneration prompt — same format with feedback."""
    outline_raw = _clean_for_image(project.get("outline", "").strip())
    outline = strip_visual_suggestions(outline_raw)

    return f"""请基于已确认的PPT大纲和逐页内容，重新生成3版不同视觉风格的PPT拼图方案。

修改意见：{feedback.strip()[:500]}

请参考以上修改意见，重新生成方案A、方案B、方案C三张完整拼图在同一张画布上。

━━━ 已确认大纲与逐页内容 ━━━
{outline}"""


def count_pages_in_outline(text: str) -> int:
    """Count page markers in outline text."""
    page_numbers = re.findall(r'第\s*(\d+)\s*页', text)
    return len(dict.fromkeys(page_numbers)) or _count_page_titles(text) or 8


def build_briefing_context(project: dict) -> str:
    """Build structured briefing context from project data."""
    parts: list[str] = []

    name = project.get("name", "").strip()
    if name:
        parts.append(f"**项目名称**：{name}")

    purpose_key = project.get("purpose", "")
    purpose_label = _PURPOSE_LABEL.get(purpose_key, purpose_key) if purpose_key else "未指定"
    parts.append(f"**应用场景**：{purpose_label}")

    audience_key = project.get("audience", "")
    audience_label = _AUDIENCE_LABEL.get(audience_key, audience_key) if audience_key else "未指定"
    parts.append(f"**目标受众**：{audience_label}")

    key_msg = project.get("key_message", "").strip()
    if key_msg:
        parts.append(f"**核心要求**：{key_msg[:800]}")

    styles = project.get("styles", [])
    if styles:
        style_labels = [_STYLE_LABEL.get(s, s) for s in styles]
        parts.append(
            f"**用户偏好的视觉方向**：{'、'.join(style_labels)}。"
            f"请将这 {len(style_labels)} 种风格方向分别应用到不同的方案中，"
            f"每个方案侧重一种风格，不要混在一起。"
        )

    narrative = project.get("narrative_style", "")
    if narrative and narrative != "auto":
        parts.append(f"**叙事风格**：{_NARRATIVE_LABEL.get(narrative, narrative)}")
    framework = project.get("narrative_framework", "")
    if framework and framework != "auto":
        parts.append(f"**叙事框架**：{_FRAMEWORK_LABEL.get(framework, framework)}")
    objective = project.get("objective", "")
    if objective and objective != "auto":
        parts.append(f"**汇报目标**：{_OBJECTIVE_LABEL.get(objective, objective)}")
    tone = project.get("tone", "")
    if tone and tone != "auto":
        parts.append(f"**语调**：{_TONE_LABEL.get(tone, tone)}")

    content_text = project.get("content_text", "").strip()
    if content_text:
        parts.append(f"**用户素材**：{_clean_for_image(content_text)[:1200]}")

    return "\n".join(parts)


# ── Internal helpers ─────────────────────────────────────────────────────

def _clean_for_image(text: str) -> str:
    return re.sub(r'\s*\[(AI增强|参考补充)\]\s*', ' ', text)


def _count_page_titles(outline: str) -> int:
    """Fallback: count page markers in outline."""
    titles = []
    for m in re.finditer(r'第\s*(\d+)\s*页[：:]\s*(.*?)(?:\n|$)', outline):
        title = m.group(2).strip()
        if title:
            titles.append(title[:60])
    if not titles:
        for m in re.finditer(
            r'###\s*第\s*(\d+)\s*页\s*\n\*\*标题\*\*[：:]\s*(.*?)(?:\n|$)', outline
        ):
            titles.append(m.group(2).strip()[:60])
    return len(titles)
