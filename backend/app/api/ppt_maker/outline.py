"""PPT Maker Feature API — Outline generation endpoint."""

from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm_service import llm_service
from app.services.llm_interaction import execute_with_quality_gate
from app.skills.ppt_maker_v2.prompts import (
    OUTLINE_SYSTEM, OUTLINE_USER,
    SKELETON_SYSTEM, SKELETON_USER,
    MATERIAL_SUMMARY_SYSTEM, MATERIAL_SUMMARY_USER,
)
from app.api.ppt_maker.projects import _load, _save, _now
from app.api.ppt_maker.models import OutlineResponse, OutlineConfirm, OutlinePage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-maker"], redirect_slashes=False)


# ── Purpose / audience / scale display labels ───────────────────────

PURPOSE_LABELS: dict[str, str] = {
    "business_report": "业务汇报",
    "project_proposal": "项目提案",
    "product_launch": "产品发布",
    "training": "培训材料",
    "review": "复盘总结",
    "story_pitch": "故事/融资路演",
    "other": "其他",
}

AUDIENCE_LABELS: dict[str, str] = {
    "executives": "高管/决策层",
    "clients": "客户/合作方",
    "team": "内部团队",
    "investors": "投资人",
    "mixed": "混合受众",
}

SCALE_LABELS: dict[str, str] = {
    "compact_8_12": "精简型（8-12页）",
    "standard_15_20": "标准型（15-20页）",
    "full_25_35": "完整型（25-35页）",
}

STYLE_LABELS: dict[str, str] = {
    "professional": "专业商务",
    "tech": "科技感",
    "minimal": "极简风格",
    "creative": "创意设计",
    "bold": "大胆醒目",
}


def _build_briefing(project: dict) -> str:
    """Build strategic briefing text from project config.

    Note: visual styles are intentionally excluded — they belong to Step 4
    (collage generation), not outline generation.
    """
    purpose = PURPOSE_LABELS.get(project.get("purpose", ""), project.get("purpose", "未指定"))
    audience = AUDIENCE_LABELS.get(project.get("audience", ""), project.get("audience", "未指定"))
    scale = SCALE_LABELS.get(project.get("scale", ""), project.get("scale", "未指定"))
    key_message = project.get("key_message", "未指定")

    narrative_style = project.get("narrative_style", "auto")
    narrative_framework = project.get("narrative_framework", "auto")
    objective = project.get("objective", "auto")
    tone = project.get("tone", "auto")

    style_label = {"auto":"由AI根据素材判断","narrative":"叙事故事型","data_report":"数据汇报型","business_proposal":"商业方案型","technical":"技术拆解型"}.get(narrative_style, narrative_style)
    framework_label = {"auto":"由AI选择","conflict_driven":"冲突驱动型","scr":"SCR型","problem_driven":"问题驱动型","opportunity_driven":"机会驱动型","abt":"ABT三幕型","hook_progressive":"钩子递进型"}.get(narrative_framework, narrative_framework)
    objective_label = {"auto":"由AI根据素材推断","drive_decision":"促成决策/批准","show_results":"展示成果/复盘","secure_resources":"争取资源/预算","build_consensus":"建立共识/对齐","transfer_knowledge":"传递认知/培训"}.get(objective, objective)
    tone_label = {"auto":"由AI根据素材判断","professional":"专业严谨","storytelling":"生动故事化","inspirational":"激励人心","concise":"简洁有力","humorous":"幽默风趣"}.get(tone, tone)

    return (
        f"## 用户需求简报（必须严格遵守）\n\n"
        f"- **演示目的**：{purpose}\n"
        f"- **汇报目标**：{objective_label}\n"
        f"- **目标受众**：{audience}\n"
        f"- **期望规模**：{scale}\n"
        f"- **叙事风格**：{style_label}\n"
        f"- **叙事框架**：{framework_label}\n"
        f"- **语调**：{tone_label}\n"
        f"- **补充要求**：{key_message if key_message else '（无特别要求）'}\n\n"
        f"请根据以上简报生成大纲。用户已明确选择以上偏好，请严格遵守。选择'auto'的项由你根据素材判断最佳方案。"
    )


