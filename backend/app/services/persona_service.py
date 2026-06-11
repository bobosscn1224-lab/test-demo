from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.persona import Persona
from app.core.prompts import load_persona_yaml, render_system_prompt


class PersonaService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active(self) -> Persona | None:
        result = await self.db.execute(select(Persona).where(Persona.is_active == True))
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Persona | None:
        result = await self.db.execute(select(Persona).where(Persona.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_id(self, persona_id: str) -> Persona | None:
        result = await self.db.execute(select(Persona).where(Persona.id == persona_id))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Persona]:
        result = await self.db.execute(select(Persona).order_by(Persona.created_at.desc()))
        return list(result.scalars().all())

    async def create(self, data: dict) -> Persona:
        persona = Persona(**data)
        self.db.add(persona)
        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def update(self, persona: Persona, data: dict) -> Persona:
        for key, value in data.items():
            if value is not None:
                setattr(persona, key, value)
        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def set_active(self, persona: Persona) -> Persona:
        # Deactivate all
        all_personas = await self.list_all()
        for p in all_personas:
            p.is_active = False
        persona.is_active = True
        await self.db.commit()
        await self.db.refresh(persona)
        return persona

    async def seed_default(self) -> Persona:
        existing = await self.get_by_slug("default")
        if existing:
            return existing
        yaml_data = load_persona_yaml("default")
        persona = Persona(
            slug=yaml_data["slug"],
            name=yaml_data["name"],
            description=yaml_data.get("description", ""),
            voice_id=yaml_data.get("voice_id", "zh-CN-YunxiNeural"),
            system_prompt_template=yaml_data["system_prompt_template"],
            config_json=yaml_data.get("config", {}),
            is_active=True,
        )
        self.db.add(persona)
        await self.db.commit()
        await self.db.refresh(persona)
        return persona


def build_system_prompt(
    persona: Persona,
    knowledge_context: str = "",
    user_profile: str = "",
    mode: str = "enhanced",
) -> str:
    data = {
        "name": persona.name,
        "system_prompt_template": persona.system_prompt_template,
        "config": persona.config_json,
    }
    return render_system_prompt(data, knowledge_context, user_profile, mode)
