"""Report record store — JSON-based persistence for weekly report metadata.

Single source of truth for the report list. No filesystem scanning.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from app.services.json_store import atomic_write_json
from app.services._paths import PUBLIC_DIR, WEEKLY_REPORT_DIR

logger = logging.getLogger(__name__)

_INDEX_PATH = os.path.abspath(os.path.join("data", "reports_index.json"))


def _existing_paths(record: dict) -> list[str]:
    """Resolve legacy absolute paths and portable canonical locations."""
    filename = os.path.basename(str(record.get("filename", "")))
    candidates = list(record.get("file_paths", []))
    if filename:
        candidates.extend([str(PUBLIC_DIR / filename), str(WEEKLY_REPORT_DIR / filename)])
    existing: list[str] = []
    for path in candidates:
        absolute = os.path.abspath(path)
        if os.path.isfile(absolute) and absolute not in existing:
            existing.append(absolute)
    return existing


def _load() -> list[dict]:
    """Load all report records from JSON file."""
    if not os.path.exists(_INDEX_PATH):
        return []
    try:
        with open(_INDEX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(records: list[dict]) -> None:
    """Save report records to JSON file."""
    atomic_write_json(_INDEX_PATH, records)


def add_record(filename: str, sheet_name: str, date_range: str, file_paths: list[str]) -> dict:
    """Add a new report record. Returns the record."""
    records = _load()
    now = time.time()
    # Remove existing record with same filename (update)
    records = [r for r in records if r.get("filename") != filename]
    record = {
        "filename": filename,
        "sheet_name": sheet_name,
        "date_range": date_range,
        "created_at": datetime.now().isoformat(),
        "created_ts": now,
        "file_paths": [os.path.abspath(p) for p in file_paths if os.path.exists(p)],
    }
    records.append(record)
    # Keep most recent 100 records
    records.sort(key=lambda r: r.get("created_ts", 0), reverse=True)
    records = records[:100]
    _save(records)
    logger.info("ReportStore: added %s (%d paths)", filename, len(record["file_paths"]))
    return record


def list_records() -> list[dict]:
    """List all report records, newest first."""
    records = _load()
    records.sort(key=lambda r: r.get("created_ts", 0), reverse=True)
    # Verify files still exist, mark missing ones
    for r in records:
        existing = _existing_paths(r)
        r["_missing"] = len(existing) == 0
        r["download_url"] = f"/api/skills/download/{r['filename']}" if existing else ""
    return records


def delete_record(filename: str) -> tuple[bool, list[str]]:
    """Delete a report record and its files. Returns (found, deleted_paths)."""
    records = _load()
    deleted: list[str] = []
    new_records = []
    for r in records:
        if r.get("filename") == filename:
            for p in _existing_paths(r):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                        deleted.append(p)
                except Exception:
                    pass
        else:
            new_records.append(r)
    if len(new_records) < len(records):
        _save(new_records)
        logger.info("ReportStore: deleted %s (%d files)", filename, len(deleted))
        return True, deleted
    return False, []


def get_record(filename: str) -> dict | None:
    """Get a single report record by filename."""
    for r in _load():
        if r.get("filename") == filename:
            return r
    return None