# ── Endpoints ──────────────────────────────────────────────────────

class OutlineRequestBody(BaseModel):
    feedback: str = ""
    skeleton: str = ""  # JSON skeleton for fill_page stage
    page_index: int | None = None
    regenerate: bool = False

@router.post("/projects/{project_id}/outline", response_model=OutlineResponse)
async def generate_outline(
    project_id: str,
    mode: str = "conservative",
    stage: str = "full",
    body: OutlineRequestBody = OutlineRequestBody(),
) -> OutlineResponse:
    """Generate or regenerate a structured PPT outline.

    Stages:
      - \"full\": Generate complete outline (all pages, all fields) — default
      - \"skeleton\": Generate only page structure (titles + types + roles + core_messages)
      - \"fill_page\": Generate one full page anchored on existing skeleton + style anchor
        Requires page_index (0-based). Feedback should contain the skeleton JSON.
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    existing_outline = project.get("outline", "")
    existing_pages = project.get("outline_pages", [])

    # Build briefing context from project configuration
    briefing_text = _build_briefing(project)

    # Collect source text from content + uploaded files
    source_text = project.get("content_text", "")

    # Read uploaded file contents — extract key sections only
    for f in (project.get("content_files") or []):
        path = f if isinstance(f, str) else f.get("path", "")
        if path and os.path.exists(path):
            try:
                from app.utils.file_parser import parse_file_sync
                file_text = parse_file_sync(path)
                if file_text:
                    filename = os.path.basename(path) if isinstance(f, str) else f.get("name", os.path.basename(path))
                    # Only take first 2000 chars — enough to capture the theme and key points
                    source_text += f"\n\n--- {filename} ---\n{file_text[:2000]}"
                    logger.info("Read file %s: %d chars (using first 2000)", filename, len(file_text))
            except Exception as e:
                logger.warning("Failed to read file %s: %s", path, e)

    if len(source_text.strip()) < 50:
        source_text = f"项目名称：{project.get('name', '')}\n核心信息：{project.get('key_message', '')}"

    # Search knowledge base (RAG) — limited to avoid overwhelming the LLM
    kb_context = ""
    try:
        from app.services.rag_service import rag_service
        query = f"{project.get('name', '')} {project.get('key_message', '')} {source_text[:300]}"
        results = await rag_service.search(query, top_k=3)
        if results:
            kb_context = "\n\n## 知识库参考资料\n" + "\n".join(
                f"- {r.get('content', '')[:250]}" for r in results if r.get('content')
            )[:1200]
            logger.info("RAG returned %d results for outline generation", len(results))
    except Exception as e:
        logger.warning("RAG search skipped: %s", e)

    # Combine sources
    full_source = source_text[:5000]
    if kb_context:
        full_source += kb_context

    # ── Pass 1: Summarize long material (fast, no thinking) ─────────
    if len(full_source) > 2000:
        try:
            summary_prompt = MATERIAL_SUMMARY_USER.format(source_text=full_source[:6000])
            logger.info("Material too long (%d chars), running summarization pass", len(full_source))
            summary_resp = await llm_service.chat(
                interaction_name="material_summarization",
                system_prompt=MATERIAL_SUMMARY_SYSTEM,
                messages=[{"role": "user", "content": summary_prompt}],
                max_tokens=1024,
                temperature=0.2,
                timeout=60,
                thinking={"type": "disabled"},
            )
            summary_text = ""
            if summary_resp.content:
                for block in summary_resp.content:
                    if hasattr(block, "text"):
                        summary_text += block.text
            if len(summary_text.strip()) > 50:
                full_source = f"## 素材结构化摘要\n{summary_text.strip()[:1500]}\n\n## 知识库参考\n{kb_context}" if kb_context else f"## 素材结构化摘要\n{summary_text.strip()[:1500]}"
                logger.info("Material summarized: %d → %d chars", len(source_text), len(full_source))
        except Exception as e:
            logger.warning("Summarization failed, using truncated source: %s", e)
            full_source = full_source[:4000]

    # Enforce page count from user's scale selection
    scale_map = {"compact_8_12": (8,12), "standard_15_20": (15,20), "full_25_35": (25,35),
                 "精简8-12页": (8,12), "标准15-20页": (15,20), "完整25-35页": (25,35)}
    lo, hi = scale_map.get(project.get("scale", ""), (8, 12))

    # Adjust prompt for mode
    system_prompt = OUTLINE_SYSTEM
    mode_instruction = f"\n\n⚠️ 硬性要求：必须生成 {lo}-{hi} 页大纲（不含封底Q&A页），不得少于{lo}页，不得超过{hi}页。"
    if mode == "conservative":
        mode_instruction += "\n⚠️ 保守模式：严格基于用户素材和知识库参考资料，不添加任何外部数据或推测。"
    else:
        system_prompt = OUTLINE_SYSTEM + (
            "\n\n增强模式：在用户素材和知识库基础上，你可以运用行业通用知识、"
            "公开数据基准、方法论框架来丰富内容。补充部分请标注[AI增强]，便于用户区分来源。"
        )
        mode_instruction += "\n🔍 增强模式：可在素材和知识库基础上补充行业数据、对标案例、方法论，补充处标注[AI增强]。"

    # ── Stage: skeleton — dedicated prompt, no full-outline template ──
    if stage == "skeleton":
        mode_instruction = f"\n\n⚠️ 硬性要求：必须恰好生成 {lo}-{hi} 页骨架。每页只输出角色、标题、核心信息三个字段。不输出正文要点和画面构思。"
        prompt = SKELETON_USER.format(
            briefing_text=briefing_text,
            source_text=full_source,
            revision_text=mode_instruction,
            page_range=f"{lo}-{hi}页",
        )
        system_prompt = SKELETON_SYSTEM
        thinking_cfg = {"type": "disabled"}
        max_tokens_out = 2048

    # ── Stage: fill_page — generate one page anchored on skeleton ──
    elif stage == "fill_page" and body.page_index is not None:
        target_page_num = body.page_index + 1
        skeleton_context = body.skeleton if body.skeleton else ""
        # Build style anchor from existing pages (use page 1 as reference)
        style_anchor = ""
        if existing_pages:
            p1 = existing_pages[0]
            style_anchor = f"第1页标题：{p1.get('title','')}\n叙事角色：{p1.get('role','')}\n核心信息：{p1.get('core_message','')}"

        prompt = (
            f"你正在为一份PPT逐页填充第{target_page_num}页的完整内容。\n\n"
            f"━━━ 用户原始素材（所有事实、故事、比喻、场景都从这里来）━━━\n"
            f"{source_text[:3000]}\n\n"
            f"━━━ 风格锚点（第1页的叙事风格，所有后续页必须延续）━━━\n"
            f"{style_anchor}\n\n"
            f"━━━ 整份PPT的页面骨架（了解全貌）━━━\n"
            f"{skeleton_context[:4000]}\n\n"
            f"━━━ 任务：填充第{target_page_num}页 ━━━\n"
            f"不只是列概念——要讲故事、描场景、用比喻。\n"
            f"正文要点中至少有一条引用素材中的具体故事或场景。\n"
            f"叙事风格必须与风格锚点完全一致。\n\n"
            f"输出格式：\n"
            f"### 第{target_page_num}页：[类型]\n"
            f"- **本页在故事中的角色**：（在整体叙事中的作用）\n"
            f"- **与前一页的关系**：（从___自然过渡到___）\n"
            f"- **核心信息**：（一句话，听众必须记住）\n"
            f"- **结论式标题**：（观点，不是话题）\n"
            f"- **正文要点**：（≥3条，至少1条包含具体故事/场景/比喻，不只列抽象概念）\n"
            f"- **画面构思和视觉建议**：（构图+色彩+焦点+图表类型）\n"
            f"{'用户修改意见：' + body.feedback.split('用户修改意见：')[1] if '用户修改意见：' in (body.feedback or '') else ''}"
        )
        thinking_cfg = {"type": "disabled"}
        max_tokens_out = 1024

    # ── Stage: full (default) — generate complete outline ──────────
    else:
        # Build revision text: mode instruction + user feedback if regenerating
        revision_text = mode_instruction
        if body.regenerate and body.feedback and body.feedback.strip():
            feedback_str = body.feedback.strip()
            feedback_len = len(feedback_str)

            # Include existing outline so LLM knows what it's modifying
            existing_context = ""
            if existing_outline.strip():
                existing_context = (
                    f"\n\n━━━ 当前大纲（供参考，需根据修改意见调整或重写）━━━\n"
                    f"{existing_outline[:3000]}\n"
                )

            # Distinguish: substantial new content (>200 chars) vs short modification notes
            if feedback_len > 200:
                # User provided detailed requirements/background — treat as PRIMARY input
                revision_text = (
                    f"{mode_instruction}\n\n"
                    f"━━━ 用户提供了详细的新要求和背景（这是本次生成的核心输入，必须完整体现）━━━\n"
                    f"{feedback_str}\n\n"
                    f"{existing_context}"
                    f"请将以上「用户提供的新要求和背景」作为大纲生成的核心依据，"
                    f"结合原有素材和当前大纲的合理部分，重新构建一份全新的大纲。"
                    f"用户的新要求优先级最高——如果新要求与当前大纲冲突，以新要求为准。"
                )
                # Also merge substantial feedback into full_source so it's part of the "资料" section
                full_source = (
                    f"## 用户补充的关键要求和背景（优先级最高）\n{feedback_str[:3000]}\n\n"
                    f"## 原有素材\n{full_source}"
                )
            else:
                # Short modification instructions
                revision_text = (
                    f"{mode_instruction}\n\n"
                    f"━━━ 用户修改意见（必须严格遵循）━━━\n"
                    f"{feedback_str}\n\n"
                    f"{existing_context}"
                    f"请根据以上修改意见重新调整大纲。特别注意用户指出的问题，"
                    f"确保新生成的大纲解决了这些反馈。"
                )
            logger.info("Outline regeneration with feedback (%d chars)", feedback_len)

        prompt = OUTLINE_USER.format(
            briefing_text=briefing_text,
            source_text=full_source,
            revision_text=revision_text,
        )
        need_thinking = (mode == "enhanced") or (len(full_source) > 3000)
        thinking_cfg = (
            {"type": "enabled", "budget_tokens": 1024} if need_thinking
            else {"type": "disabled"}
        )
        max_tokens_out = 8192

    thinking_on = thinking_cfg.get("type") != "disabled" if isinstance(thinking_cfg, dict) else False
    logger.info(
        "Generating outline for project %s (mode=%s, stage=%s, source=%d chars, thinking=%s)",
        project_id, mode, stage, len(full_source), "on" if thinking_on else "off",
    )

    try:
        # Output anchoring: pre-fill only for full stage (skeleton and fill_page have their own formats)
        msgs: list = [{"role": "user", "content": prompt}]
        outline_prefix = ""
        if stage == "full":
            msgs.append({"role": "assistant", "content": "## 演示策略\n**演示目的**："})
            outline_prefix = "## 演示策略\n**演示目的**："
        elif stage == "fill_page":
            msgs.append({"role": "assistant", "content": f"### 第{body.page_index+1}页："})
            outline_prefix = f"### 第{body.page_index+1}页："
        # skeleton stage: no pre-fill

        # Build briefing context for retry template
        extra_ctx = {
            "source_text": source_text[:5000] if source_text else "",
            "briefing_text": briefing_text if briefing_text else "",
            "revision_text": revision_text if revision_text else "",
        }

        result = await execute_with_quality_gate(
            interaction_name="outline_generation",
            system_prompt=system_prompt,
            user_prompt=prompt,
            llm_service=llm_service,
            extra_context=extra_ctx,
            thinking=thinking_cfg,
        )

        if not result.success:
            logger.error(
                "Outline generation quality gate failed: %s (retries=%d, failures=%s)",
                result.error, result.retries_used, ", ".join(result.quality_failures[-5:]),
            )
            raise HTTPException(
                status_code=500,
                detail=f"大纲生成质量检查未通过（重试{result.retries_used}次）：{result.error}",
            )

        outline = outline_prefix + result.content
        logger.info(
            "Outline generation PASSED quality gate: %d checks, %d retries",
            len(result.checks_passed), result.retries_used,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("LLM outline generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"大纲生成失败：{exc}")

    outline = outline.strip()
    if not outline:
        raise HTTPException(status_code=500, detail="LLM 返回了空内容，请重试。")

    # Parse structured pages from LLM output
    try:
        if stage == "skeleton":
            pages = _parse_skeleton(outline)
        else:
            pages = _parse_outline(outline)
    except Exception as parse_err:
        logger.warning("Outline parsing failed, using raw text: %s", parse_err)
        pages = []

    # ── Save based on stage ────────────────────────────────────────
    if stage == "skeleton":
        project["outline"] = outline
        project["outline_mode"] = mode
        project["outline_pages"] = [p.model_dump() for p in pages]  # skeleton pages
        project["status"] = "outline_generated"
        project["updated_at"] = _now()
        _save(project_id, project)
        return OutlineResponse(
            success=True, project_id=project_id,
            outline=outline, pages=pages,
            message=f"骨架已生成，共 {len(pages)} 页。请逐页填充内容。",
        )

    elif stage == "fill_page" and body.page_index is not None:
        # Merge the new page into existing pages
        if pages:
            new_page = pages[0]  # single page returned
            updated = False
            for i, p in enumerate(project.get("outline_pages", [])):
                if p.get("page_num") == new_page.page_num:
                    project["outline_pages"][i] = new_page.model_dump()
                    updated = True
                    break
            if not updated:
                project["outline_pages"].append(new_page.model_dump())
            # Sort by page_num
            project["outline_pages"].sort(key=lambda p: p.get("page_num", 0))
        project["updated_at"] = _now()
        _save(project_id, project)
        return OutlineResponse(
            success=True, project_id=project_id,
            outline=project.get("outline", ""),
            pages=[OutlinePage(**p) for p in project.get("outline_pages", [])],
            message=f"第{body.page_index+1}页已生成。",
        )

    else:
        # Full generation
        project["outline"] = outline
        project["outline_mode"] = mode
        project["outline_pages"] = [p.model_dump() for p in pages]
        project["status"] = "outline_generated"
        project["updated_at"] = _now()
        _save(project_id, project)
        return OutlineResponse(
            success=True, project_id=project_id,
            outline=outline, pages=pages,
            message=f"大纲已生成，共解析出 {len(pages)} 页。",
        )


@router.put("/projects/{project_id}/outline", response_model=OutlineResponse)
async def confirm_outline(project_id: str, data: OutlineConfirm) -> OutlineResponse:
    """Confirm or update the outline for a project.

    After the user edits the outline, they submit the final version here.
    This advances the project status to outline_confirmed.
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    project["outline"] = data.outline
    project["outline_pages"] = [p.model_dump() for p in _parse_outline(data.outline)]
    project["status"] = "outline_confirmed"
    project["updated_at"] = _now()
    _save(project_id, project)

    logger.info("Outline confirmed for project %s", project_id)

    return OutlineResponse(
        success=True,
        project_id=project_id,
        outline=data.outline,
        pages=_parse_outline(data.outline),
        message="大纲已确认，可以进入拼图生成阶段。",
    )


