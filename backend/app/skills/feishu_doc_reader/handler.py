"""Feishu Doc Reader skill — reads Feishu docs/wikis and supports analysis actions.

Triggered by doc/wiki URLs and explicit doc-reading requests.
Minutes (妙记) URLs are handled by feishu_minutes_reader — this skill
no longer claims those triggers to avoid conflicts.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from urllib.parse import parse_qs, urlparse

from app.services.feishu_service import feishu_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.feishu_token_manager import FeishuTokenManager, KB_OAUTH_SCOPE, KB_OAUTH_STATE
from app.skills.base import BaseSkill, SkillContext, SkillResult
from app.core.skill_session import SkillSessionHelper

logger = logging.getLogger(__name__)

SKILL_NAME = "feishu_doc_reader"
_sessions: dict[str, dict] = {}
_helper = SkillSessionHelper(SKILL_NAME, _sessions)

DISPLAY_LIMIT = 50000


class FeishuDocReaderSkill(BaseSkill):
    name = "feishu_doc_reader"
    description = "读取飞书文档/wiki并利用其内容进行总结、分析、生成PPT大纲等。支持应用身份读取和用户OAuth授权，可将内容保存到知识库。"
    # NOTE: Minutes-related triggers ("飞书妙记","妙记","会议纪要","会议记录") removed
    # to avoid conflict with feishu_minutes_reader.
    triggers = [
        "读取飞书文档", "飞书文档", "读取飞书", "飞书API", "飞书 API",
        "测试飞书文档", "提取飞书", "分析飞书文档", "飞书链接", "飞书URL",
    ]
    keywords = ["feishu", "lark", "docx", "docs", "wiki", "飞书", "飞书文档", "feishu.cn"]

    def can_handle(self, message: str) -> bool:
        msg = message.lower()

        # Explicitly DELEGATE knowledge-base import requests to the knowledge route
        kb_terms = (
            "导入飞书知识库", "飞书知识库导入", "同步飞书到知识库",
            "飞书同步知识库", "飞书知识库同步",
        )
        if any(term in msg for term in kb_terms):
            return False

        # Explicitly DELEGATE minutes requests to feishu_minutes_reader
        minutes_triggers = ("飞书妙记", "妙记", "会议纪要", "会议记录", "读取妙记", "读妙记", "查看妙记", "打开妙记")
        if any(t in msg for t in minutes_triggers):
            return False
        # Also delegate raw minutes URLs
        if "feishu.cn/minutes/" in msg or "/minutes/" in msg:
            return False

        # Stay in context for follow-up when a doc is loaded
        if any(s.get("stage") == "doc_loaded" for s in _sessions.values()):
            return True

        return super().can_handle(message)

    async def execute(self, context: SkillContext) -> SkillResult:
        session_id = context.session_id or "default"
        msg = context.user_message.strip()

        await _helper.restore()
        session = _sessions.get(session_id)

        # Recover active doc-loaded session when session_id is lost
        if not session:
            for sid, s in _sessions.items():
                if s.get("stage") == "doc_loaded":
                    session = s
                    session_id = sid
                    break

        if self._is_exit(msg):
            await _helper.delete(session_id)
            return SkillResult(success=True, message="已退出飞书文档读取。")

        code = self._extract_code(msg)
        if code:
            return await self._handle_oauth_code(session_id, code)

        if session and session.get("stage") == "doc_loaded" and not self._looks_like_doc_source(msg):
            return await self._handle_loaded_doc_action(context, session_id, msg)

        source = self._extract_source(msg)
        if not source:
            await _helper.save(session_id, {"stage": "awaiting_doc_url"})
            return self._ask_for_doc_url()

        await _helper.save(session_id, {"stage": "reading_doc", "pending_url": source})
        user_token = self._extract_user_token(msg) or await FeishuTokenManager.get_valid_access_token()
        clean_source = self._remove_user_token(source)
        return await self._read_or_guide_auth(session_id, clean_source, user_token)

    def _ask_for_doc_url(self) -> SkillResult:
        return SkillResult(
            success=True,
            message=(
                "📄 **飞书文档助手** 已激活\n\n"
                "请发送你想读取的飞书文档或 Wiki URL，例如：\n"
                "`https://xxx.feishu.cn/wiki/xxxxx`\n"
                "`https://xxx.feishu.cn/docx/xxxxx`\n\n"
                "💡 如果是飞书妙记（会议纪要），请使用「飞书妙记」功能。\n\n"
                "读取成功后，你可以：\n"
                "- 📝 **总结** — 生成文档摘要\n"
                "- 🔑 **提取要点** — 按主题分组提取关键信息\n"
                "- 🔍 **分析/梳理** — 根据需求深度分析内容\n"
                "- 📊 **生成PPT大纲** — 基于文档内容制作演示文稿框架\n"
                "- 💾 **保存到知识库** — 将文档存入本地知识库以便后续检索"
            ),
            data={"skill": self.name, "stage": "awaiting_doc_url"},
        )

    async def _read_or_guide_auth(self, session_id: str, url: str, user_token: str | None) -> SkillResult:
        try:
            if user_token:
                result = await feishu_service.get_doc_content_debug(url, user_access_token=user_token)
            else:
                result = await feishu_service.get_doc_content_debug_with_fallback(url)
        except Exception as exc:
            return SkillResult(
                success=False,
                message=f"调用飞书 API 失败：{exc.__class__.__name__}: {str(exc) or '无详细错误文本'}",
                data={"skill": self.name, "stage": "error"},
            )

        if result.get("ok"):
            content = result.get("content") or ""
            await _helper.save(session_id, {
                "stage": "doc_loaded",
                "url": url,
                "result": self._safe_result(result),
                "content": content,
                "title": self._doc_title(result),
            })
            return SkillResult(
                success=True,
                message=self._format_result(result) + "\n\n---\n💡 你可以继续：**总结** · **提取要点** · **分析/梳理** · **生成PPT大纲** · **保存到知识库** · 或发送另一篇飞书文档。",
                data={"skill": self.name, "stage": "doc_loaded", "result": self._safe_result(result)},
            )

        if not user_token:
            _helper.cache[session_id] = {"stage": "awaiting_oauth_code", "pending_url": url}
            return self._guide_oauth(result)

        return SkillResult(
            success=False,
            message=self._failure_summary(result),
            data={"skill": self.name, "stage": "read_failed", "result": self._safe_result(result)},
        )

    # ── Follow-up actions ───────────────────────────────────────────

    async def _handle_loaded_doc_action(self, context: SkillContext, session_id: str, msg: str) -> SkillResult:
        session = _sessions.get(session_id) or {}
        content = session.get("content") or ""
        if not content:
            await _helper.delete(session_id)
            return SkillResult(success=True, message="当前没有保留的飞书文档内容。请重新发送飞书文档 URL。")

        if self._wants_save_to_kb(msg):
            return await self._save_current_doc_to_kb(session_id, session)
        if self._wants_ppt_outline(msg):
            return await self._generate_ppt_outline(session, msg)
        if self._wants_summary(msg):
            return await self._summarize_current_doc(session)
        if self._wants_key_points(msg):
            return await self._extract_key_points(session)
        if self._wants_analysis(msg):
            return await self._analyze_doc(session, msg)
        # Default: answer question about the document
        return await self._analyze_doc(session, msg)

    async def _summarize_current_doc(self, session: dict) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书文档"
        prompt = f"""请总结下面这篇飞书文档，输出：
