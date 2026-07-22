"""
Collage Prompt Specification — shared module for v1 and v2 PPT maker.

Loads rules from collage_prompt_spec.yaml (the single source of truth).
Provides:
  - build_collage_prompt():        build a complete collage prompt
  - build_regen_prompt():          build a single-plan regeneration prompt
  - strip_visual_suggestions():    clean outline, keep content, remove layout directives
  - validate_prompt():             pre-generation validation
  - validate_output():             post-generation validation
  - get_visual_direction():        get visual direction brief for label A/B/C

All collage image generation code MUST use this module.
DO NOT hardcode prompt rules in individual files.
"""

from __future__ import annotations

import logging
import os
import re
from fractions import Fraction
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Load spec once at module import time
_SPEC_PATH = Path(__file__).parent / "collage_prompt_spec.yaml"
with open(_SPEC_PATH, encoding="utf-8") as f:
    SPEC = yaml.safe_load(f)


def _build_grid_rules(total_pages: int, columns: int = 3) -> tuple[str, str]:
    """Render mandatory + layout grid rules in Chinese ━━━ format.

    Returns (mandatory_text, layout_text) — two formatted blocks.
    """
    rows = (total_pages + columns - 1) // columns
    canvas_ratio = Fraction(columns * 16, rows * 9)
    format_values = {
        "total_pages": total_pages,
        "rows": rows,
        "columns": columns,
        "canvas_ratio": f"{canvas_ratio.numerator}:{canvas_ratio.denominator}",
    }

    mandatory = "\n".join(
        f"{i}. {rule.format(**format_values)}"
        for i, rule in enumerate(SPEC["grid_rules"]["mandatory"], 1)
    )
    layout = "\n".join(
        f"{i}. {rule.format(**format_values)}"
        for i, rule in enumerate(SPEC["grid_rules"]["layout"], 1)
    )
    return mandatory, layout


def _build_negative_prompts() -> str:
    """Render negative prompts in ❌ format."""
    items = SPEC.get("negative_prompts", [])
    return "\n".join(f"❌ {item}" for item in items)


def get_visual_direction(label: str) -> str:
    """Get visual direction brief for label A/B/C."""
    direction = SPEC["visual_directions"].get(label.upper(), {})
    return direction.get("brief", "")


def get_generation_runtime() -> dict:
    """Return persisted collage runtime limits."""
    return dict(SPEC.get("generation_runtime") or {})


def get_style_system(style: str, default: str = "professional") -> str:
    """Return one persisted visual system by key."""
    systems = SPEC.get("style_systems", {})
    return str(systems.get(style) or systems.get(default) or "")


def get_variant_style_system(styles: list[str], variant: str) -> str:
    """Resolve A/B/C style selection while keeping rules in the YAML spec."""
    defaults = {"A": "professional", "B": "tech", "C": "minimal"}
    position = {"A": 0, "B": 1, "C": 2}.get(variant.upper(), 0)
    if position < len(styles):
        selected = styles[position]
    elif variant.upper() == "B":
        selected = "tech"
    elif variant.upper() == "C":
        selected = "creative"
    else:
        selected = defaults.get(variant.upper(), "professional")
    return get_style_system(selected, defaults.get(variant.upper(), "professional"))


def strip_visual_suggestions(text: str) -> str:
    """Remove visual-suggestion blocks while keeping ALL content.

    Uses patterns from the spec file. Strips layout directives like
    '**视觉建议**' and '**画面构思**' but keeps titles, core messages,
    bullet points, and narrative text.

    Returns cleaned text, trimmed to max_chars if needed.
    """
    for rule in SPEC["content_rules"]["strip_patterns"]:
        pattern = rule["pattern"]
        flags = 0
        if "DOTALL" in rule.get("flags", ""):
            flags |= re.DOTALL
        text = re.sub(pattern, "", text, flags=flags)

    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim
    max_chars = SPEC["content_rules"]["max_chars"]
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... content trimmed for length ...]"

    return text.strip()


