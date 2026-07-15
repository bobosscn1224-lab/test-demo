"""PPT Maker Feature API — Project CRUD (JSON file store)."""

from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.services._paths import DATA_DIR
from app.api.ppt_maker.models import (
    Project, ProjectCreate, ProjectUpdate, ContentAdd,
    VALID_STATUSES, PURPOSE_MAP, AUDIENCE_MAP, SCALE_MAP, STYLE_MAP,
)

def _normalize(project_data: dict) -> dict:
    """Normalize Chinese labels to English canonical keys."""
    if project_data.get("purpose"):
        project_data["purpose"] = PURPOSE_MAP.get(project_data["purpose"], project_data["purpose"])
    if project_data.get("audience"):
        project_data["audience"] = AUDIENCE_MAP.get(project_data["audience"], project_data["audience"])
    if project_data.get("scale"):
        project_data["scale"] = SCALE_MAP.get(project_data["scale"], project_data["scale"])
    if project_data.get("styles"):
        project_data["styles"] = [STYLE_MAP.get(s, s) for s in project_data["styles"]]
    return project_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["ppt-maker"], redirect_slashes=False)

PROJECTS_DIR = DATA_DIR / "ppt_projects"


def _ensure_dir() -> None:
    """Create projects directory if it doesn't exist."""
    os.makedirs(str(PROJECTS_DIR), exist_ok=True)


def _file_path(project_id: str) -> str:
    """Get the JSON file path for a project ID."""
    return str(PROJECTS_DIR / f"{project_id}.json")


