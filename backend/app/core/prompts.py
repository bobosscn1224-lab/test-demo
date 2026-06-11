import os
import yaml
from jinja2 import Template
from app.config import settings


def load_persona_yaml(slug: str | None = None) -> dict:
    slug = slug or settings.active_persona
    persona_path = os.path.join(settings.personas_dir, f"{slug}.yaml")
    if not os.path.exists(persona_path):
        raise FileNotFoundError(f"Persona file not found: {persona_path}")
    with open(persona_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_system_prompt(
    persona: dict,
    knowledge_context: str = "",
    user_profile: str = "",
    mode: str = "enhanced",
) -> str:
    template = Template(persona["system_prompt_template"])
    config = persona.get("config", {})
    return template.render(
        name=persona["name"],
        bio=config.get("bio", ""),
        expertise=config.get("expertise", []),
        personality_traits=config.get("personality_traits", []),
        speaking_style=config.get("speaking_style", "自然、友好"),
        knowledge_scope=config.get("knowledge_scope", "通用知识"),
        knowledge_context=knowledge_context,
        user_profile=user_profile,
        mode=mode,
    )


def get_system_prompt(
    slug: str | None = None,
    knowledge_context: str = "",
    user_profile: str = "",
    mode: str = "enhanced",
) -> str:
    persona = load_persona_yaml(slug)
    return render_system_prompt(persona, knowledge_context, user_profile, mode)
