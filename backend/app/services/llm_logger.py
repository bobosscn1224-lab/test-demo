"""LLM interaction logger — records every call for audit and debugging."""
from __future__ import annotations

import json
import logging
import os
import time

logger = logging.getLogger(__name__)
_DIR = os.path.join("data", "llm_logs")
os.makedirs(_DIR, exist_ok=True)


def log_call(operation: str, system_prompt: str, user_prompt: str, response_text: str, error: str = "") -> str:
    """Log an LLM call to JSON. Returns the log file path."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{operation}_{ts}_{abs(hash(user_prompt)) % 10000:04d}.json"
    filepath = os.path.join(_DIR, filename)
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "operation": operation,
        "input": {"system": system_prompt, "user": user_prompt[:5000]},
        "output": {"text": response_text[:5000], "error": error} if not error else {"error": error},
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    logger.info("LLMLogger: %s → %s", operation, filename)
    return filepath
