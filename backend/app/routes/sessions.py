from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.chat import ChatSession, ChatMessage
from app.schemas.session import SessionCreate, SessionRead, SessionUpdate, SessionDetail, MessageRead
from app.utils.sensitive_data import redact_sensitive_text

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionRead])
async def list_sessions(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.is_archived == False)
        .order_by(ChatSession.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [
        SessionRead(
            id=session.id,
            title=redact_sensitive_text(session.title),
            persona_id=session.persona_id,
            is_archived=session.is_archived,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )
        for session in result.scalars().all()
    ]


@router.post("", response_model=SessionRead)
async def create_session(data: SessionCreate, db: AsyncSession = Depends(get_db)):
    payload = data.model_dump()
    payload["title"] = redact_sensitive_text(payload["title"])
    session = ChatSession(**payload)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    )
    messages = list(msg_result.scalars().all())

    return SessionDetail(
        id=session.id,
        title=redact_sensitive_text(session.title),
        persona_id=session.persona_id,
        is_archived=session.is_archived,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[MessageRead.model_validate(m) for m in messages],
    )


@router.patch("/{session_id}", response_model=SessionRead)
async def update_session(session_id: str, data: SessionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    for key, value in data.model_dump(exclude_none=True).items():
        if key == "title":
            value = redact_sensitive_text(value)
        setattr(session, key, value)
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session)
    await db.commit()
    return {"ok": True}
