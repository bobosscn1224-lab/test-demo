"""Episodic Memory Store — cross-session conversation indexing.

After each chat session ends (or periodically), the conversation is summarized
and indexed into ChromaDB.  Subsequent conversations can retrieve relevant
past discussions semantically.

Usage:
    from app.services.episodic_memory import episodic_memory

    # After a chat session ends
    await episodic_memory.index_session(session_id, messages, title)

    # During context assembly, find relevant past conversations
    results = await episodic_memory.search("权限问题怎么解决")
"""
from __future__ import annotations

import hashlib
import logging
import time

from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

COLLECTION_NAME = "episodic_memory"


class EpisodicMemoryStore:
    """Indexes and retrieves past conversation summaries."""

    async def _ensure_collection(self):
        """Lazy-init the episodic memory ChromaDB collection."""
        await rag_service.initialize()
        try:
            collection = rag_service.chroma_client.get_collection(COLLECTION_NAME)
        except Exception:
            collection = rag_service.chroma_client.create_collection(
                name=COLLECTION_NAME,
                metadata={"description": "Past conversation summaries for cross-session retrieval"},
            )
        return collection

    # ── index ──────────────────────────────────────────────────────────

    async def index_session(
        self,
        session_id: str,
        messages: list[dict],
        title: str = "",
    ) -> str | None:
        """Summarize a conversation and index it for future retrieval.

        Args:
            session_id: The chat session ID
            messages: List of {role, content} dicts from the conversation
            title: Optional session title

        Returns the document ID if indexed, None if skipped.
        """
        if not messages:
            return None

        # Build a simple summary from the conversation
        summary = self._build_summary(messages, title)
        if not summary or len(summary) < 20:
            return None

        try:
            collection = await self._ensure_collection()
            doc_id = f"episodic_{session_id}_{int(time.time())}"
            metadata = {
                "session_id": session_id,
                "title": title or "未命名对话",
                "message_count": len(messages),
                "indexed_at": time.time(),
                "doc_type": "episodic_memory",
                "source": "chat_session",
            }
            await rag_service.index_text(
                summary,
                {
                    "doc_id": doc_id,
                    "source": f"session:{session_id}",
                    "doc_type": "episodic_memory",
                    "session_id": session_id,
                    "title": title or "未命名对话",
                },
                collection_name=COLLECTION_NAME,
            )
            logger.info("Episodic: indexed session %s (%d messages)", session_id, len(messages))
            return doc_id
        except Exception as exc:
            logger.warning("Episodic: index_session failed for %s: %s", session_id, exc)
            return None

    # ── search ─────────────────────────────────────────────────────────

    async def search(self, query: str, top_k: int = 3) -> str:
        """Find past conversations relevant to the query.

        Returns a Markdown-formatted string for injection into the system prompt.
        """
        if not query or len(query) < 3:
            return ""

        try:
            collection = await self._ensure_collection()
            count = collection.count()
            if count == 0:
                return ""

            results = collection.query(
                query_texts=[query],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            if not documents:
                return ""

            lines = ["## 相关历史对话"]
            for doc, meta, dist in zip(documents, metadatas, distances):
                relevance = max(0, int((1 - dist) * 100)) if dist else 50
                title = (meta or {}).get("title", "历史对话")
                lines.append(f"- **{title}** (相关度 {relevance}%)：{doc[:300]}")
            return "\n".join(lines)

        except Exception as exc:
            logger.warning("Episodic: search failed: %s", exc)
            return ""

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_summary(messages: list[dict], title: str = "") -> str:
        """Build a simple summary from conversation messages."""
        parts: list[str] = []
        if title:
            parts.append(f"对话主题：{title}")

        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
        assistant_msgs = [m.get("content", "") for m in messages if m.get("role") == "assistant"]

        if user_msgs:
            # Take first and last user messages for context
            parts.append(f"用户首次提问：{user_msgs[0][:200]}")
            if len(user_msgs) > 1:
                parts.append(f"用户最后提问：{user_msgs[-1][:200]}")

        if assistant_msgs:
            # First assistant response summary
            first = assistant_msgs[0]
            parts.append(f"助手回答摘要：{first[:300]}")

        return "\n".join(parts)


# Module-level singleton
episodic_memory = EpisodicMemoryStore()
