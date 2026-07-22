"""Pro Mode — Prompt assembly engine + AI call helper.

The core value of Pro Mode: builds high-quality, consistent prompts for every shot.
Extracted to a shared module so all step services can reuse the same logic.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# AI call helper — shared by all step services
# ═══════════════════════════════════════════════════════════════════

async def ai_analyze(system_prompt: str, user_prompt: str, max_retries: int = 2) -> dict:
    """Call LLM for structured JSON analysis, parse, retry on failure.

    All step services use this single entry point for LLM calls,
    ensuring consistent error handling and retry logic.
    """
    from app.services.llm_service import llm_service
    from app.config import settings

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = await llm_service._chat_raw(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                model=settings.claude_model,
                max_tokens=4096,
                temperature=0.7,
            )
            content = ""
            if hasattr(response, 'content'):
                for block in response.content:
                    if hasattr(block, 'text'):
                        content += block.text
            else:
                content = str(response)

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            return json.loads(content)

        except Exception as e:
            last_error = str(e)
            logger.warning("AI analysis attempt %d/%d failed: %s", attempt + 1, max_retries + 1, e)
            if attempt < max_retries:
                continue

    raise RuntimeError(f"AI 分析失败（已重试 {max_retries} 次）: {last_error}")


# ═══════════════════════════════════════════════════════════════════
# Prompt builders — shared by generation step services
# ═══════════════════════════════════════════════════════════════════

def build_consistency_bible(project: dict) -> str:
    """Build shared style/consistency context applied to ALL shots."""
    chars = project.get("characters", [])
    scenes = project.get("scenes", [])
    dir_cfg = project.get("director_config") or {}

    parts = []

    for c in chars:
        name = c.get("name", "")
        desc = c.get("description", "")
        asset_id = c.get("asset_id", "")
        anchor = f"@{name}: {desc}"
        if asset_id and asset_id.startswith("asset-"):
            anchor += f" [asset://{asset_id}]"
        parts.append(anchor)

    style_rules = []
    if dir_cfg.get("color_tone"):
        style_rules.append(f"Color tone: {dir_cfg['color_tone']}")
    if dir_cfg.get("performance_style"):
        style_rules.append(f"Performance: {dir_cfg['performance_style']}")
    if dir_cfg.get("pace"):
        style_rules.append(f"Pacing: {dir_cfg['pace']}")
    if dir_cfg.get("transitions"):
        style_rules.append(f"Transitions: {dir_cfg['transitions']}")
    if style_rules:
        parts.append("VISUAL STYLE: " + " | ".join(style_rules))

    for s in scenes:
        scene_parts = [f"@{s.get('name','')}: {s.get('description','')[:80]}"]
        if s.get("lighting"):
            scene_parts.append(f"Light: {s.get('lighting','')[:60]}")
        if s.get("time_of_day"):
            scene_parts.append(f"Time: {s.get('time_of_day','')}")
        parts.append(" | ".join(scene_parts))

    parts.append(
        "CONSISTENCY RULES: All shots maintain identical character appearance, "
        "same lighting quality, same color grading, same film stock look "
        "throughout the entire sequence."
    )
    return "\n".join(parts)


def build_shot_prompt(project: dict, shot: dict) -> str:
    """Build a high-quality Seedance prompt for a single shot.

    Structure:
      1. CHARACTERS: @name anchors with detailed descriptions
      2. SCENE: @name with spatial/lighting context
      3. ACTION: shot description + camera + dialogue
      4. MOOD: mood keywords
      5. CONSISTENCY: shared style rules for cross-shot coherence
    """
    chars = project.get("characters", [])
    char_map = {c["id"]: c for c in chars}
    scenes = project.get("scenes", [])
    scene_map = {s["id"]: s for s in scenes}

    sections = []

    # 1. Character Anchors
    char_ids = shot.get("character_ids", [])
    if char_ids:
        char_lines = []
        for cid in char_ids:
            c = char_map.get(cid)
            if c:
                name = c.get("name", "")
                desc = c.get("description", "")
                asset_id = c.get("asset_id", "")
                anchor = f"@{name}: {desc}"
                if asset_id and asset_id.startswith("asset-"):
                    anchor += f" (asset://{asset_id})"
                char_lines.append(anchor)
        if char_lines:
            sections.append("CHARACTERS:\n" + "\n".join(char_lines))

    # 2. Scene Context
    scene_id = shot.get("scene_id", "")
    if scene_id and scene_id in scene_map:
        s = scene_map[scene_id]
        scene_block = f"@{s.get('name','')}: {s.get('description','')}"
        if s.get("lighting"):
            scene_block += f"\nLighting: {s.get('lighting','')}"
        if s.get("time_of_day"):
            scene_block += f"\nTime: {s.get('time_of_day','')}"
        sections.append("SCENE:\n" + scene_block)

    # 3. Action + Camera
    action_parts = []
    if shot.get("description"):
        action_parts.append(shot["description"])
    if shot.get("camera"):
        action_parts.append(f"[Camera: {shot['camera']}]")
    if shot.get("dialogue"):
        action_parts.append(f"[Dialogue: {shot['dialogue']}]")
    if action_parts:
        sections.append("ACTION:\n" + " ".join(action_parts))

    # 4. Mood
    if shot.get("mood"):
        sections.append(f"MOOD: {shot['mood']}")

    # 5. Consistency Bible
    consistency = build_consistency_bible(project)
    if consistency:
        sections.append("CONSISTENCY:\n" + consistency)

    return "\n\n".join(sections)
