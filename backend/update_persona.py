"""Update the default persona template in DB from yaml file."""
import sys; sys.path.insert(0, r'd:\数字分身\backend')
import asyncio
from app.core.database import engine, Base
from app.core.prompts import load_persona_yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

async def main():
    yaml_data = load_persona_yaml("default")
    new_template = yaml_data["system_prompt_template"]

    async with AsyncSession(engine) as db:
        # Update persona with slug='default'
        result = await db.execute(text(
            "UPDATE personas SET system_prompt_template = :t WHERE slug = 'default'"
        ), {"t": new_template})
        await db.commit()
        print(f"Updated {result.rowcount} persona(s) with new template")

        # Verify
        result = await db.execute(text("SELECT slug, length(system_prompt_template) FROM personas WHERE slug='default'"))
        row = result.fetchone()
        if row:
            print(f"  slug={row[0]}, template_length={row[1]}")
        else:
            print("  No persona found, will be seeded on next startup")

asyncio.run(main())
