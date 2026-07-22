"""Image generation service — unified entry point for all generation scenarios.

Usage:
    from app.services.image_generation import ImageGenerationService

    # Text-to-image
    result = await ImageGenerationService.text_to_image(prompt, output_path)

    # Image-to-image (with reference)
    result = await ImageGenerationService.image_to_image(prompt, ref_url, output_path)

    # Collage batch (A/B/C variants, concurrent)
    results = await ImageGenerationService.generate_collage_variants(project, ...)

    # Collage single (generate or regenerate one variant)
    result = await ImageGenerationService.generate_collage_single(project, label, ...)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from typing import Callable

from app.services._paths import PUBLIC_DIR
from app.services.collage_prompt_spec import (
    get_generation_runtime,
    strip_visual_suggestions,
)

from .layout import calculate_grid_layout, normalize_collage_image, grid_canvas_size
from .prompts import (
    build_briefing_context,
    build_collage_prompts,
    build_collage_regen_prompt,
    count_pages_in_outline,
)
from .types import CollageBatchResult, GenerationResult

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────

def _download_url(filename: str) -> str:
    return f"/api/skills/download/{filename}"


def _clean_for_image(text: str) -> str:
    return re.sub(r'\s*\[(AI增强|参考补充)\]\s*', ' ', text)


def _emit(callback: Callable, data: dict) -> None:
    """Fire-and-forget callback invocation."""
    import inspect
    try:
        result = callback(data)
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(result)
            except RuntimeError:
                pass
    except Exception:
        pass


# ── Service ──────────────────────────────────────────────────────────────

class ImageGenerationService:
    """统一生图服务 — 所有生图调用的唯一入口。"""

    # ── Low-level methods ────────────────────────────────────────────────

    @staticmethod
    async def text_to_image(
        prompt: str,
        output_path: str,
        *,
        backend: str = "",
        timeout: float | None = None,
        reference_url: str = "",
        progress_callback: Callable | None = None,
    ) -> GenerationResult:
        """纯文本生图。"""
        from app.skills.ppt_maker_v2.image_gen import generate as _gen

        runtime = get_generation_runtime()
        timeout = timeout or int(runtime.get("provider_call_timeout_seconds", 420))
        backend = backend or str(runtime.get("required_backend") or "tutujin_vip")

        error = await _gen(
            prompt, output_path,
            interaction_name="ppt_collage",
            timeout=timeout,
            backend=backend,
            reference_url=reference_url,
            progress_callback=progress_callback,
        )

        if error:
            return GenerationResult(success=False, error=error, backend=backend)

        filename = os.path.basename(output_path)
        return GenerationResult(
            success=True, filename=filename, path=output_path,
            download_url=_download_url(filename), backend=backend,
        )

    @staticmethod
    async def image_to_image(
        prompt: str,
        reference_url: str,
        output_path: str,
        *,
        backend: str = "",
        timeout: float | None = None,
        progress_callback: Callable | None = None,
    ) -> GenerationResult:
        """图生图（以参考图为底版）。"""
        return await ImageGenerationService.text_to_image(
            prompt, output_path,
            backend=backend, timeout=timeout,
            reference_url=reference_url,
            progress_callback=progress_callback,
        )

    # ── Collage batch generation ─────────────────────────────────────────

    @staticmethod
    async def generate_collage_variants(
        project: dict,
        *,
        project_id: str = "",
        on_batch_progress: Callable | None = None,
        on_variant_progress: Callable | None = None,
    ) -> CollageBatchResult:
        """Generate ONE image containing all 3 collage variants (A/B/C).

        Single API call — 3 variants in one image, side by side.
        """
        from app.skills.ppt_maker_v2.image_gen import generate as _gen

        runtime = get_generation_runtime()
        backend = str(runtime.get("required_backend") or "apiyi")
        timeout = int(runtime.get("provider_call_timeout_seconds", 420))

        run_id = uuid.uuid4().hex[:10]
        prompt = build_collage_prompts(project)
        total_pages = count_pages_in_outline(
            strip_visual_suggestions(_clean_for_image(project.get("outline", "").strip()))
        )
        validation_context = {
            "expected_pages": total_pages, "columns": 3,
            "outline": strip_visual_suggestions(_clean_for_image(project.get("outline", "").strip())),
        }

        output_dir = str(PUBLIC_DIR)
        os.makedirs(output_dir, exist_ok=True)
        filename = f"ppt_maker_{project_id[:8]}_{run_id}_collage.png"
        out_path = os.path.join(output_dir, filename)

        if on_batch_progress:
            _emit(on_batch_progress, {"status": "generating", "message": "正在生成三套风格方案..."})

        error = await _gen(
            prompt, out_path,
            interaction_name="ppt_collage",
            validation_context=validation_context,
            timeout=timeout, backend=backend,
            quality="low",
            size="auto",
        )

        if error:
            if on_batch_progress:
                _emit(on_batch_progress, {"status": "failed", "message": str(error)[:200]})
            return CollageBatchResult(
                success=False,
                errors={"batch": str(error)},
                run_id=run_id,
            )

        result = GenerationResult(
            success=True, label="all", filename=filename,
            path=out_path, download_url=_download_url(filename),
            backend=backend,
        )

        if on_batch_progress:
            _emit(on_batch_progress, {
                "status": "completed",
                "message": "三套风格方案已生成（在同一张图上）",
            })

        return CollageBatchResult(
            success=True,
            collages=[result],
            visual_directions={
                "A": "方案A（图上左侧）", "B": "方案B（图上中间）", "C": "方案C（图上右侧）",
            },
            run_id=run_id,
        )

    # ── Single collage generation ────────────────────────────────────────

    @staticmethod
    async def generate_collage_single(
        project: dict,
        label: str,
        *,
        feedback: str = "",
        project_id: str = "",
        on_progress: Callable | None = None,
    ) -> GenerationResult:
        """生成或重新生成单套拼图。"""
        from app.skills.ppt_maker_v2.image_gen import generate as _gen

        runtime = get_generation_runtime()
        backend = str(runtime.get("required_backend") or "tutujin_vip")
        timeout = int(runtime.get("provider_call_timeout_seconds", 420))

        label = label.upper().strip()
        run_id = uuid.uuid4().hex[:10]

        if feedback.strip():
            prompt = build_collage_regen_prompt(project, label, feedback)
        else:
            prompts_list = build_collage_prompts(project)
            match = next((p for l, p in prompts_list if l == label), None)
            if not match:
                return GenerationResult(
                    success=False, label=label,
                    error=f"无法构建方案 {label} 的提示词",
                )
            prompt = match

        output_dir = str(PUBLIC_DIR)
        os.makedirs(output_dir, exist_ok=True)
        filename = f"ppt_maker_{project_id[:8]}_{run_id}_{label.lower()}.png"
        out_path = os.path.join(output_dir, filename)

        total_pages = count_pages_in_outline(
            strip_visual_suggestions(_clean_for_image(project.get("outline", "").strip()))
        )
        validation_context = {"expected_pages": total_pages, "columns": 3,
                            "outline": strip_visual_suggestions(_clean_for_image(project.get("outline", "").strip()))}

        if on_progress:
            _emit(on_progress, {
                "label": label, "status": "generating", "attempt": 1,
                "message": f"正在生成方案 {label}",
            })

        error = await _gen(
            prompt, out_path,
            interaction_name="ppt_collage",
            validation_context=validation_context,
            timeout=timeout, backend=backend,
            progress_callback=on_progress,
            credential_slot=label,
        )

        if error:
            if on_progress:
                _emit(on_progress, {
                    "label": label, "status": "failed",
                    "message": str(error)[:200],
                })
            return GenerationResult(
                success=False, label=label, error=str(error), backend=backend,
            )

        # Post-process
        # Post-process normalization disabled — model layout varies too much
        # norm_error = normalize_collage_image(out_path, total_pages)

        if on_progress:
            _emit(on_progress, {
                "label": label, "status": "completed",
                "message": f"方案 {label} 已生成",
            })

        return GenerationResult(
            success=True, label=label, filename=filename,
            path=out_path, download_url=_download_url(filename),
            backend=backend,
        )