# ── Skeleton parser ──────────────────────────────────────────────────

def _parse_skeleton(text: str) -> list[OutlinePage]:
    """Parse skeleton-format output with narrative strategy + per-page logic."""
    import re
    pages: list[OutlinePage] = []
    seen_cover = False

    # Find the "逐页逻辑设计" section
    logic_start = text.find('逐页逻辑设计')
    if logic_start < 0:
        logic_start = text.find('页面骨架')
    section_text = text[logic_start:] if logic_start >= 0 else text

    # Split by "### 第N页" markers
    sections = re.split(r'\n(?=###\s*第\s*\d+\s*页)', section_text)
    if len(sections) <= 1:
        sections = re.split(r'(?:^|\n)#{1,4}\s*第\s*(\d+)\s*页', section_text)

    for section in sections:
        section = section.strip()
        if not section or len(section) < 10:
            continue

        num_match = re.search(r'第\s*(\d+)\s*页', section)
        if not num_match:
            continue
        page_num = int(num_match.group(1))

        # Type detection
        page_type = "content"
        if not seen_cover and (page_num == 1 or any(w in section.lower() for w in ['封面', 'cover'])):
            page_type = "cover"; seen_cover = True
        elif any(w in section for w in ['总结', '行动号召', '下一步', '收束']):
            page_type = "summary"

        # Extract fields from new format
        title = _extract_field(section, ['标题', '主标题'])
        if not title:
            title = f"第{page_num}页"

        role = _extract_field(section, ['为什么需要这一页', '角色'])
        expression = _extract_field(section, ['表达方式'])
        audience_effect = _extract_field(section, ['听众看完这页会'])
        transition = _extract_field(section, ['承接上一页的逻辑'])

        # Build role from multiple fields
        full_role = role
        if transition:
            full_role = f"{role} | {transition}" if role else transition

        # Core message combines role + audience effect
        core = expression if expression else ""
        if audience_effect:
            core = f"{core} → {audience_effect}" if core else audience_effect

        pages.append(OutlinePage(
            page_num=page_num, title=title, type=page_type,
            role=full_role[:300] if full_role else "",
            core_message=core[:300] if core else "",
            points=[], visual_hint="",  # skeleton — empty, filled in Phase 2
        ))

    if not pages:
        # Fallback: try old skeleton format or create minimal pages
        blocks = [b.strip() for b in text.split('\n\n') if len(b.strip()) > 20 and '第' in b[:20]]
        for i, block in enumerate(blocks[:20], 1):
            title_match = re.search(r'标题[：:]\s*(.+?)(?:\n|$)', block)
            title_line = title_match.group(1)[:100] if title_match else block.split('\n')[0][:100]
            pages.append(OutlinePage(
                page_num=i, title=re.sub(r'\*\*|##|###', '', title_line).strip(),
                type="content", points=[], visual_hint="",
            ))

    return pages


