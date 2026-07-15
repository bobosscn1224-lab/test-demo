"""Codex PPTX Service — delegates image-to-PPTX to Codex CLI with presentations plugin.

Codex (GPT-5.5 + vision + presentations plugin) sees the image directly and
creates a proper editable PPTX via PowerPoint's native API. No python-pptx OOXML issues.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

CODEX_EXE = r"C:\Users\Lenovo\AppData\Local\OpenAI\Codex\bin\8e55c2dd143b6354\codex.exe"

RECONSTRUCTION_PROMPT = """请把这张PPT视觉稿高仿真还原成一个16:9 PPTX文件。

核心目标：
采用"复杂视觉保真+主要文字可编辑"的混合还原策略。最大优先级是保留原图的整体设计质感、构图、视觉完成度和高级感，同时保证主要文字内容可以在PPT中直接编辑。不要把整页简单铺成一张背景图。

硬性要求：
1、主要文字不得整体作为图片保留，必须尽量使用PPT原生文本框重建。
2、必须可编辑的文字包括：主标题、副标题、正文段落、金句、关键数字、关键词、结论框文字、注释文字、页脚说明、章节名、页码。
3、复杂视觉区域内部的小字，如果拆分会明显破坏视觉质感，可以保留为图片，但需要在最终说明中标注。
4、不要为了视觉保真，把所有文字都压成图片。
5、不要为了全量可编辑，把复杂视觉效果重建成低质感的PPT默认图形。

还原策略：
1、先识别页面结构，将画面拆成"复杂视觉资产层"和"可编辑信息层"。
2、复杂视觉资产层优先从原图裁切/提取为高清图片素材嵌入PPTX。
3、可编辑信息层使用PPT原生文本、形状、线条、基础图形和简单图表重建。
4、如果原图文字需要改成可编辑文本，请使用背景色、渐变近似或局部遮罩覆盖原图文字，再叠加可编辑文本，避免重影。
5、对于复杂图标、品牌logo、照片、插画、3D图、拼图、复杂图表、复杂流程图、复杂循环图、复杂背景、材质、纹理、光影、景深、玻璃拟态、金属质感、柔光和投影，可以保留为图片。
6、对于简单线条、分隔线、基础几何框、轻量标签、简单按钮、简单色块、页码、基础表格和简单图表，尽量重建为可编辑PPT元素。
7、品牌logo、商标、产品UI、人物、商品图、官方图标不要手绘或伪造，优先保留为原图裁切图片素材。

文字重建要求：
1、尽量保持原图的字体气质、字号层级、字重、颜色、行距、字距、对齐方式和位置。
2、中文优先选择接近原图的黑体/微软雅黑/思源黑体风格；英文和数字选择与原图接近的无衬线或衬线字体。
3、不允许出现明显错字、漏字、换行错误、文本溢出、文字重叠或位置漂移。

设计还原要求：
1、保持原图的版式、比例、视觉重心、阅读顺序和留白节奏。
2、保持原图的颜色、对比度、明暗关系、光源方向、阴影强度和空间层次。
3、所有元素的位置、大小、层级、裁切方式、圆角、描边、阴影、透明度和对齐关系要尽量贴近原图。

输出要求：
1、输出一个PPTX文件到 data/outputs/ 目录，文件名格式: ppt_codex_{session_id}.pptx
2、简要说明哪些元素是可编辑的，哪些是图片素材。"""


async def generate_pptx(
    image_path: str,
    session_id: str = "",
    output_dir: str | None = None,
    timeout: int = 300,
) -> dict | None:
    """Call Codex CLI to generate an editable PPTX from an image.

    Args:
        image_path: Path to the source PPT image
        session_id: Session identifier for naming
        output_dir: Where to save the output PPTX
        timeout: Max wait time in seconds

    Returns:
        dict with filename, path, url, codex_output
    """
    if not os.path.exists(CODEX_EXE):
        return {"error": f"Codex not found at {CODEX_EXE}"}

    if not os.path.exists(image_path):
        return {"error": f"Image not found: {image_path}"}

    out_dir = Path(output_dir) if output_dir else Path("data/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = session_id[:8] if session_id else uuid.uuid4().hex[:8]
    out_name = f"ppt_codex_{sid}.pptx"
    out_path = out_dir / out_name

    prompt = RECONSTRUCTION_PROMPT + f"\n\n请将生成的PPTX保存到: {out_path}"

    logger.info("Calling Codex for image-to-PPTX: %s -> %s", image_path, out_name)

    try:
        # Run Codex in a thread to avoid blocking the event loop
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_codex, image_path, prompt, timeout),
            timeout=timeout + 30,
        )

        if os.path.exists(out_path):
            size = os.path.getsize(out_path)
            logger.info("Codex PPTX generated: %s (%d bytes)", out_name, size)
            return {
                "filename": out_name,
                "path": str(out_path),
                "url": f"/api/skills/download/{out_name}",
                "size": size,
                "codex_output": result,
            }
        else:
            logger.warning("Codex did not produce output file: %s", out_path)
            return {"error": "Codex completed but no PPTX file was generated", "codex_output": result}

    except asyncio.TimeoutError:
        logger.warning("Codex timed out after %ds", timeout)
        return {"error": f"Codex timed out after {timeout}s. Try a simpler image or increase timeout."}
    except Exception as exc:
        logger.warning("Codex call failed: %s", exc)
        return {"error": f"Codex error: {exc}"}


def _run_codex(image_path: str, prompt: str, timeout: int) -> str:
    """Execute Codex CLI synchronously (called from thread pool)."""
    cmd = [
        CODEX_EXE, "exec",
        "--image", image_path,
        "--sandbox", "workspace-write",
        "--model", "gpt-5.5",
        "--ephemeral",
        prompt,
    ]

    logger.debug("Running: codex exec --image %s ...", os.path.basename(image_path))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=os.path.dirname(image_path) or ".",
        env={**os.environ, "CODEX_HOME": os.path.expanduser("~/.codex")},
    )

    output = result.stdout + "\n" + result.stderr
    if result.returncode != 0:
        logger.warning("Codex exited with code %d: %s", result.returncode, result.stderr[:300])

    return output.strip()
