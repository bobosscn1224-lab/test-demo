"""PPT Maker v2 — image generation helper (API only, CLI disabled)."""

import logging
import os

from app.services._paths import PUBLIC_DIR

logger = logging.getLogger(__name__)

OUTPUT_DIR = str(PUBLIC_DIR)


async def generate(prompt: str, out_path: str, timeout: int = 420, backend: str = "",
                   reference_url: str = "") -> str | None:
    """Generate an image via image_gen_service API pipeline.

    If backend is specified, use only that backend. Otherwise tries all configured.
    reference_url: optional collage image URL for style reference (tutujin multimodal).
    Returns None on success, error string on failure.
    """
    os.makedirs(os.path.dirname(out_path) or OUTPUT_DIR, exist_ok=True)

    from app.services.image_gen_service import generate_image

    result = await generate_image(prompt, out_path, size="1792x1024", force_backend=backend,
                                   reference_url=reference_url)
    if result.success:
        return None
    return f"图片生成失败：{result.error}"