1. 一句话结论
2. 核心要点
3. 关键背景/事实
4. 可执行建议

文档标题：{title}

文档内容：
{content[:60000]}"""
        try:
            response = await llm_service.chat(
                system_prompt="你是严谨的业务文档总结助手，输出简洁、结构清楚、不要编造信息。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000, temperature=0.2, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(response)
        except Exception as exc:
            return SkillResult(success=False, message=f"总结文档失败：{exc}")
        return SkillResult(success=True, message=text, data={"skill": self.name, "stage": "doc_loaded"})

    async def _extract_key_points(self, session: dict) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书文档"
        prompt = f"""请从下面飞书文档中提取关键要点。要求：
- 按主题分组
- 保留重要数据、名词、结论
- 不要添加文档中没有的信息

文档标题：{title}

文档内容：
{content[:60000]}"""
        try:
            response = await llm_service.chat(
                system_prompt="你是严谨的信息抽取助手。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000, temperature=0.2, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(response)
        except Exception as exc:
            return SkillResult(success=False, message=f"提取要点失败：{exc}")
        return SkillResult(success=True, message=text, data={"skill": self.name, "stage": "doc_loaded"})

    async def _generate_ppt_outline(self, session: dict, user_hint: str = "") -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书文档"
        hint_text = f"\n用户额外要求：{user_hint}" if user_hint and user_hint not in ("生成PPT大纲", "PPT大纲") else ""
        prompt = f"""你是一个资深的演示文稿策划专家。请根据下面这篇飞书文档的内容，生成一份专业的 PPT 大纲。

