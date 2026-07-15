import os
import re
import json
import asyncio
import logging
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService
from app.services.llm_service import llm_service
from app.services.persona_service import PersonaService, build_system_prompt
from app.services.rag_service import rag_service
from app.skills import find_skill, find_skill_by_name, SkillContext, SkillResult
from app.utils.file_parser import parse_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def upload_status_message(skill_name: str, session_id: str | None) -> str:
    if skill_name == "ppt_maker" and session_id:
        try:
            from app.skills.ppt_maker.handler import _sessions as ppt_sessions

            stage = (ppt_sessions.get(session_id) or {}).get("stage")
        except Exception:
            stage = None
        if stage == "awaiting_collage_for_pages":
            return "正在接收 PPT 整体缩略图，准备进入第 3 步生成分页高清风格图，请稍候...\n\n"
        if stage == "awaiting_page_image_for_editable_ppt":
            return "正在接收单页高清 PPT 风格图，准备进入第 4 步制作可下载 PPTX，请稍候...\n\n"
        if stage == "awaiting_outline_for_visual":
            return "正在读取你提供的 PPT 大纲，准备进入第 2 步生成三版缩略图，请稍候...\n\n"
        if stage == "awaiting_content":
            return "正在读取上传资料，准备生成 PPT 大纲，请稍候...\n\n"
        return "正在处理上传文件并继续当前 PPT 制作流程，请稍候...\n\n"
    return "正在读取上传文件并处理，请稍候...\n\n"


async def stream_skill_events(skill, context: SkillContext, sid: str):
    """Stream skill progress tokens and final skill result."""
    try:
        if hasattr(skill, "execute_stream"):
            async for item in skill.execute_stream(context):
                if isinstance(item, SkillResult):
                    event = json.dumps({
                        "type": "skill",
                        "skill": skill.name,
                        "session_id": sid,
                        "success": item.success,
                        "message": item.message,
                        "data": item.data,
                        "follow_up_action": item.follow_up_action,
                    }, ensure_ascii=False)
                    yield f"data: {event}\n\n"
                else:
                    event = json.dumps({"type": "token", "data": str(item)}, ensure_ascii=False)
                    yield f"data: {event}\n\n"
            return

        result = await skill.execute(context)
        event = json.dumps({
            "type": "skill",
            "skill": skill.name,
            "session_id": sid,
            "success": result.success,
            "message": result.message,
            "data": result.data,
            "follow_up_action": result.follow_up_action,
        }, ensure_ascii=False)
        yield f"data: {event}\n\n"
    except Exception as exc:
        logger.exception("Skill execution failed: %s", getattr(skill, "name", "unknown"))
        event = json.dumps({
            "type": "skill",
            "skill": getattr(skill, "name", "unknown"),
            "session_id": sid,
            "success": False,
            "message": f"技能执行出错了：{exc}",
            "data": {"stage": "error"},
            "follow_up_action": None,
        }, ensure_ascii=False)
        yield f"data: {event}\n\n"

# Patterns that suggest the user is correcting a previous answer
_CORRECTION_HINTS = [
    r"不对",
    r"错了",
    r"说错了",
    r"回答错了",
    r"搞错了",
    r"弄错了",
    r"应该是",
    r"纠正",
    r"校正",
    r"改正",
    r"不是.*而是",
]


def _looks_like_correction(message: str) -> bool:
    msg = message.strip()
    if len(msg) > 200:
        return False
    return any(re.search(p, msg) for p in _CORRECTION_HINTS)


