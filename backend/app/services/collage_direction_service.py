"""Select concise, deck-level visual systems for PPT collage exploration."""
from __future__ import annotations

import json
from typing import Any, Callable

from app.services.collage_prompt_spec import get_visual_direction
from app.services.llm_interaction import execute_with_quality_gate


_SYSTEM_PROMPT = """你是商业演示视觉总监。根据项目语境和已确认大纲，选择三种最适合且明显不同的整套视觉系统。
只描述整套视觉语言，不写逐页构图，不改写内容。严格输出 JSON 数组。"""


def _fallback() -> dict[str, str]:
    return {label: get_visual_direction(label) for label in ("A", "B", "C")}


def _render_direction(item: dict[str, Any]) -> str:
    return (
        f"{item['name']}；版式：{item['layout']}；信息密度：{item['density']}；"
        f"图表语言：{item['charts']}；图片方式：{item['imagery']}；"
        f"背景处理：{item['background']}；标题排版：{item['typography']}。"
    )


async def select_visual_directions(
    *,
    project_context: str,
    cleaned_outline: str,
    raw_call: Callable[..., Any] | None = None,
) -> dict[str, str]:
    user_prompt = (
        "━━━ 项目语境 ━━━\n" + project_context.strip() +
        "\n\n━━━ 已确认大纲（仅用于判断视觉方向）━━━\n" + cleaned_outline.strip() +
        "\n\n返回 A/B/C 三个对象。"
    )
    if raw_call is None:
        from app.services.llm_service import LLMService
        raw_call = LLMService()._chat_raw
    try:
        result = await execute_with_quality_gate(
            interaction_name="collage_visual_directions",
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            raw_call=raw_call,
        )
    except Exception:
        return _fallback()
    if not result.success:
        return _fallback()
    try:
        items = json.loads(result.content)
        by_label = {str(item["label"]).upper(): _render_direction(item) for item in items}
        if set(by_label) != {"A", "B", "C"} or len(set(by_label.values())) != 3:
            return _fallback()
        return {label: by_label[label] for label in ("A", "B", "C")}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _fallback()
