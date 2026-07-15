"""Tool Call Logger — records every external API/tool invocation.

Tracks: tool name, parameters, result, success/failure, latency, session context.
Enables analysis of tool reliability and identifies optimization opportunities.

Aligns with: Mechanism 5 (工具调用优化) + Operation Monitoring (运行监控)
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

TOOL_LOG_PATH = os.path.join("data", "tool_calls.jsonl")


@dataclass
class ToolCall:
    """A single tool invocation record."""
    tool_name: str  # e.g. "feishu_get_doc", "feishu_search"
    params: dict = field(default_factory=dict)
    result_summary: str = ""  # success / HTTP_400 / timeout / ...
    duration_ms: int = 0
    session_id: str = ""
    error: str = ""


class ToolLogger:
    """Records and analyzes tool invocations."""

    # ── recording ─────────────────────────────────────────────────────

    async def record(self, call: ToolCall) -> None:
        """Record a tool call to the log."""
        try:
            os.makedirs(os.path.dirname(TOOL_LOG_PATH), exist_ok=True)
            entry = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "tool_name": call.tool_name,
                "params_summary": json.dumps(call.params, ensure_ascii=False)[:200],
                "result": call.result_summary,
                "duration_ms": call.duration_ms,
                "session_id": call.session_id,
                "error": call.error[:200] if call.error else "",
            }
            with open(TOOL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.debug("Tool log write failed: %s", exc)

    async def wrap_call(
        self,
        tool_name: str,
        session_id: str = "",
        **params,
    ):
        """Async context manager that records the tool call."""
        t0 = time.monotonic()
        result_summary = "unknown"
        error = ""
        try:
            yield
            result_summary = "success"
        except Exception as exc:
            result_summary = "error"
            error = str(exc)
            raise
        finally:
            duration = int((time.monotonic() - t0) * 1000)
            await self.record(ToolCall(
                tool_name=tool_name,
                params=params,
                result_summary=result_summary,
                duration_ms=duration,
                session_id=session_id,
                error=error,
            ))

    # ── analysis ──────────────────────────────────────────────────────

    async def get_stats(self, tool_name: str | None = None, limit: int = 100) -> dict:
        """Get failure rate and latency stats for tool calls."""
        if not os.path.exists(TOOL_LOG_PATH):
            return {"total": 0, "success_rate": 0, "avg_latency_ms": 0}

        calls: list[dict] = []
        with open(TOOL_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    if tool_name and c.get("tool_name") != tool_name:
                        continue
                    calls.append(c)

        recent = calls[-limit:]
        if not recent:
            return {"total": len(calls), "success_rate": 0, "avg_latency_ms": 0}

        success = sum(1 for c in recent if c.get("result") == "success")
        avg_latency = sum(c.get("duration_ms", 0) for c in recent) / len(recent)

        # Per-tool breakdown
        tool_stats: dict[str, dict] = {}
        for c in recent:
            tn = c.get("tool_name", "unknown")
            if tn not in tool_stats:
                tool_stats[tn] = {"total": 0, "success": 0, "total_latency": 0}
            tool_stats[tn]["total"] += 1
            if c.get("result") == "success":
                tool_stats[tn]["success"] += 1
            tool_stats[tn]["total_latency"] += c.get("duration_ms", 0)

        return {
            "total": len(calls),
            "recent_total": len(recent),
            "success_rate": round(success / len(recent) * 100, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "by_tool": {
                tn: {
                    "total": s["total"],
                    "success_rate": round(s["success"] / s["total"] * 100, 1),
                    "avg_latency_ms": round(s["total_latency"] / s["total"], 1),
                }
                for tn, s in tool_stats.items()
            },
        }


# Module-level singleton
tool_logger = ToolLogger()
