"""Activity store — JSON persistence for draft weekly report activities.
Prevents LLM drift by saving every state change to disk.
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)
_DIR = os.path.join("data", "report_drafts")
os.makedirs(_DIR, exist_ok=True)


def _path(session_id: str) -> str:
    safe = session_id.replace("\\", "_").replace("/", "_").replace("..", "_")
    return os.path.join(_DIR, f"{safe}.json")


def load(session_id: str) -> dict:
    """Load activities for a session. Returns {start_date, end_date, days: [{day_index, activities}]}."""
    p = _path(session_id)
    if not os.path.exists(p):
        return {"start_date": "", "end_date": "", "days": [[] for _ in range(5)]}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure days is always 5 lists
        if "days" not in data or len(data.get("days", [])) != 5:
            data["days"] = [[] for _ in range(5)]
        return data
    except Exception:
        return {"start_date": "", "end_date": "", "days": [[] for _ in range(5)]}


def save(session_id: str, start_date: str, end_date: str, days_activities: list[list[dict]]) -> None:
    """Save activities to disk."""
    data = {"start_date": start_date, "end_date": end_date, "days": days_activities}
    with open(_path(session_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("ActivityStore: saved %d activities for %s", sum(len(d) for d in days_activities), session_id)
