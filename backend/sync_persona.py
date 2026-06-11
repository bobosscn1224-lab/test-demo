"""Sync persona from YAML to database."""
import asyncio
import yaml
from sqlalchemy import select
from app.core.database import async_session
from app.models.persona import Persona


async def sync():
    # Load YAML
    with open("personas/default.yaml", "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)

    async with async_session() as db:
        result = await db.execute(select(Persona).where(Persona.slug == "default"))
        persona = result.scalar_one_or_none()

        if not persona:
            print("Persona not found in DB!")
            return

        # Update template and config from YAML
        persona.system_prompt_template = yaml_data["system_prompt_template"]
        persona.config_json = yaml_data.get("config", {})
        persona.name = yaml_data["name"]
        persona.description = yaml_data.get("description", "")

        await db.commit()
        await db.refresh(persona)
        print("Persona synced successfully!")
        print(f"  Template length: {len(persona.system_prompt_template)} chars")
        print(f"  Config keys: {list(persona.config_json.keys())}")
        print(f"  max_response_length: {persona.config_json.get('max_response_length')}")
        print(f"  speaking_style preview: {persona.config_json.get('speaking_style', '')[:100]}...")

        # Verify critical phrases exist
        checks = ["回复应充分展开", "至少500字", "knowledge_scope"]
        for c in checks:
            found = c in persona.system_prompt_template or c in str(persona.config_json)
            print(f"  Check '{c}': {'FOUND' if found else 'MISSING'}")


if __name__ == "__main__":
    asyncio.run(sync())
