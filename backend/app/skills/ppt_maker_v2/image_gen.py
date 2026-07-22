"""PPT Maker v2 — image generation helper (API only, CLI disabled)."""

from __future__ import annotations

import asyncio
import logging
import os

from app.services._paths import PUBLIC_DIR

logger = logging.getLogger(__name__)

OUTPUT_DIR = str(PUBLIC_DIR)


async def generate(prompt: str, out_path: str, *, interaction_name: str,
                   validation_context: dict | None = None, timeout: int = 420,
                   backend: str = "", reference_url: str = "",
                   progress_callback=None, credential_slot: str = "",
                   quality: str = "standard", size: str = "1792x1024") -> str | None:
    """Generate an image via image_gen_service API pipeline.

    If backend is specified, use only that backend. Otherwise tries all configured.
    reference_url: optional collage image URL for style reference (tutujin multimodal).
    quality: "low" | "medium" | "high" — for apiyi backend.
    Returns None on success, error string on failure.
    """
    os.makedirs(os.path.dirname(out_path) or OUTPUT_DIR, exist_ok=True)

    from app.services.image_gen_service import generate_image

    overall_timeout = timeout
    if interaction_name == "ppt_collage":
        from app.services.collage_prompt_spec import get_generation_runtime
        runtime = get_generation_runtime()
        max_calls = int(runtime.get("max_paid_calls_per_variant", 2))
        cooldown = min(float(runtime.get("retry_cooldown_seconds", 8)), float(timeout))
        overall_timeout = float(timeout) * max_calls + cooldown
    try:
        result = await asyncio.wait_for(
            generate_image(
                prompt, out_path, interaction_name=interaction_name,
                validation_context=validation_context, size=size,
                quality=quality,
                force_backend=backend, reference_url=reference_url,
                provider_timeout=timeout,
                progress_callback=progress_callback,
                credential_slot=credential_slot,
            ),
            timeout=overall_timeout,
        )
    except asyncio.TimeoutError:
        return f"图片生成超时（单次调用上限{timeout}秒）"
    if result.success:
        return None
    return f"图片生成失败：{result.error}"
