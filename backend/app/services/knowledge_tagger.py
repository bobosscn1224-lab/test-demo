"""Knowledge Tagger — auto-tag documents with structured business labels.

After a file is indexed into ChromaDB, this service analyzes its content
and assigns structured tags (process, role, doc_type, project).  These
tags are stored in ChromaDB metadata and used by the RAG search to
boost/filter results based on the current business context.

Tags improve retrieval precision — directly addressing the quality issue:
"回答太全面但没重点" by enabling context-aware result ranking.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# Canonical tag vocabulary
PROCESS_STAGES = [
    "MO", "LTC", "POC", "售前", "售后", "交付", "运维",
    "商机管理", "方案评审", "合同", "招投标", "其他",
]
ROLES = [
    "FDE", "售前工程师", "销售", "技术经理", "产品经理",
    "项目经理", "客户成功", "其他",
]
DOC_TYPES = [
    "制度规则", "流程文档", "方案模板", "评审模板",
    "案例", "经验总结", "培训材料", "工具文档", "其他",
]

TAG_PROMPT = """分析以下文档内容，为其打上结构化标签。

## 文档内容（前2000字）
{content}

## 可用标签

流程阶段（选1-2个）：{stages}
岗位角色（选1个）：{roles}
文档类型（选1个）：{doc_types}

## 额外提取
- project: 涉及的项目名称（如有），否则null
- keywords: 3-5个核心关键词

返回严格JSON：
{{"process_stage":["MO"],"role":"FDE","doc_type":"方案模板","project":null,"keywords":["关键词1","关键词2"]}}"""


class KnowledgeTagger:
    """Auto-tags documents with business context labels."""

    @property
    def stages(self) -> list[str]:
        return PROCESS_STAGES

    @property
    def roles(self) -> list[str]:
        return ROLES

    @property
    def doc_types(self) -> list[str]:
        return DOC_TYPES

    # ── public API ────────────────────────────────────────────────────

    async def tag_file(self, file_path: str) -> dict[str, Any]:
        """Analyze a file and return structured tags. Caches to .meta file."""
        cache_path = file_path + ".tags.json"
        if os.path.exists(cache_path):
            try:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("file_path") == file_path:
                    return cached
            except Exception:
                pass

        # Read file content
        try:
            from app.utils.file_parser import parse_file_sync
            text = parse_file_sync(file_path)
        except Exception:
            text = ""
        if not text:
            return self._default_tags()

        # Ask LLM to tag
        prompt = TAG_PROMPT.format(
            content=text[:2000],
            stages=", ".join(PROCESS_STAGES),
            roles=", ".join(ROLES),
            doc_types=", ".join(DOC_TYPES),
        )
        try:
            resp = await llm_service.chat(
                interaction_name="knowledge_tagging",
                system_prompt="你是企业知识管理专家。严格返回JSON格式的标签。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,
                thinking={"type": "disabled"},
            )
            text_out = ""
            if resp.content:
                for block in resp.content:
                    if hasattr(block, "text"):
                        text_out += block.text
            text_out = text_out.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            # Handle LLM returning markdown or extra text around JSON
            if "{" in text_out and "}" in text_out:
                text_out = text_out[text_out.index("{"):text_out.rindex("}")+1]
            tags = json.loads(text_out)
        except Exception as exc:
            logger.debug("Tagging failed for %s, using defaults: %s", file_path, exc)
            tags = {}

        # Normalize + fill defaults
        result = {
            "file_path": file_path,
            "process_stage": self._normalize_list(tags.get("process_stage", []), PROCESS_STAGES),
            "role": self._normalize_value(tags.get("role", ""), ROLES),
            "doc_type": self._normalize_value(tags.get("doc_type", ""), DOC_TYPES),
            "project": tags.get("project") if tags.get("project") else None,
            "keywords": tags.get("keywords", [])[:5],
        }

        # Cache
        try:
            os.makedirs(os.path.dirname(cache_path) if os.path.dirname(cache_path) else ".", exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception:
            pass

        return result

    async def tag_text(self, text: str, source: str = "unknown") -> dict[str, Any]:
        """Tag raw text (e.g. Feishu doc content)."""
        prompt = TAG_PROMPT.format(
            content=text[:2000],
            stages=", ".join(PROCESS_STAGES),
            roles=", ".join(ROLES),
            doc_types=", ".join(DOC_TYPES),
        )
        try:
            resp = await llm_service.chat(
                interaction_name="knowledge_tagging",
                system_prompt="你是企业知识管理专家。严格返回JSON格式的标签。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,
                thinking={"type": "disabled"},
            )
            text_out = ""
            if resp.content:
                for block in resp.content:
                    if hasattr(block, "text"):
                        text_out += block.text
            text_out = text_out.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            tags = json.loads(text_out)
        except Exception:
            tags = {}

        return {
            "source": source,
            "process_stage": self._normalize_list(tags.get("process_stage", []), PROCESS_STAGES),
            "role": self._normalize_value(tags.get("role", ""), ROLES),
            "doc_type": self._normalize_value(tags.get("doc_type", ""), DOC_TYPES),
            "project": tags.get("project") if tags.get("project") else None,
            "keywords": tags.get("keywords", [])[:5],
        }

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _default_tags() -> dict[str, Any]:
        return {
            "process_stage": ["其他"],
            "role": "其他",
            "doc_type": "其他",
            "project": None,
            "keywords": [],
        }

    @staticmethod
    def _normalize_value(value: str, valid_list: list[str]) -> str:
        if value in valid_list:
            return value
        return "其他"

    @staticmethod
    def _normalize_list(values: list[str], valid_list: list[str]) -> list[str]:
        result = [v for v in values if v in valid_list]
        return result if result else ["其他"]

    @staticmethod
    def tags_to_metadata(tags: dict[str, Any]) -> dict[str, Any]:
        """Convert tags dict to ChromaDB-compatible metadata."""
        return {
            "process_stage": ",".join(tags.get("process_stage", [])),
            "role": tags.get("role", "其他"),
            "doc_type": tags.get("doc_type", "其他"),
            "project": tags.get("project") or "",
            "keywords": ",".join(tags.get("keywords", [])),
        }


# Module-level singleton
knowledge_tagger = KnowledgeTagger()
