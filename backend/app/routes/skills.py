import os
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.skills import find_skill, SkillContext
from app.models.skill import SkillExecution

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("/list")
async def list_skills():
    from app.skills import get_all
    skills = get_all()
    visible = [s for s in skills if s.triggers]  # Only show user-triggerable skills
    return [
        {
            "name": s.name,
            "description": s.description,
            "triggers": s.triggers,
            "keywords": getattr(s, "keywords", []),
        }
        for s in visible
    ]


@router.post("/trigger")
async def trigger_skill(
    message: str = Form(...),
    session_id: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    skill = find_skill(message)
    if not skill:
        return {"handled": False, "message": "没有匹配的技能，将作为普通对话处理"}

    # Save uploaded file if any
    uploaded_files = []
    if file:
        upload_dir = os.path.join("data", "uploads", "skills")
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, file.filename or "upload")
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        uploaded_files.append({
            "filename": file.filename,
            "path": file_path,
            "content_type": file.content_type,
        })

    context = SkillContext(
        db=db,
        user_message=message,
        session_id=session_id,
        uploaded_files=uploaded_files,
    )

    result = await skill.execute(context)

    # Record execution
    execution = SkillExecution(
        skill_name=skill.name,
        session_id=session_id,
        trigger_message=message,
        result_data={"success": result.success, "message": result.message, "data": result.data},
        status="success" if result.success else "error",
    )
    db.add(execution)
    await db.commit()

    return {
        "handled": True,
        "skill": skill.name,
        "success": result.success,
        "message": result.message,
        "data": result.data,
        "follow_up_action": result.follow_up_action,
    }


@router.get("/download/{filename}")
async def download_skill_output(filename: str):
    output_dir = os.path.join("data", "outputs")
    file_path = os.path.join(output_dir, filename)
    if not os.path.exists(file_path):
        return {"error": "File not found"}
    return FileResponse(file_path, filename=filename)
