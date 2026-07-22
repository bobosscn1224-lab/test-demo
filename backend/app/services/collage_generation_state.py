"""Crash-safe collage generation progress and complete-batch validation."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services._paths import DATA_DIR
from app.services.json_store import atomic_write_json


STATE_DIR = DATA_DIR / "ppt_collage_generation"
TERMINAL_STATUSES = {"completed", "failed", "timed_out", "cancelled"}
TRANSIENT_VARIANT_STATUSES = {
    "generating", "geometry_checking", "normalizing", "semantic_checking", "cooling_down",
}
COMMITTABLE_VARIANT_STATUSES = {"passed", "passed_with_manual_review"}


def _state_path(project_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{8}", project_id):
        raise ValueError("invalid project id")
    return STATE_DIR / f"{project_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_generation_state() -> dict[str, Any]:
    return {
        "run_id": "", "status": "idle", "current_label": "", "attempt": 0,
        "completed_labels": [], "started_at": "", "updated_at": "",
        "elapsed_seconds": 0, "message": "", "error": "",
        "variants": {
            label: {
                "status": "queued", "attempt": 0, "elapsed_seconds": 0,
                "message": "", "error": "", "artifact_path": "",
            }
            for label in ("A", "B", "C")
        },
    }


def save_generation_state(project_id: str, state: dict[str, Any]) -> dict[str, Any]:
    merged = empty_generation_state()
    path = _state_path(project_id)
    # Always load previous state for the same run to preserve variants
    if path.exists():
        try:
            with path.open(encoding="utf-8") as handle:
                previous = json.load(handle)
            if previous.get("run_id") == state.get("run_id") and isinstance(previous.get("variants"), dict):
                merged["variants"] = previous["variants"]
        except (OSError, ValueError, TypeError):
            pass
    # Extract variant updates before they get overwritten by merged.update()
    incoming_variants = state.pop("variants", None)
    merged.update(state)
    # Merge variant updates into preserved variants dict
    if isinstance(incoming_variants, dict) and isinstance(merged.get("variants"), dict):
        for label, variant_data in incoming_variants.items():
            if label in merged["variants"]:
                merged["variants"][label].update(variant_data)
    merged["updated_at"] = _now()
    _merge_variant_defaults(merged)
    atomic_write_json(path, merged)
    return merged


def _merge_variant_defaults(result: dict[str, Any]) -> None:
    provided = result.get("variants") if isinstance(result.get("variants"), dict) else {}
    defaults = empty_generation_state()["variants"]
    result["variants"] = {
        label: {**defaults[label], **(provided.get(label) or {})}
        for label in ("A", "B", "C")
    }


def load_generation_state(project_id: str, *, recover_transient: bool = False) -> dict[str, Any]:
    path = _state_path(project_id)
    if not path.exists():
        return empty_generation_state()
    try:
        with path.open(encoding="utf-8") as handle:
            result = empty_generation_state()
            result.update(json.load(handle))
            _merge_variant_defaults(result)
            if recover_transient:
                for variant in result["variants"].values():
                    if variant.get("status") in TRANSIENT_VARIANT_STATUSES:
                        variant["status"] = "retrying"
                        variant["message"] = "检测到中断任务，等待恢复"
            started = str(result.get("started_at") or "")
            if started:
                try:
                    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    if result.get("status") in TERMINAL_STATUSES and result.get("updated_at"):
                        end_dt = datetime.fromisoformat(str(result["updated_at"]).replace("Z", "+00:00"))
                    else:
                        end_dt = datetime.now(timezone.utc)
                    result["elapsed_seconds"] = max(0, int((end_dt - start_dt).total_seconds()))
                except (TypeError, ValueError):
                    pass
            return result
    except (OSError, ValueError, TypeError):
        return empty_generation_state()


def save_variant_state(
    project_id: str,
    run_id: str,
    label: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    normalized = str(label or "").strip().upper()
    if normalized not in {"A", "B", "C"}:
        raise ValueError("variant label must be A, B or C")
    current = load_generation_state(project_id)
    if current.get("run_id") and current.get("run_id") != run_id:
        raise ValueError("run_id does not match current collage generation")
    current["run_id"] = run_id
    current["variants"][normalized].update(patch)
    current["current_label"] = normalized
    current["attempt"] = int(current["variants"][normalized].get("attempt") or 0)
    return save_generation_state(project_id, current)


def is_complete_collage_batch(collages: list[dict], run_id: str) -> bool:
    if not run_id or len(collages) != 3:
        return False
    labels = {str(item.get("label", "")).upper() for item in collages}
    if labels != {"A", "B", "C"}:
        return False
    for item in collages:
        if item.get("run_id") != run_id:
            return False
        path = str(item.get("path") or "")
        if not path or not Path(path).is_file():
            return False
    return True


def is_committable_batch(
    collages: list[dict],
    run_id: str,
    variants: dict[str, dict[str, Any]],
) -> bool:
    if not is_complete_collage_batch(collages, run_id):
        return False
    if set(variants) != {"A", "B", "C"}:
        return False
    return all(
        str(variants[label].get("status") or "") in COMMITTABLE_VARIANT_STATUSES
        for label in ("A", "B", "C")
    )
