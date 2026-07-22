"""PPT Maker Feature API — Single page generation endpoint."""

from __future__ import annotations

import logging
import os
import re
import uuid

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services._paths import PUBLIC_DIR
from app.services.collage_prompt_spec import get_variant_style_system
from app.skills.ppt_maker_v2 import image_gen
from app.skills.ppt_maker_v2.prompts import SINGLE_PAGE_BASE
from app.skills.ppt_maker_v2.constants import IMAGE_TIMEOUT
from app.api.ppt_maker.projects import _load, _save, _now
from app.api.ppt_maker.models import (
    PageGenerateResponse, PageItem, PageRegenerateRequest, PageUpdateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ppt-maker"], redirect_slashes=False)


# ── Style label & visual system maps ──────────────────────────────────

_STYLE_LABEL: dict[str, str] = {
    "professional": "专业严谨", "tech": "科技感", "minimal": "简约商务",
    "creative": "创意活泼", "bold": "高端大气",
}

def _clean_for_image(text: str) -> str:
    """Strip AI markers that would pollute image generation prompts."""
    return re.sub(r'\s*\[(AI增强|参考补充)\]\s*', ' ', text)


def _download_url(filename: str) -> str:
    """Build a download URL for an image file in PUBLIC_DIR (relative path)."""
    return f"/api/skills/download/{filename}"


def _build_style_text(project: dict, variant: str) -> str:
    """Build a visual style description from the project's selected styles.

    variant: "A", "B", or "C" — each emphasizes different aspects of the user's styles.
    """
    return get_variant_style_system(project.get("styles", []), variant)


def _extract_slides(outline: str) -> list[dict]:
    """Parse individual slide sections from an outline text.

    Looks for 「第X页」 markers; falls back to paragraph chunks.
    """
    matches = list(re.finditer(
        r"(第\s*\d+\s*页[:：]?.*?)(?=第\s*\d+\s*页[:：]?|\Z)",
        outline,
        re.S,
    ))
    slides: list[dict] = []
    for i, m in enumerate(matches, 1):
        text = m.group(1).strip()
        title = text.split("\n")[0].strip() if "\n" in text else text[:80]
        title = re.sub(r"^第\s*\d+\s*页[:：]?\s*", "", title)
        slides.append({"index": i, "title": title, "content": text[:3000]})

    # Fallback: split by blank lines
    if not slides:
        chunks = [c.strip() for c in outline.split("\n\n") if c.strip()][:20]
        for i, c in enumerate(chunks, 1):
            title = c.split("\n")[0][:80] if "\n" in c else c[:80]
            slides.append({"index": i, "title": title, "content": c[:3000]})
    return slides


def _detect_layout(content: str) -> str:
    """Detect page layout type from content keywords."""
    c = content.lower()
    if any(w in c for w in ["封面", "title", "标题页", "cover"]):
        return "COVER — centered title + subtitle, org/date at bottom"
    if any(w in c for w in ["目录", "agenda", "contents"]):
        return "AGENDA/TOC — numbered list layout"
    if any(w in c for w in ["图表", "chart", "数据", "趋势", "对比", "占比", "%"]):
        return "DATA/CHART — chart-focused with 2-3 insight callouts"
    if any(w in c for w in ["对比", "比较", "vs", "方案", "优劣"]):
        return "COMPARISON — multi-column comparison layout"
    if any(w in c for w in ["流程", "步骤", "阶段", "process", "step", "timeline"]):
        return "PROCESS/TIMELINE — horizontal or vertical flow"
    if any(w in c for w in ["总结", "下一步", "感谢", "summary", "conclusion"]):
        return "SUMMARY/CLOSING — key takeaways or call-to-action"
    if any(w in c for w in ["概述", "背景", "目标", "现状"]):
        return "OVERVIEW — title + 2-4 text blocks"
    return "CONTENT — standard business slide"


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/projects/{project_id}/pages", response_model=PageGenerateResponse)
async def generate_pages(project_id: str) -> PageGenerateResponse:
    """Generate high-res single-page images for each slide in the outline.

    Requires a confirmed outline and a selected collage variant.
    Uses ALL persisted project data (styles, purpose, scale) to customize
    the visual system for each page.

    This is a long-running operation — each page may take several minutes.
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = _clean_for_image(project.get("outline", "").strip())
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲。")

    choice = project.get("selected_collage", "A").upper().strip()
    if not choice or choice not in ("A", "B", "C"):
        choice = "A"

    # Find collage filename for reference context
    collage_filename = ""
    for c in project.get("collages", []):
        if c.get("label") == choice:
            collage_filename = c.get("filename", "")
            break

    # Build visual style text from user's selected styles, not hardcoded A/B/C
    style_text = _build_style_text(project, choice)

    # Parse outline into individual slides
    slides = _extract_slides(outline)
    if not slides:
        raise HTTPException(status_code=400, detail="无法从大纲中解析出单独的页面。请检查大纲格式。")

    total = len(slides)
    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    pages: list[dict] = []
    pages_response: list[PageItem] = []

    for slide in slides:
        idx = slide["index"]
        filename = f"ppt_maker_{project_id[:8]}_{run_id}_page_{idx:02d}.png"
        out_path = os.path.join(output_dir, filename)

        layout_type = _detect_layout(_clean_for_image(slide.get("content", "")))

        prompt = SINGLE_PAGE_BASE.format(
            page_num=idx,
            total_pages=total,
            choice_label=choice,
            collage_filename=collage_filename,
            style_text=style_text,
            layout_type=layout_type,
            slide_content=_clean_for_image(slide.get("content", ""))[:2000],
        )

        # Build reference image URL from the selected collage
        ref_url = ""
        if collage_filename:
            port = getattr(settings, "port", 8001)
            ref_url = f"http://localhost:{port}/api/skills/download/{collage_filename}"

        logger.info(
            "Generating page %d/%d for project %s (styles=%s, choice=%s, ref=%s)",
            idx, total, project_id, project.get("styles"), choice, collage_filename or "none",
        )

        error = await image_gen.generate(
            prompt, out_path, interaction_name="ppt_slide",
            validation_context={"page": idx, "expected_aspect": 16 / 9},
            timeout=IMAGE_TIMEOUT, backend=project.get("image_backend", ""),
            reference_url=ref_url,
        )
        if error:
            logger.error("Page %d generation failed for project %s: %s", idx, project_id, error)
            # Save whatever pages we have so far before raising error
            if pages:
                project["page_images"] = sorted(pages, key=lambda p: p["page_num"])
                project["updated_at"] = _now()
                _save(project_id, project)
                logger.info("Saved %d partial pages before failure", len(pages))
            raise HTTPException(
                status_code=500,
                detail=f"第 {idx}/{total} 页生成失败（已保存前 {len(pages)} 页）：{error}",
            )

        pages.append({
            "page_num": idx,
            "title": slide.get("title", ""),
            "filename": filename,
            "path": out_path,
            "prompt": prompt,  # persisted for future reference / regeneration
        })
        pages_response.append(PageItem(
            page_num=idx,
            title=slide.get("title", ""),
            filename=filename,
            download_url=_download_url(filename),
        ))

        # Incremental save after each successful page
        project["page_images"] = sorted(pages, key=lambda p: p["page_num"])
        project["updated_at"] = _now()
        _save(project_id, project)
        logger.info("Saved page %d/%d for project %s", idx, total, project_id)

    # Save pages to project
    project["page_images"] = sorted(pages, key=lambda p: p["page_num"])
    project["status"] = "pages_generated"
    project["updated_at"] = _now()
    _save(project_id, project)

    logger.info("All %d pages generated for project %s", total, project_id)

    return PageGenerateResponse(
        success=True,
        project_id=project_id,
        pages=pages_response,
        total_pages=total,
        message=f"全部 {total} 页已生成。",
    )


@router.put(
    "/projects/{project_id}/pages/{page_num}",
    response_model=PageUpdateResponse,
)
async def regenerate_page(
    project_id: str,
    page_num: int,
    data: PageRegenerateRequest,
) -> PageUpdateResponse:
    """Regenerate a specific page with optional modifications.

    If modifications are provided, they are appended to the page content
    as additional instructions for the image generator.
    Uses project's persisted style data for visual consistency.
    """
    try:
        project = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    outline = _clean_for_image(project.get("outline", "").strip())
    if not outline:
        raise HTTPException(status_code=400, detail="请先生成并确认大纲。")

    choice = project.get("selected_collage", "A").upper().strip()
    if not choice or choice not in ("A", "B", "C"):
        choice = "A"

    # Find the target slide content
    slides = _extract_slides(outline)
    target_slide = None
    for s in slides:
        if s["index"] == page_num:
            target_slide = s
            break

    if target_slide is None:
        raise HTTPException(
            status_code=404,
            detail=f"第 {page_num} 页在大纲中未找到。大纲共有 {len(slides)} 页。",
        )

    total = len(slides)

    # Apply modifications to slide content
    slide_content = _clean_for_image(target_slide.get("content", ""))[:2000]
    if data.modifications:
        slide_content += f"\n\n修改要求：{data.modifications}"

    # Use project's persisted styles for visual system
    style_text = data.style_preference if data.style_preference else _build_style_text(project, choice)

    collage_filename = ""
    for c in project.get("collages", []):
        if c.get("label") == choice:
            collage_filename = c.get("filename", "")
            break

    output_dir = str(PUBLIC_DIR)
    os.makedirs(output_dir, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]

    filename = f"ppt_maker_{project_id[:8]}_{run_id}_page_{page_num:02d}.png"
    out_path = os.path.join(output_dir, filename)

    layout_type = _detect_layout(slide_content)

    prompt = SINGLE_PAGE_BASE.format(
        page_num=page_num,
        total_pages=total,
        choice_label=choice,
        collage_filename=collage_filename,
        style_text=style_text,
        layout_type=layout_type,
        slide_content=slide_content,
    )

    # Build reference image URL
    regen_ref_url = ""
    if collage_filename:
        port = getattr(settings, "port", 8001)
        regen_ref_url = f"http://localhost:{port}/api/skills/download/{collage_filename}"

    logger.info("Regenerating page %d for project %s (ref=%s)", page_num, project_id, collage_filename or "none")

    error = await image_gen.generate(
        prompt, out_path, interaction_name="ppt_slide",
        validation_context={"page": page_num, "expected_aspect": 16 / 9},
        timeout=IMAGE_TIMEOUT, backend=project.get("image_backend", ""),
        reference_url=regen_ref_url,
    )
    if error:
        logger.error("Page %d regeneration failed for project %s: %s", page_num, project_id, error)
        raise HTTPException(
            status_code=500,
            detail=f"第 {page_num} 页重新生成失败：{error}",
        )

    # Update the page entry in project data
    pages = list(project.get("pages", []))
    replaced = False
    for p in pages:
        if p.get("index") == page_num:
            p["filename"] = filename
            p["path"] = out_path
            p["title"] = target_slide.get("title", "")
            replaced = True
            break
    if not replaced:
        pages.append({
            "index": page_num,
            "title": target_slide.get("title", ""),
            "filename": filename,
            "path": out_path,
        })

    project["page_images"] = sorted(pages, key=lambda p: p.get("index", 0))
    project["updated_at"] = _now()
    _save(project_id, project)

    return PageUpdateResponse(
        success=True,
        project_id=project_id,
        page_num=page_num,
        filename=filename,
        download_url=_download_url(filename),
        message=f"第 {page_num} 页已重新生成。",
    )
