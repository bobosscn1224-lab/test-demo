import os
import re
import hashlib
import logging
import asyncio
from collections import defaultdict

import httpx

from app.config import settings
from app.utils.file_parser import parse_file, parse_file_sync
from app.utils.text_chunker import chunk_text

logger = logging.getLogger(__name__)

CHUNK_SIZE = 450
CHUNK_OVERLAP = 80
TOP_K_DEFAULT = 8
HYBRID_CANDIDATES = 200
MAX_CHUNKS_PER_DOC = 3
MAX_CONTEXT_CHARS = 16000


class SiliconFlowEmbedding:
    """Thin wrapper around SiliconFlow's OpenAI-compatible embeddings API.

    Provides an ``encode(texts) -> list[list[float]]`` interface so the rest of
    the RAG service doesn't need to know about the HTTP backend.
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client = httpx.Client(
            timeout=httpx.Timeout(60.0),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return embedding vectors for *texts*.

        Args:
            texts: One or more strings to embed.  Texts longer than 400 chars
                   are truncated to stay under SiliconFlow's 512-token limit.

        Returns:
            A list of embedding vectors (each a list of floats), in the same
            order as *texts*.
        """
        if isinstance(texts, str):
            texts = [texts]

        # Keep chunks within the embedding model's practical context window.
        # The chunker is configured to stay near this size, so truncation should
        # be a last-resort guard rather than normal behavior.
        MAX_CHARS = 512
        truncated = []
        for t in texts:
            if len(t) > MAX_CHARS:
                truncated.append(t[:MAX_CHARS])
            else:
                truncated.append(t)

        # SiliconFlow limits batch size; chunk if needed
        all_embeddings = []
        batch_size = 32
        for i in range(0, len(truncated), batch_size):
            batch = truncated[i:i + batch_size]
            resp = self._client.post(
                self._base_url,
                json={"model": self._model, "input": batch},
            )
            if resp.status_code != 200:
                logger.error("SiliconFlow embedding API error %d: %s", resp.status_code, resp.text[:500])
                raise RuntimeError(f"Embedding API returned {resp.status_code}")

            data = resp.json()
            # SiliconFlow returns {"data": [{"embedding": [...], "index": 0}, ...]}
            items = sorted(data["data"], key=lambda x: x["index"])
            for item in items:
                all_embeddings.append(item["embedding"])

        return all_embeddings


