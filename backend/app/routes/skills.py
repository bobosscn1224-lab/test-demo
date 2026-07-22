from __future__ import annotations

import os
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.skills import find_skill, SkillContext
from app.models.skill import SkillExecution
from app.services._paths import PUBLIC_DIR, UPLOADS_DIR, WEEKLY_REPORT_DIR

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
        safe_name = os.path.basename(file.filename or "upload") or "upload"
        file_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}_{safe_name}")
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


@router.get("/download/{file_path:path}")
async def download_skill_output(file_path: str):
    """Download a skill output file. Supports both flat files and subdirectories."""
    import urllib.parse
    # Decode URL-encoded path
    file_path = urllib.parse.unquote(file_path)
    output_dir = PUBLIC_DIR.resolve()
    full_path = (output_dir / file_path).resolve()
    try:
        full_path.relative_to(output_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not full_path.is_file():
        # Also try looking for the file directly in data/outputs/
        fallback = (output_dir / os.path.basename(file_path)).resolve()
        if fallback.is_file():
            full_path = fallback
        else:
            report_fallback = (WEEKLY_REPORT_DIR.resolve() / os.path.basename(file_path)).resolve()
            if report_fallback.is_file():
                full_path = report_fallback
            else:
                raise HTTPException(status_code=404, detail=f"File not found: {os.path.basename(file_path)}")
    ext = full_path.suffix.lower()
    media_map = {
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".md": "text/markdown; charset=utf-8",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
        ".svg": "image/svg+xml",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    filename = full_path.name
    return FileResponse(str(full_path), filename=filename, media_type=media_type)


# ══════════════════════════════════════════════════════════════════
# Legacy batch endpoints — DEPRECATED, use /api/v1/pptx/* instead
# These are kept for backward compatibility only.
# ══════════════════════════════════════════════════════════════════

@router.post("/batch-pptx", deprecated=True)
async def batch_convert_images(data: dict):
    """[DEPRECATED] Use POST /api/v1/pptx/convert-async instead."""
    from app.services.batch_pptx_service import PIPELINE_VERSION, batch_convert

    images = data.get("images", [])
    if not images or len(images) < 1:
        return {"error": "At least 1 image required"}

    output_dir = str(PUBLIC_DIR)

    result = await batch_convert(images, output_dir=output_dir)
    result["pipelines_version"] = PIPELINE_VERSION
    return result


@router.post("/batch-pptx-async", deprecated=True)
async def batch_convert_async(data: dict):
    """[DEPRECATED] Use POST /api/v1/pptx/convert-async instead."""
    from app.services.batch_job_manager import create_job

    images = data.get("images", [])
    if not images or len(images) < 1:
        return {"error": "At least 1 image required"}

    output_dir = str(PUBLIC_DIR)

    job_id = create_job(images, output_dir)
    return {"job_id": job_id, "status": "queued", "total": len(images)}


@router.get("/batch-status/{job_id}", deprecated=True)
async def batch_job_status(job_id: str):
    """[DEPRECATED] Use GET /api/v1/pptx/jobs/{job_id} instead."""
    from app.services.batch_job_manager import get_job

    job = get_job(job_id)
    if not job:
        return {"error": "Job not found"}
    return job