# ── Outline parser ──────────────────────────────────────────────────

def _parse_outline(text: str) -> list[OutlinePage]:
    """Parse LLM-generated outline text into structured OutlinePage objects.

    Handles format: ### 第N页：标题  or  第N页：标题
    Extracts: title, type, role, core_message, points, visual_hint
    """
    import re

    pages: list[OutlinePage] = []

    # Split by page markers: ### 第N页, 第N页, ### Page N, etc.
    page_sections = re.split(r'\n(?=#{1,4}\s*第\s*\d+\s*页|\s*第\s*\d+\s*页[：:])', text)

    # Also try splitting by the pattern if the above didn't work
    if len(page_sections) <= 1:
        page_sections = re.split(r'(?:^|\n)(?:#{1,4}\s*)?第\s*(\d+)\s*页[：:\s]', text)
        # Reconstruct sections with page numbers
        if len(page_sections) > 1:
            reconstructed = []
            for i in range(1, len(page_sections), 2):
                if i + 1 < len(page_sections):
                    reconstructed.append(f"第{page_sections[i]}页：{page_sections[i+1]}")
            page_sections = reconstructed

    seen_cover = False

    for section in page_sections:
        section = section.strip()
        if not section or len(section) < 10:
            continue

        # Extract page number
        num_match = re.search(r'第\s*(\d+)\s*页', section)
        if not num_match:
            continue
        page_num = int(num_match.group(1))
        lines = section.split('\n')

        # Extract title: look for "标题" marker or use first substantive line after page marker
        title = _extract_field(section, ['结论式标题', '标题', '主标题', 'title'])
        if not title:
            for line in lines:
                line = line.strip().lstrip('#').strip()
                # Skip metadata lines
                if not line or any(kw in line for kw in ['角色', '关系', '核心信息', '核心观点', '视觉', '正文', '要点', '第', '页']):
                    continue
                title = re.sub(r'\*\*([^*]+)\*\*', r'\1', line)[:100]
                break
        if not title:
            title = f"第{page_num}页"

        # Detect page type — only first page that matches gets "cover"
        page_type = "content"
        section_lower = section.lower()
        if not seen_cover and any(w in section_lower for w in ['封面', 'cover', '标题页']):
            page_type = "cover"
            seen_cover = True
        elif any(w in section_lower for w in ['目录', 'agenda', 'toc', 'contents']):
            page_type = "toc"
        elif any(w in section_lower for w in ['总结', '下一步', '感谢', 'summary', 'conclusion', 'ending']):
            page_type = "summary"

        # Extract fields
        role = _extract_field(section, ['角色', 'role'])
        core = _extract_field(section, ['核心信息', '核心观点', 'core message', 'key message'])
        visual = _extract_field(section, ['画面构思和视觉建议', '画面构思', '视觉建议', '视觉', 'visual', '图表类型'])

        # Extract bullet points — look for lines starting with - or • or numbered
        points = []
        in_bullets = False
        for line in lines:
            stripped = line.strip()
            # Start bullet section
            if any(kw in stripped for kw in ['正文要点', '要点', 'key points', '核心内容']):
                in_bullets = True
                continue
            # End bullet section on next section header — MUST be line-start field pattern
            if in_bullets and re.match(r'^[-•]*\s*\*\*[^*]+\*\*[：:]', stripped):
                in_bullets = False
                continue
            if in_bullets or stripped.startswith('-') or stripped.startswith('•') or stripped.startswith('*') or re.match(r'^\d+[.、]', stripped):
                point = re.sub(r'^[-•*\d]+[.、\s]*', '', stripped).strip()
                # Filter out field labels and role descriptions
                label_patterns = ['角色', '关系', '核心信息', '核心观点', '演示目的', '目标受众',
                                  '叙事框架', '关键信息', '标题', '正文要点', '要点', '画面构思', '视觉建议']
                if (len(point) > 5 and not point.startswith('#')
                        and not any(kw in point[:20] for kw in label_patterns)):
                    # Split comma/semicolon-concatenated points
                    if any(sep in point for sep in ['；', ';', '，', ',', '、']):
                        sub_points = re.split(r'[；;，,、]', point)
                        for sp in sub_points:
                            sp = sp.strip()
                            if len(sp) > 5:
                                points.append(sp[:200])
                    else:
                        points.append(point[:200])
                in_bullets = True

        # Also look for bold markers **xxx** which often indicate key points
        if not points:
            bold_matches = re.findall(r'\*\*(.+?)\*\*', section)
            for m in bold_matches:
                if len(m) > 5 and m not in [title, role, core]:
                    points.append(m[:200])

        # Filter out field labels and role descriptions from points
        skip_patterns = ['角色', '关系', '核心信息', '核心观点', '演示目的', '目标受众', '叙事框架', '关键信息',
                        'role', 'core message', 'purpose', 'audience']
        points = [p for p in points if not any(kw in p[:20] for kw in skip_patterns)]
        points = points[:5]

        pages.append(OutlinePage(
            page_num=page_num,
            title=title,
            type=page_type,
            role=role[:200] if role else "",
            core_message=core[:200] if core else "",
            points=points,
            visual_hint=visual[:200] if visual else "",
        ))

    # If parsing failed, create minimal pages from raw text
    if not pages:
        # Create one page per major text block
        blocks = [b.strip() for b in text.split('\n\n') if len(b.strip()) > 30]
        for i, block in enumerate(blocks[:30], 1):
            title_line = block.split('\n')[0][:100]
            pages.append(OutlinePage(
                page_num=i,
                title=re.sub(r'\*\*|##|###', '', title_line).strip(),
                type="content",
                points=[l.strip().lstrip('-•* ') for l in block.split('\n')[1:6] if len(l.strip()) > 10],
            ))

    return pages


def _extract_field(text: str, keywords: list[str]) -> str:
    """Extract a field value from text by keyword matching."""
    import re
    for kw in keywords:
        # Match patterns like "**角色**：xxx" or "- **角色**：xxx" or "角色：xxx"
        patterns = [
            rf'\*\*{kw}\*\*[：:]\s*(.+?)(?:\n|$)',
            rf'[-•]\s*\*\*{kw}\*\*[：:]\s*(.+?)(?:\n|$)',
            rf'(?:\*\*)?{kw}(?:\*\*)?[：:]\s*(.+?)(?:\n|$)',
            rf'[-•]\s*{kw}[：:]\s*(.+?)(?:\n|$)',
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return ""