def build_collage_prompt(
    *,
    total_pages: int,
    cleaned_outline: str,
    variant_label: str,
    project_context: str = "",
    columns: int = 3,
    visual_direction: str = "",
) -> str:
    """Build a complete collage prompt from the spec template.

    Args:
        total_pages:  number of slides in the deck
        cleaned_outline: outline with visual suggestions already stripped
        variant_label:  "A", "B", or "C"
        project_context: formatted project info (purpose, audience, etc.)
        columns: grid columns (default 3)

    Returns:
        Complete prompt string ready for image generation API.
    """
    rows = (total_pages + columns - 1) // columns
    grid_mandatory, grid_layout = _build_grid_rules(total_pages, columns)
    visual_direction = visual_direction.strip() or get_visual_direction(variant_label)

    template = SPEC["prompt_template"]
    negative_prompts = _build_negative_prompts()

    prompt = template.format(
        variant_label=variant_label,
        total_pages=total_pages,
        rows=rows,
        columns=columns,
        grid_rules_mandatory=grid_mandatory,
        grid_rules_layout=grid_layout,
        negative_prompts=negative_prompts,
        project_context=project_context or "应用场景：未指定\n目标受众：未指定\n视觉风格：专业严谨",
        cleaned_outline=cleaned_outline,
        visual_direction=visual_direction or "",
    )

    # Validate before returning
    errors = validate_prompt(prompt, total_pages, cleaned_outline)
    if errors:
        logger.warning("Collage prompt validation warnings: %s", errors)

    return prompt


def build_regen_prompt(
    *,
    total_pages: int,
    cleaned_outline: str,
    label: str,
    modifications: str,
    project_context: str = "",
    columns: int = 3,
    visual_direction: str = "",
) -> str:
    """Build a single-plan regeneration prompt with modifications."""
    rows = (total_pages + columns - 1) // columns
    grid_mandatory, grid_layout = _build_grid_rules(total_pages, columns)
    visual_direction = visual_direction.strip() or get_visual_direction(label)
    negative_prompts = _build_negative_prompts()

    template = SPEC["regen_template"]
    prompt = template.format(
        total_pages=total_pages,
        rows=rows,
        columns=columns,
        label=label,
        grid_rules_mandatory=grid_mandatory,
        grid_rules_layout=grid_layout,
        negative_prompts=negative_prompts,
        project_context=project_context or "应用场景：未指定\n目标受众：未指定\n视觉风格：专业严谨",
        modifications=modifications,
        cleaned_outline=cleaned_outline,
        visual_direction=visual_direction or "",
    )

    errors = validate_prompt(prompt, total_pages, cleaned_outline)
    if errors:
        logger.warning("Regen prompt validation warnings: %s", errors)

    return prompt


# ── Validation ────────────────────────────────────────────────────────────

def validate_prompt(prompt: str, total_pages: int, cleaned_outline: str) -> list[str]:
    """Pre-generation validation. Returns list of warning/error messages."""
    warnings = []
    for rule in SPEC["validation"]["pre_generation"]:
        check = rule["check"]
        error_msg = rule["error"]
        try:
            # Evaluate simple checks (safe subset of Python)
            if check == "total_pages > 0":
                if not (total_pages > 0):
                    warnings.append(error_msg)
            elif check == "len(cleaned_outline) > 50":
                if not (len(cleaned_outline) > 50):
                    warnings.append(f"{error_msg} (actual: {len(cleaned_outline)} chars)")
            elif check == "'强制约束' in prompt":
                if "强制约束" not in prompt:
                    warnings.append(error_msg)
            elif check == "'排版约束' in prompt":
                if "排版约束" not in prompt:
                    warnings.append(error_msg)
            elif check == "len(prompt) < 8000":
                if not (len(prompt) < 8000):
                    warnings.append(f"{error_msg} (actual: {len(prompt)} chars)")
        except Exception as exc:
            logger.warning("Validation check failed: %s — %s", check, exc)
    return warnings


def validate_output(output_path: str) -> list[str]:
    """Post-generation validation. Returns list of warning/error messages."""
    warnings = []
    for rule in SPEC["validation"]["post_generation"]:
        check = rule["check"]
        error_msg = rule["error"]
        try:
            if check == "os.path.exists(output_path)":
                if not os.path.exists(output_path):
                    warnings.append(error_msg)
            elif check == "os.path.getsize(output_path) > 1000":
                if os.path.exists(output_path) and os.path.getsize(output_path) <= 1000:
                    warnings.append(f"{error_msg} (actual: {os.path.getsize(output_path)} bytes)")
        except Exception as exc:
            logger.warning("Output validation failed: %s — %s", check, exc)
    return warnings