要求：
1. **封面**：给出 PPT 标题、副标题
2. **目录**：3-6 个章节标题
3. **每章内容**：每个章节包含 2-5 页，每页给出：
   - 页面标题
   - 核心要点（2-4 个 bullet points）
   - 建议的视觉呈现方式（图表、流程图、对比表等）
4. **总结页**：关键结论和下一步行动
5. 保留文档中的关键数据、案例、引用
6. 不要添加文档中没有的信息

文档标题：{title}
{hint_text}

文档内容：
{content[:60000]}"""
        try:
            response = await llm_service.chat(
                system_prompt="你是资深的演示文稿策划专家，输出专业、结构化、可直接用于制作PPT的大纲。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000, temperature=0.3, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(response)
        except Exception as exc:
            return SkillResult(success=False, message=f"生成 PPT 大纲失败：{exc}")
        return SkillResult(
            success=True,
            message=f"📊 **PPT 大纲已生成**（基于：{title}）\n\n{text}\n\n---\n💡 如需调整大纲或进入 PPT 制作流程，请告诉我。",
            data={"skill": self.name, "stage": "doc_loaded", "ppt_outline": text},
        )

    async def _analyze_doc(self, session: dict, user_question: str) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书文档"
        prompt = f"""请根据下面这篇飞书文档的内容，回答用户的问题或按要求进行分析。

要求：
- 严格基于文档内容，不要编造信息
- 如果文档中没有相关信息，诚实说明
- 引用文档中的具体内容作为依据
- 输出结构清晰，便于阅读

文档标题：{title}

文档内容：
{content[:60000]}