async def _detect_and_store_correction(
    message: str, session_id: str, db: AsyncSession
) -> dict | None:
    """Use LLM to extract original question + correct answer from a correction message."""
    if not session_id or not _looks_like_correction(message):
        return None

    from app.models.chat import ChatMessage

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(8)
    )
    messages = list(result.scalars().all())
    messages.reverse()

    if len(messages) < 2:
        return None

    context_lines = []
    for m in messages[-8:]:
        role = "用户" if m.role == "user" else "助手"
        context_lines.append(f"{role}: {m.content[:300]}")
    context = "\n".join(context_lines)

    prompt = f"""判断用户最新消息是否在纠正助手之前的回答。如果是，提取被纠正的原始问题和正确答案。

对话历史：
{context}

用户最新消息：{message}

只返回严格 JSON，不要带 markdown：
如果是纠正：{{"is_correction": true, "question": "原始问题", "correct_answer": "正确答案"}}
如果不是纠正：{{"is_correction": false, "question": null, "correct_answer": null}}"""

    try:
        response = await llm_service.chat(
            system_prompt="你是一个对话分析助手。只返回严格 JSON 格式的结果。",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        data = json.loads(text)
        if data.get("is_correction") and data.get("question") and data.get("correct_answer"):
            cid = await rag_service.add_correction(
                question=data["question"],
                correct_answer=data["correct_answer"],
                source="chat_auto",
            )
            logger.info("Auto-correction stored: %s 鈫?%s", data["question"][:60], data["correct_answer"][:60])
            return {"id": cid, "question": data["question"], "correct_answer": data["correct_answer"]}
    except Exception:
        logger.warning("Correction detection failed", exc_info=True)

    return None


async def sse_generator(
    chat_svc: ChatService,
    message: str,
    session_id: str | None,
    persona_slug: str | None,
    mode: str = "enhanced",
    extra_context: str = "",
):
    knowledge_context = ""
    try:
        knowledge_context = await rag_service.search(message)
        if knowledge_context:
            logger.info("RAG context retrieved for chat (%d chars)", len(knowledge_context))
    except Exception:
        logger.warning("RAG search failed, continuing without knowledge context", exc_info=True)

    if extra_context:
        knowledge_context = f"{extra_context}\n\n{knowledge_context}".strip()

    async for event_json in chat_svc.stream_response(
        user_message=message,
        session_id=session_id,
        persona_slug=persona_slug,
        knowledge_context=knowledge_context,
        mode=mode,
    ):
        yield f"data: {event_json}\n\n"


@router.post("/stream")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    # Check for ongoing multi-turn skill sessions — restore from DB first
    # (in-memory _sessions is cleared on server restart, but DB persists)
    skill = None
    if req.session_id:
        # Restore each skill's sessions from DB before checking in-memory state
        from app.skills.weekly_report.handler import _sessions, _helper as wr_helper
        await wr_helper.restore()
        if req.session_id in _sessions:
            skill = find_skill_by_name("weekly_report")

        if not skill:
            from app.skills.ppt_maker_v2.handler import _sessions as ppt_sessions, _helper as ppt_helper
            await ppt_helper.restore()
            if req.session_id in ppt_sessions:
                skill = find_skill_by_name("ppt_maker")

        if not skill:
            from app.skills.feishu_doc_reader.handler import _sessions as feishu_doc_sessions, _helper as feishu_helper
            await feishu_helper.restore()
            if req.session_id in feishu_doc_sessions:
                skill = find_skill_by_name("feishu_doc_reader")

        if not skill:
            from app.skills.image_gen import _sessions as img_sessions, _helper as img_helper
            await img_helper.restore()
            if req.session_id in img_sessions:
                skill = find_skill_by_name("image_gen")

    # Check for skill trigger
    if not skill:
        skill = find_skill(req.message)

    if skill and skill.triggers:  # Only auto-trigger skills with triggers
        async def skill_sse():
            # Use existing session_id or generate one for multi-turn skill flows
            sid = req.session_id or str(__import__("uuid").uuid4())
            context = SkillContext(
                db=db,
                user_message=req.message,
                session_id=sid,
                persona_slug=req.persona_slug,
            )
            async for event in stream_skill_events(skill, context, sid):
                yield event

        return StreamingResponse(
            skill_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # Correction detection runs in background 鈥?don't block chat
    if _looks_like_correction(req.message) and req.session_id:
        asyncio.create_task(_detect_and_store_correction(req.message, req.session_id, db))

    # Normal chat
    chat_svc = ChatService(db)
    return StreamingResponse(
        sse_generator(chat_svc, req.message, req.session_id, req.persona_slug, req.mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/upload-and-chat")
async def upload_and_chat(
    message: str = Form(...),
    session_id: str | None = Form(None),
    persona_slug: str | None = Form(None),
    mode: str = Form("enhanced"),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    uploaded_files = []
    upload_dir = os.path.join("data", "uploads", "chat")
    upload_root = os.path.abspath(upload_dir)
    os.makedirs(upload_root, exist_ok=True)

    incoming_files: list[UploadFile] = []
    if file:
        incoming_files.append(file)
    if files:
        incoming_files.extend(files)

    for upload in incoming_files:
        safe_name = os.path.basename(upload.filename or "upload")
        if not safe_name or safe_name in {".", ".."}:
            safe_name = "upload"
        stored_name = f"{uuid.uuid4().hex}_{safe_name}"
        file_path = os.path.abspath(os.path.join(upload_root, stored_name))
        if os.path.commonpath([upload_root, file_path]) != upload_root:
            raise HTTPException(status_code=400, detail="Invalid filename")

        content = await upload.read()
        with open(file_path, "wb") as f:
            f.write(content)

        uploaded_files.append({
            "filename": upload.filename,
            "path": file_path,
            "content_type": upload.content_type,
        })

    # Check skill — restore from DB first (survives server restart)
    skill = None
    if session_id:
        from app.skills.weekly_report.handler import _sessions, _helper as wr_helper
        await wr_helper.restore()
        if session_id in _sessions:
            skill = find_skill_by_name("weekly_report")
        if not skill:
            from app.skills.ppt_maker_v2.handler import _sessions as ppt_sessions, _helper as ppt_helper
            await ppt_helper.restore()
            if session_id in ppt_sessions:
                skill = find_skill_by_name("ppt_maker")
    if not skill:
        skill = find_skill(message)
    if not skill and uploaded_files and any(k in message for k in ("入口3", "第3步", "缩略图", "分页高清")):
        sid = session_id or str(uuid.uuid4())
        from app.skills.ppt_maker.handler import _sessions as ppt_sessions
        ppt_sessions[sid] = {"stage": "awaiting_collage_for_pages", "entry_choice": "3"}
        session_id = sid
        skill = find_skill_by_name("ppt_maker")
    if not skill and uploaded_files and any(k in message for k in ("入口4", "第4步", "可编辑PPT", "可编辑 PPT", "单页高清")):
        sid = session_id or str(uuid.uuid4())
        from app.skills.ppt_maker.handler import _sessions as ppt_sessions
        ppt_sessions[sid] = {"stage": "awaiting_page_image_for_editable_ppt", "entry_choice": "4"}
        session_id = sid
        skill = find_skill_by_name("ppt_maker")
    if skill and skill.triggers and uploaded_files:
        async def skill_sse():
            sid = session_id or str(uuid.uuid4())
            status = json.dumps({
                "type": "token",
                "data": upload_status_message(skill.name, sid),
            }, ensure_ascii=False)
            yield f"data: {status}\n\n"
            context = SkillContext(
                db=db,
                user_message=message,
                session_id=sid,
                persona_slug=persona_slug,
                uploaded_files=uploaded_files,
            )
            async for event in stream_skill_events(skill, context, sid):
                yield event

        return StreamingResponse(
            skill_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    file_context_parts: list[str] = []
    for uploaded in uploaded_files:
        file_path = uploaded["path"]
        filename = uploaded.get("filename") or os.path.basename(file_path)
        try:
            parsed_text = await parse_file(file_path)
        except Exception:
            parsed_text = None
            logger.warning("Failed to parse uploaded chat file: %s", file_path, exc_info=True)

        if parsed_text:
            excerpt = parsed_text[:30000]
            if len(parsed_text) > len(excerpt):
                excerpt += "\n[内容已截断，仅展示前 30000 字符]"
            file_context_parts.append(
                f"上传文件：{filename}\n文件内容：\n{excerpt}"
            )
        else:
            file_context_parts.append(
                f"上传文件：{filename}\n文件内容：系统暂时无法从该文件中提取文本。"
            )

    file_context = ""
    if file_context_parts:
        file_context = "用户上传的文件内容如下，请优先参考这些材料回答：\n\n" + "\n\n---\n\n".join(file_context_parts)

    # Fall back to normal chat
    chat_svc = ChatService(db)
    return StreamingResponse(
        sse_generator(chat_svc, message, session_id, persona_slug, mode, file_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/message", response_model=ChatResponse)
async def chat_message(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    persona_svc = PersonaService(db)
    persona = None
    if req.persona_slug:
        persona = await persona_svc.get_by_slug(req.persona_slug)
    if not persona:
        persona = await persona_svc.get_active()
    if not persona:
        persona = await persona_svc.seed_default()

    knowledge_context = ""
    try:
        knowledge_context = await rag_service.search(req.message)
    except Exception:
        pass
    system_prompt = build_system_prompt(persona, knowledge_context=knowledge_context)
    messages = [{"role": "user", "content": req.message}]

    response = await llm_service.chat(system_prompt=system_prompt, messages=messages)
    reply = ""
    if response.content:
        for block in response.content:
            if hasattr(block, "text"):
                reply = block.text
                break

    from app.models.chat import ChatSession, ChatMessage
    import uuid

    session = ChatSession(
        id=str(uuid.uuid4()),
        title=req.message[:50],
        persona_id=persona.id,
    )
    db.add(session)
    db.add(ChatMessage(id=str(uuid.uuid4()), session_id=session.id, role="user", content=req.message))
    db.add(ChatMessage(id=str(uuid.uuid4()), session_id=session.id, role="assistant", content=reply,
                       tokens_in=response.usage.input_tokens if response.usage else None,
                       tokens_out=response.usage.output_tokens if response.usage else None))
    await db.commit()

    return ChatResponse(
        session_id=session.id,
        reply=reply,
        tokens_in=response.usage.input_tokens if response.usage else None,
        tokens_out=response.usage.output_tokens if response.usage else None,
    )