def _load(project_id: str) -> dict:
    """Load a project from its JSON file. Raises FileNotFoundError if missing."""
    path = _file_path(project_id)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Project '{project_id}' not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(project_id: str, data: dict) -> None:
    """Save a project dict to its JSON file."""
    _ensure_dir()
    path = _file_path(project_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _generate_id() -> str:
    """Generate a short 8-character hex project ID."""
    return secrets.token_hex(4)


def _now() -> str:
    """ISO-format current UTC timestamp."""
    return datetime.utcnow().isoformat() + "Z"


def _to_project(data: dict) -> Project:
    """Convert raw dict to Project model. Separates outline_pages from page_images.

    New format: outline_pages (structured outline) and page_images (generated images)
    are separate fields. Legacy projects had both mixed in 'pages'.
    """
    outline_text = data.get("outline", "")

    # ── Collages: enrich with download_url ──
    collages = []
    for c in data.get("collages", []):
        c = dict(c)
        if not c.get("download_url") and c.get("filename"):
            c["download_url"] = f"/api/skills/download/{c['filename']}"
        collages.append(c)

    # ── Outline pages: new field first, fallback to legacy 'pages' ──
    outline_pages = list(data.get("outline_pages", []))
    if not outline_pages:
        # Migration from legacy: pick entries with type/points from old 'pages'
        legacy = data.get("pages", [])
        outline_pages = [dict(p) for p in legacy if isinstance(p, dict) and (p.get("type") or p.get("points"))]
    if not outline_pages and outline_text:
        # Last resort: parse from raw outline text
        try:
            from app.api.ppt_maker.outline import _parse_outline
            outline_pages = [p.model_dump() for p in _parse_outline(outline_text)]
        except Exception:
            pass

    # ── Page images: new field first, fallback to legacy 'pages' ──
    page_images = list(data.get("page_images", []))
    if not page_images:
        legacy = data.get("pages", [])
        page_images = [dict(p) for p in legacy if isinstance(p, dict) and p.get("filename") and not p.get("type")]
    for p in page_images:
        if not p.get("download_url") and p.get("filename"):
            p["download_url"] = f"/api/skills/download/{p['filename']}"
        if not p.get("page_num") and p.get("index"):
            p["page_num"] = p["index"]

    # ── Legacy pages: keep for backward compat, but don't mix ──
    legacy_pages = data.get("pages", [])

    return Project(
        id=data.get("id", ""),
        name=data.get("name", ""),
        purpose=data.get("purpose", ""),
        audience=data.get("audience", ""),
        scale=data.get("scale", ""),
        styles=data.get("styles", []),
        key_message=data.get("key_message", ""),
        narrative_style=data.get("narrative_style", "auto"),
        narrative_framework=data.get("narrative_framework", "auto"),
        objective=data.get("objective", "auto"),
        tone=data.get("tone", "auto"),
        status=data.get("status", "created"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        outline=outline_text,
        selected_collage=data.get("selected_collage", ""),
        image_backend=data.get("image_backend", ""),
        content_text=data.get("content_text", ""),
        content_files=data.get("content_files", []),
        outline_pages=outline_pages,
        collages=collages,
        page_images=page_images,
        pages=legacy_pages,
    )


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/", response_model=Project)
async def create_project(data: ProjectCreate) -> Project:
    """Create a new PPT project."""
    project_id = _generate_id()
    now = _now()
    record = {
        "id": project_id,
        "name": data.name,
        "purpose": data.purpose,
        "audience": data.audience,
        "scale": data.scale,
        "styles": data.styles,
        "key_message": data.key_message,
        "narrative_style": data.narrative_style,
        "narrative_framework": data.narrative_framework,
        "objective": data.objective,
        "tone": data.tone,
        "status": "created",
        "created_at": now,
        "updated_at": now,
        "outline": "",
        "selected_collage": "",
        "image_backend": "",
        "content_text": "",
        "content_files": [],
        "outline_pages": [],
        "collages": [],
        "page_images": [],
        "pages": [],
    }
    record = _normalize(record)
    _save(project_id, record)
    logger.info("Created project %s: %s", project_id, data.name)
    return _to_project(record)


@router.get("/", response_model=list[Project])
async def list_projects() -> list[Project]:
    """List all PPT projects, newest first."""
    _ensure_dir()
    results: list[Project] = []
    try:
        for filename in sorted(os.listdir(str(PROJECTS_DIR)), reverse=True):
            if not filename.endswith(".json"):
                continue
            project_id = filename[:-5]  # strip .json
            try:
                record = _load(project_id)
                results.append(_to_project(record))
            except Exception:
                logger.warning("Failed to load project %s", project_id, exc_info=True)
    except FileNotFoundError:
        pass
    return results


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str) -> Project:
    """Get a single project by ID."""
    try:
        record = _load(project_id)
        return _to_project(record)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")


@router.put("/{project_id}", response_model=Project)
async def update_project(project_id: str, data: ProjectUpdate) -> Project:
    """Update project metadata (name, purpose, etc.)."""
    try:
        record = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    update_fields = data.model_dump(exclude_unset=True)
    for key, value in update_fields.items():
        if value is not None:
            record[key] = value
    record = _normalize(record)
    record["updated_at"] = _now()
    _save(project_id, record)
    return _to_project(record)


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> dict:
    """Delete a project and its JSON file."""
    path = _file_path(project_id)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    os.remove(path)
    logger.info("Deleted project %s", project_id)
    return {"success": True, "project_id": project_id}


@router.post("/{project_id}/content", response_model=Project)
async def add_content(project_id: str, data: ContentAdd) -> Project:
    """Add content to a project (text, file refs, or feishu reference)."""
    try:
        record = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    if data.text:
        if record.get("content_text"):
            record["content_text"] += "\n\n" + data.text
        else:
            record["content_text"] = data.text

    if data.files:
        existing = list(record.get("content_files", []))
        existing.extend(data.files)
        record["content_files"] = existing

    if data.feishu_ref:
        existing = list(record.get("content_files", []))
        existing.append({"type": "feishu", "ref": data.feishu_ref})
        record["content_files"] = existing

    if record.get("status") == "created":
        record["status"] = "content_added"

    record["updated_at"] = _now()
    _save(project_id, record)
    return _to_project(record)


@router.put("/{project_id}/content", response_model=Project)
async def update_content(project_id: str, data: ContentAdd) -> Project:
    """Replace project content entirely (supports file deletion)."""
    try:
        record = _load(project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")

    record["content_text"] = data.text
    record["content_files"] = data.files
    record["updated_at"] = _now()
    _save(project_id, record)
    return _to_project(record)