class RAGService:
    """Retrieval-Augmented Generation service backed by ChromaDB + SiliconFlow embeddings."""

    def __init__(self) -> None:
        self._embedding_fn: SiliconFlowEmbedding | None = None
        self._client = None
        self._collection = None
        self._corrections = None
        self._ready = False

    async def initialize(self) -> None:
        """Lazy-initialize the embedding client and ChromaDB collection."""
        if self._ready:
            return

        try:
            import chromadb
        except ImportError as e:
            logger.warning("ChromaDB not installed: %s", e)
            return

        api_key = settings.siliconflow_api_key
        if not api_key:
            logger.warning("SiliconFlow API key not configured – RAG service disabled")
            return

        model = settings.embedding_model
        logger.info("Initializing SiliconFlow embedding: %s", model)
        self._embedding_fn = SiliconFlowEmbedding(
            api_key=api_key,
            base_url=settings.siliconflow_embedding_base_url,
            model=model,
        )

        persist_dir = settings.chroma_persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        logger.info("Initializing ChromaDB at %s", persist_dir)
        self._client = chromadb.PersistentClient(path=persist_dir)

        # Auto-clear collections if embedding model changed (vectors are incompatible).
        expected_model_tag = _model_tag(model)
        existing_names = [c.name for c in self._client.list_collections()]
        for coll_name in ("knowledge_base", "corrections"):
            if coll_name not in existing_names:
                continue
            existing = self._client.get_collection(coll_name)
            old_tag = existing.metadata.get("embedding_model") if existing.metadata else None
            needs_clear = (old_tag is None) or (old_tag != expected_model_tag)
            if needs_clear and existing.count() > 0:
                logger.warning(
                    "Embedding model changed (%s → %s) — clearing incompatible collection '%s'"
                    " (%d docs). Knowledge base will need to be re-indexed.",
                    old_tag or "unknown", expected_model_tag, coll_name, existing.count(),
                )
                self._client.delete_collection(coll_name)

        self._collection = self._client.get_or_create_collection(
            name="knowledge_base",
            metadata={"hnsw:space": "cosine", "embedding_model": expected_model_tag},
        )

        self._corrections = self._client.get_or_create_collection(
            name="corrections",
            metadata={"hnsw:space": "cosine", "embedding_model": expected_model_tag},
        )

        self._ready = True
        logger.info("RAG service initialized (%d docs, %d corrections)",
                    self._collection.count(), self._corrections.count())

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ── Indexing ──────────────────────────────────────────────

    def _index_text_sync(self, text: str, metadata: dict | None = None) -> list[str]:
        meta = metadata or {}
        chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            return []

        try:
            embeddings = self._embedding_fn.encode(chunks)
            docs_to_index = chunks
        except Exception:
            # If batch fails (e.g. token limit), try one-by-one and skip problematic chunks
            logger.warning("Batch embedding failed for %s, falling back to single-chunk encoding",
                          meta.get("source", "text"))
            embeddings = []
            docs_to_index = []
            for chunk in chunks:
                try:
                    emb = self._embedding_fn.encode([chunk])
                    embeddings.extend(emb)
                    docs_to_index.append(chunk)
                except Exception:
                    logger.warning("Skipping chunk (embedding failed): %.100s...", chunk)
            if not embeddings:
                return []

        ids = [_make_chunk_id(meta.get("source", ""), meta.get("file_path", ""), i) for i in range(len(embeddings))]
        metadatas = [{**meta, "chunk_index": i, "chunk_total": len(embeddings)} for i in range(len(embeddings))]

        self._collection.upsert(ids=ids, embeddings=embeddings, documents=docs_to_index, metadatas=metadatas)
        logger.info("Indexed %d chunks from %s", len(embeddings), meta.get("source", "text"))
        return ids

    async def index_text(self, text: str, metadata: dict | None = None) -> list[str]:
        if not self._ready:
            await self.initialize()
        if not self._ready or not text:
            return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._index_text_sync, text, metadata)

    async def index_text_markdown(self, text: str, metadata: dict | None = None) -> list[str]:
        """Index text after first cleaning it to Markdown via LLM."""
        if not self._ready:
            await self.initialize()
        if not self._ready or not text:
            return []

        from app.utils.markdown_cleaner import clean_to_markdown_sync
        cleaned = clean_to_markdown_sync(text)
        if not cleaned:
            return []

        return await self.index_text(cleaned, metadata)

    async def index_file(self, file_path: str) -> list[str]:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return []

        text = parse_file_sync(file_path)
        if not text:
            logger.warning("No text extracted from %s", file_path)
            return []

        doc_id = _make_doc_id(file_path)
        meta = {
            "source": os.path.basename(file_path),
            "file_path": file_path,
            "doc_id": doc_id,
        }
        return await self.index_text(text, meta)

    # ── Hybrid Search ─────────────────────────────────────────

    def _decompose_term(self, term: str) -> list[str]:
        """Split an alphanumeric term into alpha/number alternations.

        "L2PO" → ["L", "2", "PO"]  — each part must exist in text for a partial match.
        "L2" → ["L", "2"]
        "MO" → ["MO"]  (single part, no split)
        """
        parts = re.findall(r'[a-zA-Z]+|[0-9]+', term)
        if len(parts) <= 1:
            return [term]
        return parts

    def _keyword_score(self, query: str, text: str) -> float:
        """Score text by keyword overlap with query. Returns 0.0-1.0."""
        try:
            import jieba
        except ImportError:
            jieba = None

        q = query.lower()
        t = text.lower()

        # Extract terms: Chinese runs + alphanumeric runs
        terms = set(re.findall(r'[一-鿿]+|[a-zA-Z0-9]+', q))
        if not terms:
            return 0.0

        # ── Exact & smart partial matching ──
        exact_score = 0.0
        for term in terms:
            if term in t:
                # Exact contiguous match
                exact_score += 1.0
            elif re.match(r'^[a-zA-Z0-9]+$', term) and len(term) >= 2:
                # Try splitting at alpha/number boundaries
                parts = self._decompose_term(term)
                if len(parts) > 1:
                    found = sum(1 for p in parts if p.lower() in t)
                    if found == len(parts):
                        exact_score += 0.85  # All sub-parts found, near-exact
                    elif found > 0:
                        exact_score += 0.4 * (found / len(parts))
        exact_score /= len(terms)

        # ── Jieba token overlap ──
        token_score = 0.0
        if jieba:
            qt = set(jieba.cut(q))
            tt = set(jieba.cut(t))
            if qt:
                token_score = len(qt & tt) / len(qt)

        # ── Character bigram + trigram overlap ──
        qb = {q[i:i+2] for i in range(max(0, len(q)-1))} | {q[i:i+3] for i in range(max(0, len(q)-2))}
        tb = {t[i:i+2] for i in range(max(0, len(t)-1))} | {t[i:i+3] for i in range(max(0, len(t)-2))}
        bigram_score = len(qb & tb) / max(len(qb), 1) if qb else 0.0

        return 0.5 * exact_score + 0.3 * token_score + 0.2 * bigram_score

    def _keyword_candidates_sync(self, query: str, limit: int = 80) -> list[dict]:
        """Return lexical candidates from the local collection.

        Chroma's vector query is good at semantic recall, but process questions
        often contain exact identifiers such as M11.1, L2 PO, CRM, or QBC. A
        lightweight lexical pass keeps those exact-match chunks in the candidate
        pool before final fusion.
        """
        try:
            data = self._collection.get(include=["documents", "metadatas"])
        except Exception:
            logger.warning("Keyword candidate scan failed", exc_info=True)
            return []

        candidates = []
        ids = data.get("ids", [])
        docs = data.get("documents", [])
        metadatas = data.get("metadatas", [])
        for i, doc in enumerate(docs):
            score = self._keyword_score(query, doc or "")
            if score <= 0:
                continue
            candidates.append({
                "id": ids[i] if i < len(ids) else f"kw_{i}",
                "document": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "kw": score,
            })

        candidates.sort(key=lambda x: x["kw"], reverse=True)
        return candidates[:limit]

    def _hybrid_search_sync(self, query: str, top_k: int):
        """Run hybrid search: vector recall + lexical recall + fused ranking."""
        n_fetch = min(HYBRID_CANDIDATES, max(1, self._collection.count()))
        candidates: dict[str, dict] = {}

        try:
            qe = self._embedding_fn.encode([query])
            results = self._collection.query(query_embeddings=qe, n_results=n_fetch)
        except Exception:
            logger.warning("Hybrid search failed for: %s", query[:100], exc_info=True)
            results = None

        if results and results.get("documents") and results["documents"][0]:
            docs = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            ids = results.get("ids", [[]])[0]
            for i, doc in enumerate(docs):
                cid = ids[i] if i < len(ids) else f"vec_{i}"
                sem = max(0.0, 1.0 - distances[i]) if i < len(distances) else 0.0
                kw = self._keyword_score(query, doc)
                candidates[cid] = {
                    "id": cid,
                    "document": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": distances[i] if i < len(distances) else 1.0,
                    "sem": sem,
                    "kw": kw,
                }

        for item in self._keyword_candidates_sync(query):
            cid = item["id"]
            existing = candidates.get(cid)
            if existing:
                existing["kw"] = max(existing.get("kw", 0.0), item["kw"])
            else:
                candidates[cid] = {
                    "id": cid,
                    "document": item["document"],
                    "metadata": item["metadata"],
                    "distance": 1.0,
                    "sem": 0.0,
                    "kw": item["kw"],
                }

        if not candidates:
            return [], [], [], []

        ranked = sorted(
            candidates.values(),
            key=lambda x: (0.45 * x.get("sem", 0.0)) + (0.55 * x.get("kw", 0.0)),
            reverse=True,
        )

        per_doc_counts = defaultdict(int)
        top = []
        for item in ranked:
            meta = item.get("metadata") or {}
            doc_id = meta.get("doc_id", "")
            if doc_id and per_doc_counts[doc_id] >= MAX_CHUNKS_PER_DOC:
                continue
            if doc_id:
                per_doc_counts[doc_id] += 1
            score = (0.45 * item.get("sem", 0.0)) + (0.55 * item.get("kw", 0.0))
            top.append((item, score))
            if len(top) >= top_k:
                break

        out_docs = [item["document"] for item, _ in top]
        out_metas = [item.get("metadata", {}) for item, _ in top]
        out_dists = [item.get("distance", 1.0) for item, _ in top]
        out_scores = [s for _, s in top]

        return out_docs, out_metas, out_dists, out_scores

    def _search_sync(self, query: str, top_k: int = TOP_K_DEFAULT) -> str:
        # 1. Check corrections first — authoritative answers
        corrections = self._search_corrections_sync(query, threshold=0.85)
        correction_parts = []
        if corrections:
            for c in corrections:
                correction_parts.append(
                    f"【已校正答案 — 优先采用】\n问题: {c['question']}\n正确答案: {c['correct_answer']}"
                )

        # 2. Hybrid search in knowledge base
        docs, metadatas, _d, _s = self._hybrid_search_sync(query, top_k)
        if not docs and not correction_parts:
            return ""

        parts = []
        if correction_parts:
            parts.extend(correction_parts)
            if docs:
                parts.append("--- 以下为知识库检索结果（仅供参考）---")
        used_chars = sum(len(part) for part in parts)
        for i, doc in enumerate(docs):
            source = metadatas[i].get("source", "unknown") if i < len(metadatas) else "unknown"
            if used_chars + len(doc) > MAX_CONTEXT_CHARS:
                break
            ref_num = i + 1
            parts.append(f"[{ref_num}] 来源: {source}\n{doc}")
            used_chars += len(doc)

        return "\n\n---\n\n".join(parts)

    async def search(self, query: str, top_k: int = TOP_K_DEFAULT) -> str:
        if not self._ready:
            await self.initialize()
        if not self._ready or not query:
            return ""

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query, top_k)

    def _search_raw_sync(self, query: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
        # Check corrections first
        corrections = self._search_corrections_sync(query, threshold=0.85)
        out = []
        if corrections:
            for c in corrections:
                out.append({
                    "content": f"[已校正] {c['correct_answer']}",
                    "metadata": {"source": "correction", "question": c["question"],
                                  "correction_id": c["id"], "similarity": c["similarity"]},
                    "score": c["similarity"],
                })

        docs, metadatas, _d, scores = self._hybrid_search_sync(query, top_k)
        if docs:
            for i, doc in enumerate(docs):
                item = {
                    "content": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "score": round(scores[i], 4) if i < len(scores) else 0,
                }
                out.append(item)
        return out

    async def search_raw(self, query: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
        if not self._ready:
            await self.initialize()
        if not self._ready or not query:
            return []

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_raw_sync, query, top_k)

    # ── Delete / Stats ────────────────────────────────────────

    def _delete_doc_sync(self, doc_id: str) -> int:
        try:
            existing = self._collection.get(where={"doc_id": doc_id})
            if existing and existing["ids"]:
                self._collection.delete(ids=existing["ids"])
                logger.info("Deleted %d chunks for doc %s", len(existing["ids"]), doc_id)
                return len(existing["ids"])
        except Exception:
            logger.warning("Failed to delete doc %s", doc_id, exc_info=True)
        return 0

    async def delete_doc(self, doc_id: str) -> int:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return 0

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._delete_doc_sync, doc_id)

    def _get_stats_sync(self) -> dict:
        try:
            count = self._collection.count()
            result = self._collection.get(include=["metadatas"])
            unique_docs = set()
            if result and result.get("metadatas"):
                for m in result["metadatas"]:
                    if m and m.get("doc_id"):
                        unique_docs.add(m["doc_id"])
            return {"status": "ready", "total_chunks": count, "unique_docs": len(unique_docs)}
        except Exception:
            return {"status": "error", "total_chunks": 0, "unique_docs": 0}

    async def get_stats(self) -> dict:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return {"status": "unavailable", "total_chunks": 0, "unique_docs": 0}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_stats_sync)

    # ── Corrections (self-learning) ───────────────────────────

    def _add_correction_sync(self, question: str, correct_answer: str, source: str = "manual") -> str:
        from datetime import datetime
        cid = hashlib.md5(question.encode()).hexdigest()[:12]

        # Dedup: remove existing corrections with very similar question
        if self._corrections.count() > 0:
            try:
                qe = self._embedding_fn.encode([question])
                existing = self._corrections.query(query_embeddings=qe, n_results=min(3, self._corrections.count()))
                if existing and existing.get("ids") and existing["ids"][0]:
                    for i, eid in enumerate(existing["ids"][0]):
                        dist = existing["distances"][0][i] if existing.get("distances") else 0
                        if (1.0 - dist) >= 0.92:
                            self._corrections.delete(ids=[eid])
                            cid = eid
            except Exception:
                pass

        emb = self._embedding_fn.encode([question])
        self._corrections.add(
            ids=[cid],
            embeddings=emb,
            documents=[correct_answer],
            metadatas=[{"question": question, "correct_answer": correct_answer,
                        "source": source, "created_at": datetime.now().isoformat()}],
        )
        logger.info("Correction saved: %s → %s", question[:60], correct_answer[:60])
        return cid

    async def add_correction(self, question: str, correct_answer: str, source: str = "manual") -> str:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return ""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._add_correction_sync, question, correct_answer, source)

    def _search_corrections_sync(self, query: str, threshold: float = 0.85) -> list[dict]:
        if self._corrections.count() == 0:
            return []
        try:
            qe = self._embedding_fn.encode([query])
            results = self._corrections.query(query_embeddings=qe, n_results=min(3, self._corrections.count()))
        except Exception:
            return []

        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        out = []
        for i, doc in enumerate(results["documents"][0]):
            dist = results["distances"][0][i] if results.get("distances") else 0
            sim = 1.0 - dist
            if sim >= threshold:
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                out.append({
                    "id": results["ids"][0][i],
                    "question": meta.get("question", ""),
                    "correct_answer": doc,
                    "similarity": round(sim, 4),
                })
        return out

    async def search_corrections(self, query: str, threshold: float = 0.85) -> list[dict]:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_corrections_sync, query, threshold)

    def _delete_correction_sync(self, correction_id: str) -> bool:
        try:
            self._corrections.delete(ids=[correction_id])
            return True
        except Exception:
            return False

    async def delete_correction(self, correction_id: str) -> bool:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return False
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._delete_correction_sync, correction_id)

    def _list_corrections_sync(self) -> list[dict]:
        if self._corrections.count() == 0:
            return []
        try:
            data = self._corrections.get(include=["documents", "metadatas"])
        except Exception:
            return []
        out = []
        for i, cid in enumerate(data.get("ids", [])):
            meta = data["metadatas"][i] if i < len(data.get("metadatas", [])) else {}
            doc = data["documents"][i] if i < len(data.get("documents", [])) else ""
            out.append({
                "id": cid,
                "question": meta.get("question", ""),
                "correct_answer": doc,
                "source": meta.get("source", ""),
                "created_at": meta.get("created_at", ""),
            })
        return out

    async def list_corrections(self) -> list[dict]:
        if not self._ready:
            await self.initialize()
        if not self._ready:
            return []
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._list_corrections_sync)


def _make_chunk_id(source: str, file_path: str, index: int) -> str:
    base = file_path or source or "text"
    digest = hashlib.md5(base.encode()).hexdigest()[:12]
    return f"{digest}_{index:04d}"


def _make_doc_id(file_path: str) -> str:
    return hashlib.md5(file_path.encode()).hexdigest()[:12]


def _model_tag(model: str) -> str:
    """Short stable tag for the embedding model so we can detect changes."""
    return hashlib.md5(model.encode()).hexdigest()[:8]


rag_service = RAGService()
