"""Pro Mode — Project persistence layer.

Single source of truth for project CRUD. All other modules import from here.
Uses json_store.atomic_write_json for crash-safe persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.services.json_store import atomic_write_json

from .models import StepUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/project", tags=["pro-mode-project"])

_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data" / "pro_mode"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_PROJECT_FILE = _DATA_DIR / "projects.json"


# ── Low-level persistence (shared by all modules) ──────────────────

def load_all_projects() -> dict[str, Any]:
    if _PROJECT_FILE.exists():
        try:
            return json.loads(_PROJECT_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"projects": {}}
    return {"projects": {}}


def save_all_projects(data: dict[str, Any]) -> None:
    atomic_write_json(str(_PROJECT_FILE), data)


def load_project(project_id: str) -> dict | None:
    data = load_all_projects()
    return data.get("projects", {}).get(project_id)


def save_project(project_id: str, project: dict) -> None:
    data = load_all_projects()
    if "projects" not in data:
        data["projects"] = {}
    data["projects"][project_id] = project
    save_all_projects(data)


def update_project(project_id: str, updates: dict) -> dict | None:
    data = load_all_projects()
    project = data.get("projects", {}).get(project_id)
    if not project:
        return None
    project.update(updates)
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_all_projects(data)
    return project


# ── REST endpoints ─────────────────────────────────────────────────

@router.get("/list")
async def list_projects():
    """列出所有项目。"""
    data = load_all_projects()
    projects = list(data.get("projects", {}).values())
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    summaries = [{
        "id": p["id"], "title": p.get("title", ""), "genre": p.get("genre", ""),
        "summary": p.get("summary", ""),
        "char_count": len(p.get("characters", [])), "scene_count": len(p.get("scenes", [])),
        "shot_count": len(p.get("shots", [])), "current_step": p.get("current_step", 0),
        "template": p.get("template", ""),
        "created_at": p.get("created_at", ""),
    } for p in projects]
    return {"total": len(summaries), "projects": summaries}


@router.get("/{project_id}")
async def get_project(project_id: str):
    """获取项目完整详情。"""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"success": True, "project": project}


@router.patch("/{project_id}/step")
async def update_project_step(project_id: str, req: StepUpdateRequest):
    """更新项目当前步骤（持久化进度）。"""
    project = update_project(project_id, {"current_step": req.current_step})
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"success": True, "current_step": req.current_step}


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """删除项目。"""
    data = load_all_projects()
    if project_id not in data.get("projects", {}):
        raise HTTPException(status_code=404, detail="项目不存在")
    del data["projects"][project_id]
    save_all_projects(data)
    return {"success": True, "message": f"项目 {project_id} 已删除"}
