"""Call the deckweaver pipeline to convert image -> editable PPTX.

Uses the full deckweaver stack at d:/数字分身/deckweaver with
ENABLE_NATIVE_OUTLINE_SHAPES = True for native shape generation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

DECKWEAVER_ROOT = Path(r"d:\数字分身\deckweaver")
SCRIPTS = DECKWEAVER_ROOT / "scripts"
PAGE_SCRIPTS = SCRIPTS / "page"
DECK_SCRIPTS = SCRIPTS / "deck"
PIPELINE_VERSION = "deckweaver_v1"


async def convert_image_to_pptx(
    image_path: str,
    session_id: str = "",
    output_dir: str | None = None,
) -> dict[str, Any]:
    source = Path(image_path)
    if not source.exists():
        return {"error": f"Image not found: {source.name}"}

    out_dir = Path(output_dir) if output_dir else Path("data/outputs")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    sid = (session_id or uuid.uuid4().hex)[:8]
    run_id = uuid.uuid4().hex[:6]
    stem = f"ppt_dw_{sid}_{run_id}"

    work = Path(tempfile.mkdtemp(prefix="dw_"))
    try:
        ocr_data = await _run_rapidocr_export(source, work)
        if not ocr_data:
            return {"error": "RapidOCR detected no text in the image."}
        logger.info("DeckWeaver: OCR found %d text items", len(ocr_data))

        result = await _run_deckweaver_pipeline(source, work)
        if not result:
            return {"error": "Deckweaver pipeline failed"}

        layout_path = work / "layouts" / "page_01.layout.json"
        if not layout_path.exists():
            return {"error": "Layout JSON not generated"}

        pptx_path = out_dir / f"{stem}.pptx"
        await _build_pptx_from_layout(layout_path, pptx_path, source)
        if not pptx_path.exists():
            return {"error": "PPTX build failed"}

        return {
            "filename": pptx_path.name,
            "pipeline_version": PIPELINE_VERSION,
            "path": str(pptx_path),
            "url": f"/api/skills/download/{pptx_path.name}",
            "report": {
                "source": source.name,
                "pipeline_version": PIPELINE_VERSION,
                "text_items": len(ocr_data),
            },
        }
    finally:
        try:
            shutil.rmtree(work, ignore_errors=True)
        except Exception:
            pass


async def _run_rapidocr_export(image_path: Path, work: Path) -> list[dict] | None:
    return await asyncio.to_thread(_run_rapidocr_sync, image_path, work)


def _run_rapidocr_sync(image_path: Path, work: Path) -> list[dict] | None:
    from rapidocr_onnxruntime import RapidOCR
    import cv2, numpy as np

    ocr_dir = work / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)

    engine = RapidOCR()
    data = np.fromfile(str(image_path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        from PIL import Image
        img = np.array(Image.open(str(image_path)).convert("RGB"))[:, :, ::-1]
    if img is None:
        return None

    result, _ = engine(img)
    if not result:
        return None

    items = []
    for box, text, conf in result:
        x1, y1 = int(box[0][0]), int(box[0][1])
        x2, y2 = int(box[2][0]), int(box[2][1])
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        if x2 <= x1 or y2 <= y1 or not text or not text.strip():
            continue
        items.append({
            "text": str(text).strip(),
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "confidence": float(conf) if conf else 0.95,
        })

    out_path = ocr_dir / "page_01.ocr.json"
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


async def _run_deckweaver_pipeline(image_path: Path, work: Path) -> bool:
    return await asyncio.to_thread(_run_pipeline_sync, image_path, work)


def _run_pipeline_sync(image_path: Path, work: Path) -> bool:
    src_dir = work / "source"
    src_dir.mkdir(exist_ok=True)
    dest = src_dir / "page_01.png"
    shutil.copy2(image_path, dest)

    for d in ["inventory", "layouts", "manifests", "assets", "debug"]:
        (work / d).mkdir(exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS)

    try:
        r = subprocess.run(
            [sys.executable, str(PAGE_SCRIPTS / "run_pipeline.py"),
             "--source-dir", str(src_dir),
             "--work-dir", str(work),
             "--pages", "01"],
            capture_output=True, text=True, timeout=180,
            env=env,
        )
        if r.returncode != 0:
            logger.error("Deckweaver pipeline failed:\n%s\n%s",
                         r.stdout[-500:], r.stderr[-500:])
            return False
        logger.info("Deckweaver pipeline OK:\n%s", r.stderr[-300:])
        return True
    except subprocess.TimeoutExpired:
        logger.error("Deckweaver pipeline timed out")
        return False
    except Exception as exc:
        logger.error("Deckweaver pipeline error: %s", exc)
        return False


async def _build_pptx_from_layout(layout_path: Path, output_path: Path, source_image: Path) -> bool:
    return await asyncio.to_thread(_build_pptx_sync, layout_path, output_path, source_image)


def _build_pptx_sync(layout_path: Path, output_path: Path, source_image: Path) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS)

    try:
        r = subprocess.run(
            [sys.executable, str(DECK_SCRIPTS / "build_pptx_from_layout.py"),
             "--layout", str(layout_path),
             "--assets-root", str(layout_path.parent.parent),
             "--out", str(output_path)],
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if r.returncode != 0:
            logger.error("build_pptx failed:\n%s", r.stderr[-500:])
            return False
        return True
    except Exception as exc:
        logger.error("build_pptx error: %s", exc)
        return False
