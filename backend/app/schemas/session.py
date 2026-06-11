from pydantic import BaseModel
from datetime import datetime


class SessionCreate(BaseModel):
    title: str = "新对话"
    persona_id: str | None = None


class SessionRead(BaseModel):
    id: str
    title: str
    persona_id: str | None = None
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionUpdate(BaseModel):
    title: str | None = None
    is_archived: bool | None = None


class MessageRead(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    audio_path: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionDetail(SessionRead):
    messages: list[MessageRead] = []