用户问题/要求：
{user_question}"""
        try:
            response = await llm_service.chat(
                system_prompt="你是严谨的文档分析助手。严格基于提供的文档内容回答问题，不编造信息。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000, temperature=0.2, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(response)
        except Exception as exc:
            return SkillResult(success=False, message=f"分析文档失败：{exc}")
        return SkillResult(success=True, message=text, data={"skill": self.name, "stage": "doc_loaded"})

    async def _save_current_doc_to_kb(self, session_id: str, session: dict) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书文档"
        url = session.get("url") or ""
        doc_id = hashlib.md5(url.encode()).hexdigest()[:12]

        from app.routes.knowledge import _load_feishu_import_records, _save_feishu_import_records
        records = _load_feishu_import_records()
        existing = records.get(url)
        if existing:
            try:
                await rag_service.delete_doc(doc_id)
            except Exception:
                pass

        metadata = {
            "source": title, "file_path": url, "doc_id": doc_id,
            "doc_type": "feishu", "session_id": session_id,
        }
        try:
            chunk_ids = await rag_service.index_text(content, metadata)
        except Exception as exc:
            return SkillResult(success=False, message=f"保存到知识库失败：{exc}", data={"skill": self.name, "stage": "doc_loaded"})

        records[url] = {"name": title, "url": url, "chunks": len(chunk_ids), "imported_at": time.time()}
        _save_feishu_import_records(records)

        action = "已更新" if existing else "已保存"
        extra = f"（之前 {existing['chunks']} → 现在 {len(chunk_ids)} 个分块）" if existing else ""
        return SkillResult(
            success=True,
            message=f"{action}到知识库：{title}\n\n写入分片数：{len(chunk_ids)}{extra}",
            data={"skill": self.name, "stage": "doc_loaded", "chunk_count": len(chunk_ids), "is_update": bool(existing)},
        )

    # ── OAuth ───────────────────────────────────────────────────────

    def _guide_oauth(self, result: dict) -> SkillResult:
        try:
            auth_url = FeishuTokenManager.build_oauth_url()
            auth_part = f"请打开下面的飞书授权链接：\n\n{auth_url}\n\n"
        except Exception as exc:
            auth_part = f"我没能自动生成授权链接，请检查后端是否配置了 FEISHU_OAUTH_REDIRECT_URI。\n错误：{exc}\n\n"

        return SkillResult(
            success=False,
            message=(
                "这篇飞书文档需要你的用户授权才能读取。\n\n"
                + auth_part
                + "授权完成后，飞书会跳转到回调页面。请把完整回调 URL 贴回来，或者只贴 code。\n\n"
                + "示例：\n"
                + "https://your-callback?code=abc123&state=knowledge_feishu_import\n\n"
                + "或：\n"
                + "code: abc123\n\n"
                + "💡 此授权与「知识库 → 飞书知识库导入」共用同一套 token。"
            ),
            data={"skill": self.name, "stage": "awaiting_oauth_code", "result": self._safe_result(result)},
        )

    async def _handle_oauth_code(self, session_id: str, code: str) -> SkillResult:
        token_data = await FeishuTokenManager.exchange_code(code)
        if not token_data:
            return SkillResult(
                success=False,
                message="授权交换失败。请确认 code 没有过期/用过，redirect_uri 与飞书后台完全一致，并重新授权。",
                data={"skill": self.name, "stage": "awaiting_oauth_code"},
            )

        access_token = token_data.get("access_token")
        pending_url = (_sessions.get(session_id) or {}).get("pending_url")
        if pending_url:
            return await self._read_or_guide_auth(session_id, pending_url, access_token)

        await _helper.save(session_id, {"stage": "awaiting_doc_url"})
        return SkillResult(
            success=True,
            message="授权成功，token 已保存到统一飞书授权文件（与知识库共享）。现在请发送你想读取的飞书文档 URL。",
            data={"skill": self.name, "stage": "awaiting_doc_url"},
        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _is_exit(self, msg: str) -> bool:
        normalized = msg.strip().lower().replace(" ", "")
        return len(normalized) <= 12 and normalized in {"退出", "返回", "不读了", "取消", "结束"}

    def _looks_like_doc_source(self, msg: str) -> bool:
        return "http" in msg or "feishu.cn" in msg or "docx/" in msg or "wiki/" in msg

    def _wants_summary(self, msg: str) -> bool:
        return any(k in msg for k in ("总结", "概括", "摘要", "summarize", "summary"))

    def _wants_key_points(self, msg: str) -> bool:
        return any(k in msg for k in ("要点", "重点", "关键点", "提取"))

    def _wants_save_to_kb(self, msg: str) -> bool:
        return any(k in msg for k in ("保存知识库", "存入知识库", "加入知识库", "写入知识库", "保存到知识库"))

    def _wants_ppt_outline(self, msg: str) -> bool:
        return any(k in msg for k in ("PPT大纲", "ppt大纲", "幻灯片大纲", "演示文稿大纲", "生成大纲", "PPT框架",
                                      "ppt outline", "slide outline", "生成PPT", "制作PPT", "做PPT",
                                      "汇报PPT", "提案PPT", "培训PPT"))

    def _wants_analysis(self, msg: str) -> bool:
        return any(k in msg for k in ("分析", "梳理", "整理", "提炼", "归纳", "对比", "归纳总结"))

    def _extract_code(self, msg: str) -> str | None:
        parsed = urlparse(msg.strip())
        if parsed.query:
            code = parse_qs(parsed.query).get("code", [None])[0]
            if code:
                return code.strip()
        match = re.search(r"(?:^|\b)code\s*[:：=]\s*([A-Za-z0-9._-]+)", msg, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        if len(msg.strip()) > 10 and re.fullmatch(r"[A-Za-z0-9._-]+", msg.strip()) and not msg.startswith("http"):
            return msg.strip()
        return None

    def _extract_source(self, msg: str) -> str:
        url_match = re.search(r"https?://[^\s)）>]+", msg)
        if url_match:
            url = url_match.group(0).strip().strip("\"'<>").rstrip(".,;:!?）)")
            return url
        return ""

    def _extract_user_token(self, msg: str) -> str | None:
        for pattern in (r"userAccessToken\s*[:：]\s*([^\s]+)", r"user_access_token\s*[:：]\s*([^\s]+)"):
            match = re.search(pattern, msg, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _remove_user_token(self, text: str) -> str:
        for pattern in (r"userAccessToken\s*[:：]\s*[^\s]+", r"user_access_token\s*[:：]\s*[^\s]+"):
            text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
        return text.strip()

    def _doc_title(self, result: dict) -> str:
        node = result.get("wiki_node") or {}
        return node.get("title") or "飞书文档"

    def _format_result(self, result: dict) -> str:
        content = result.get("content") or ""
        if content:
            preview = content[:DISPLAY_LIMIT]
            remaining = len(content) - len(preview)
            suffix = f"\n\n[内容较长，已展示前 {DISPLAY_LIMIT} 字，剩余 {remaining} 字未在聊天中展开]" if remaining > 0 else ""
            title = self._doc_title(result)
            return f"飞书文档读取成功：{title}\n\n正文长度：{len(content)} 字符\n\n{preview}{suffix}"
        if result.get("error"):
            return f"没有读取到正文。原因：{result['error']}"
        if result.get("fallback") and result["fallback"].get("used"):
            return "没有读取到正文。已尝试应用身份和用户授权，但仍未成功。"
        return "没有读取到正文。可能是应用没有文档权限，或文档类型/链接不正确。"

    def _failure_summary(self, result: dict) -> str:
        lines = ["没有读取到正文。已尝试应用身份和用户授权，但仍未成功。", "", "排查信息："]
        fb = result.get("fallback") or {}
        if fb:
            lines.append(f"- 回退策略：{fb.get('strategy')}，是否回退到用户 token：{'是' if fb.get('used') else '否'}")
            for item in fb.get("tenant_attempts") or []:
                lines.append(f"  - {item.get('label')}: HTTP {item.get('http_status')}, code={item.get('code')}, msg={item.get('msg')}")
        if result.get("warning"):
            lines.append(f"- 当前提示：{result.get('warning')}")
        attempts = result.get("attempts") or []
        if attempts:
            lines.append("- 当前认证方式尝试：")
            for item in attempts:
                lines.append(f"  - {item.get('label')}: HTTP {item.get('http_status')}, code={item.get('code')}, msg={item.get('msg')}")
        lines.extend([
            "", "下一步建议：",
            "1. 确认你本人能在浏览器打开该飞书文档。",
            "2. 如果是 wiki 链接，确认 token 授权 scope 完整。",
            "3. 如果 token 可能过期，请重新授权。",
        ])
        return "\n".join(lines)

    def _safe_result(self, result: dict) -> dict:
        copied = dict(result)
        content = copied.get("content") or ""
        copied["content_preview"] = content[:DISPLAY_LIMIT]
        copied["content_length"] = len(content)
        copied.pop("content", None)
        return copied
