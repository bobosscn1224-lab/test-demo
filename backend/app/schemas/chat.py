from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    persona_slug: str | None = None
    mode: str = "enhanced"  # "kb_only" | "enhanced"


class ChatStreamEvent(BaseModel):
    type: str  # "token" | "done" | "error"
    data: str


class ChatDoneData(BaseModel):
    session_id: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    tokens_in: int | None = None
    tokens_out: int | None = None
