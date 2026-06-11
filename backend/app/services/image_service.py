"""Extract text from document images using PaddleOCR (local, free, best Chinese OCR)."""
import io
import os
import hashlib
import logging
import asyncio
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

IMAGE_CACHE_DIR = Path("data/image_descriptions")
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(lang='ch')
    return _ocr


class ImageService:
    def __init__(self):
        ImageService._ensure_cache_dir()

    @staticmethod
    def _ensure_cache_dir():
        IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    async def describe_image(self, image_bytes: bytes, source_hint: str = "") -> str:
        """Run PaddleOCR on an image and return extracted text. Results are cached."""
        img_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        cache_path = IMAGE_CACHE_DIR / f"{img_hash}.txt"

        if cache_path.exists():
            cached = cache_path.read_text(encoding="utf-8").strip()
            if cached:
                return cached

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            with open(tmp_path, 'wb') as f:
                f.write(image_bytes)

            ocr = _get_ocr()
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                _OCR_EXECUTOR,
                lambda: list(ocr.predict(tmp_path)),
            )

            if not results:
                return ""

            lines = []
            for res in results:
                # PaddleOCR 3.x returns OCRResult objects; access as dict
                texts = res.get('rec_texts') if isinstance(res, dict) else getattr(res, 'rec_texts', None)
                if texts:
                    for text in texts:
                        text = text.strip()
                        if text:
                            lines.append(text)

            description = "\n".join(lines)

            if description:
                cache_path.write_text(description, encoding="utf-8")
                logger.info("OCR extracted %d chars from image %s (source: %s)",
                            len(description), img_hash, source_hint)
            return description

        except Exception:
            logger.warning("OCR failed for image %s", img_hash, exc_info=True)
            return ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


image_service = ImageService()
