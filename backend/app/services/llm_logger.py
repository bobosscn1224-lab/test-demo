"""Redacted audit records for every paid model attempt."""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from app.services._paths import DATA_DIR
from app.services.json_store import atomic_write_json
from app.utils.sensitive_data import redact_sensitive_text

logger = logging.getLogger(__name__)
_DIR = DATA_DIR / "model_audit"


def _safe(value: str, limit: int = 5000) -> str:
    return redact_sensitive_text(str(value or ""))[:limit]


def log_model_attempt(
    *, interaction_name: str, attempt: int, model: str, status: str,
    failures: list[str], checks: list[str], usage: dict[str, Any],
    system_prompt: str, user_prompt: str, output: str,
) -> str:
    """Persist one redacted attempt; never stores credentials or full huge inputs."""
    _DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
    filename = f"{stamp}_{uuid.uuid4().hex[:10]}_{interaction_name}.json"
    path = _DIR / filename
    redacted_user = _safe(user_prompt)
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "interaction_name": interaction_name,
        "attempt": attempt,
        "model": model,
        "status": status,
        "checks_passed": checks,
        "failures": [_safe(x, 1000) for x in failures],
        "usage": usage,
        "input": {
            "system_preview": _safe(system_prompt, 2000),
            "user_preview": redacted_user,
            "user_sha256": hashlib.sha256(redacted_user.encode("utf-8")).hexdigest(),
            "user_chars": len(user_prompt or ""),
        },
        "output": {
            "preview": _safe(output),
            "chars": len(output or ""),
        },
    }
    atomic_write_json(path, record)
    logger.info("ModelAudit: %s attempt=%s status=%s", interaction_name, attempt, status)
    return str(path)


def log_call(operation: str, system_prompt: str, user_prompt: str,
             response_text: str, error: str = "") -> str:
    """Backward-compatible logger for legacy non-model operations."""
    return log_model_attempt(
        interaction_name=operation,
        attempt=1,
        model="legacy",
        status="call_failed" if error else "passed",
        failures=[error] if error else [],
        checks=[], usage={}, system_prompt=system_prompt,
        user_prompt=user_prompt, output=response_text,
    )
