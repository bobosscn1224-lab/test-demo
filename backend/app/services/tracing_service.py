"""LLM Tracing & Observability Service — Langfuse-backed.

Records every LLM call (prompt, response, tokens, latency) and quality scores.
Gracefully degrades to in-memory logging if Langfuse is not installed/configured.

Two modes:
  1. Full Langfuse  — docker-compose up or cloud.langfuse.com
  2. Lightweight log — writes to data/traces.jsonl (no external dependencies)

Config (in .env):
  LANGFUSE_PUBLIC_KEY=...     # required for Langfuse mode
  LANGFUSE_SECRET_KEY=...
  LANGFUSE_HOST=http://localhost:3000   # self-hosted, or omit for cloud
"""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

TRACES_PATH = os.path.join("data", "traces.jsonl")

# Try importing Langfuse; fall back to lightweight mode
_LANGFUSE_AVAILABLE = False
try:
    from langfuse import Langfuse as _LangfuseClient

    _LANGFUSE_AVAILABLE = True
except ImportError:
    pass


@dataclass
class TraceSpan:
    """A single LLM call trace."""
    trace_id: str
    name: str  # e.g. "chat", "quality_check", "extraction"
    input_text: str = ""
    output_text: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    metadata: dict = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


class TracingService:
    """Unified tracing: Langfuse when available, lightweight JSONL fallback."""

    def __init__(self):
        self._client = None
        self._enabled = False
        self._mode = "off"

        if _LANGFUSE_AVAILABLE:
            pk = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
            sk = os.environ.get("LANGFUSE_SECRET_KEY", "")
            if pk and sk:
                host = os.environ.get("LANGFUSE_HOST", "")
                kwargs = {"public_key": pk, "secret_key": sk}
                if host:
                    kwargs["host"] = host
                try:
                    self._client = _LangfuseClient(**kwargs)
                    self._enabled = True
                    self._mode = "langfuse"
                    logger.info("Tracing: Langfuse mode (host=%s)", host or "cloud")
                except Exception as exc:
                    logger.warning("Langfuse init failed, using lightweight mode: %s", exc)
                    self._mode = "lightweight"
                    self._enabled = True
            else:
                logger.info("Tracing: Langfuse installed but not configured, using lightweight mode")
                self._mode = "lightweight"
                self._enabled = True
        else:
            logger.info("Tracing: Langfuse not installed, using lightweight mode")
            self._mode = "lightweight"
            self._enabled = True

    @property
    def is_available(self) -> bool:
        return self._enabled

    # ── trace recording ──────────────────────────────────────────────

    async def record(self, span: TraceSpan) -> str | None:
        """Record a single trace span. Returns trace_id or None."""
        if not self._enabled:
            return None

        trace_id = span.trace_id or _gen_id()
        span.trace_id = trace_id

        if self._mode == "langfuse" and self._client:
            return self._record_langfuse(span)
        else:
            return self._record_lightweight(span)

    async def record_score(self, trace_id: str, name: str, value: float) -> None:
        """Attach a score to an existing trace."""
        if self._mode == "langfuse" and self._client:
            try:
                self._client.score(
                    trace_id=trace_id,
                    name=name,
                    value=value,
                )
            except Exception as exc:
                logger.debug("Langfuse score failed: %s", exc)
        else:
            self._log_line({
                "type": "score",
                "trace_id": trace_id,
                "name": name,
                "value": value,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })

    # ── internal ─────────────────────────────────────────────────────

    def _record_langfuse(self, span: TraceSpan) -> str:
        trace = self._client.trace(
            id=span.trace_id,
            name=span.name,
            input=span.input_text[:2000] if span.input_text else None,
            output=span.output_text[:2000] if span.output_text else None,
            metadata={
                **span.metadata,
                "model": span.model,
                "tokens_in": span.tokens_in,
                "tokens_out": span.tokens_out,
                "latency_ms": span.latency_ms,
            },
            tags=span.tags,
        )
        # Generation span for token-level detail
        self._client.generation(
            trace_id=span.trace_id,
            name=f"{span.name}_generation",
            input=span.input_text[:2000],
            output=span.output_text[:2000],
            model=span.model,
            usage={
                "input": span.tokens_in,
                "output": span.tokens_out,
            },
        )
        for name, value in span.scores.items():
            self._client.score(trace_id=span.trace_id, name=name, value=value)
        return span.trace_id

    def _record_lightweight(self, span: TraceSpan) -> str:
        self._log_line({
            "type": "trace",
            "trace_id": span.trace_id,
            "name": span.name,
            "model": span.model,
            "tokens_in": span.tokens_in,
            "tokens_out": span.tokens_out,
            "latency_ms": span.latency_ms,
            "tags": span.tags,
            "scores": span.scores,
            "input_preview": span.input_text[:200],
            "output_preview": span.output_text[:200],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        return span.trace_id

    @staticmethod
    def _log_line(entry: dict) -> None:
        try:
            os.makedirs(os.path.dirname(TRACES_PATH), exist_ok=True)
            with open(TRACES_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def _gen_id() -> str:
    import uuid
    return str(uuid.uuid4())[:12]


# Module-level singleton
tracing_service = TracingService()
