import json
import uuid
import asyncio
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.chat import ChatSession, ChatMessage
from app.models.persona import Persona
from app.services.llm_service import llm_service
from app.services.persona_service import PersonaService, build_system_prompt
from app.services.user_profile_service import UserProfileService, extract_user_info_from_message


def gen_uuid():
    return str(uuid.uuid4())


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.persona_svc = PersonaService(db)
        self.profile_svc = UserProfileService(db)

    async def _get_or_create_session(self, session_id: str | None, persona: Persona | None = None) -> ChatSession:
        if session_id:
            result = await self.db.execute(select(ChatSession).where(ChatSession.id == session_id))
            session = result.scalar_one_or_none()
            if session:
                return session
        session = ChatSession(
            id=gen_uuid(),
            title="新对话",
            persona_id=persona.id if persona else None,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def _get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return [{"role": m.role, "content": m.content} for m in messages]

    async def stream_response(
        self,
        user_message: str,
        session_id: str | None = None,
        persona_slug: str | None = None,
        knowledge_context: str = "",
        mode: str = "enhanced",
    ) -> AsyncGenerator[str, None]:
        # Load persona
        persona = None
        if persona_slug:
            persona = await self.persona_svc.get_by_slug(persona_slug)
        if not persona:
            persona = await self.persona_svc.get_active()
        if not persona:
            persona = await self.persona_svc.seed_default()

        # Get or create session
        session = await self._get_or_create_session(session_id, persona)

        # Auto-title
        if session.title == "新对话":
            session.title = user_message[:50] + ("..." if len(user_message) > 50 else "")

        # Save user message
        user_msg = ChatMessage(
            id=gen_uuid(),
            session_id=session.id,
            role="user",
            content=user_message,
        )
        self.db.add(user_msg)
        await self.db.commit()

        # Build context: persona + user profile + knowledge
        user_profile_summary = await self.profile_svc.get_profile_summary()
        system_prompt = build_system_prompt(
            persona,
            knowledge_context=knowledge_context,
            user_profile=user_profile_summary,
            mode=mode,
        )

        history = await self._get_history(session.id, limit=40)
        messages = history

        # Stream from DeepSeek
        full_reply = ""
        tokens_in = None
        tokens_out = None

        try:
            mt = persona.config_json.get("max_response_length", 32768)
            print(f"[CHAT] max_tokens={mt} from persona.config_json")
            async for token in llm_service.stream_chat(
                system_prompt=system_prompt,
                messages=messages,
                temperature=persona.config_json.get("temperature", 0.7),
                max_tokens=mt,
                thinking={"type": "disabled"},
            ):
                full_reply += token
                yield json.dumps({"type": "token", "data": token}, ensure_ascii=False)
        except Exception as e:
            yield json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False)
            return

        # Save assistant message
        assistant_msg = ChatMessage(
            id=gen_uuid(),
            session_id=session.id,
            role="assistant",
            content=full_reply,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self.db.add(assistant_msg)
        await self.db.commit()

        # Background: extract user info from this conversation
        asyncio.create_task(extract_user_info_from_message(user_message, full_reply, self.db))

        # Send done event
        yield json.dumps(
            {"type": "done", "data": {"session_id": session.id, "tokens_in": tokens_in, "tokens_out": tokens_out}},
            ensure_ascii=False,
        )
