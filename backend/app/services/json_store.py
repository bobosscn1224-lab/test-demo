"""Shared crash-safe JSON persistence helpers."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | Path, data: Any, *, indent: int | None = 2) -> None:
    """Write JSON in the target directory and atomically replace the old file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=indent)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp), str(target))
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
