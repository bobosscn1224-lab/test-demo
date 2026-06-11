"""
LLM-based text-to-Markdown cleaner.

Takes raw text extracted from PDF/DOCX/XLSX/PPTX and converts it to clean,
well-structured Markdown suitable for chunking and embedding.
"""

import logging
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

CLEAN_PROMPT = """你是一个文档格式化助手。请将以下从文件中提取的原始文本转换为干净的 Markdown 格式。

要求：
1. 保留所有事实信息，不要添加或删减内容
2. 修复PDF提取导致的单字换行、乱码、多余空格等问题
3. 识别并格式化：标题（使用 #）、列表（使用 - 或 1.）、表格（使用 | 格式）
4. 保持原文的章节结构和层级关系
5. 如果原文有表格数据，尽可能还原为 Markdown 表格
6. 删除无关的页眉页脚、水印字符
7. 保留人名、职位、部门、流程名称等关键信息
8. 直接输出 Markdown，不要加任何解释或前言

原始文本：
"""


def clean_to_markdown_sync(text: str) -> str:
    """Convert raw extracted text to clean Markdown using the LLM.

    Returns empty string on failure (caller should fall back to raw text).
    """
    if not text or len(text.strip()) < 20:
        return text

    # Truncate very long texts to avoid excessive API cost
    max_input = 8000
    if len(text) > max_input:
        text = text[:max_input] + "\n...(content truncated)..."

    try:
        client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
        )
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=8192,
            temperature=0.1,
            system="你是一个专业的文档格式化工具。只输出格式化后的 Markdown，不输出任何其他内容。",
            messages=[{"role": "user", "content": CLEAN_PROMPT + "\n" + text}],
        )
        # DeepSeek V4 Pro returns ThinkingBlock mixed with TextBlock — extract text only
        text_blocks = [b for b in response.content if b.type == "text"]
        result = text_blocks[0].text if text_blocks else ""
        if not result:
            return text  # Fall back if no text block
        logger.info("Markdown cleaning: %d chars → %d chars", len(text), len(result))
        return result.strip()
    except Exception:
        logger.warning("Markdown cleaning failed, using raw text", exc_info=True)
        return text  # Fall back to raw text on any error
