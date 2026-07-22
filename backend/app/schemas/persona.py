from __future__ import annotations

from pydantic import BaseModel
from datetime import datetime


class PersonaBase(BaseModel):
    name: str
    slug: str
    description: str = ""
    avatar_url: str = ""
    voice_id: str = "zh-CN-YunxiNeural"
    system_prompt_template: str = ""
    config_json: dict = {}


class PersonaCreate(PersonaBase):
    pass


class PersonaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    avatar_url: str | None = None
    voice_id: str | None = None
    system_prompt_template: str | None = None
    config_json: dict | None = None


class PersonaRead(PersonaBase):
    id: str
    is_active: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
