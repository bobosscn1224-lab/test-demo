"""Feishu Minutes (飞书妙记) reader skill — standalone, single-purpose.

Reads Feishu meeting recordings: basic info + full transcript.
Uses shared FeishuTokenManager for OAuth tokens.
Session state persisted to SQLite, survives uvicorn reloads.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time

from app.services.feishu_service import feishu_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.feishu_token_manager import FeishuTokenManager
from app.skills.base import BaseSkill, SkillContext, SkillResult
from app.core.session_store import session_store

logger = logging.getLogger(__name__)

SKILL_NAME = "feishu_minutes_reader"
_sessions: dict[str, dict] = {}
DISPLAY_LIMIT = 50000


async def _restore_sessions() -> int:
    """Load active sessions from DB into memory cache."""
    active = await session_store.find_by_stage(SKILL_NAME, "minutes_loaded")
    for s in active:
        sid = s.pop("_session_id", "")
        s.pop("_stage", None)
        s.pop("_updated_at", None)
        if sid and sid not in _sessions:
            _sessions[sid] = s
    return len(active)


async def _save_session(session_id: str, data: dict) -> None:
    stage = data.get("stage", "")
    _sessions[session_id] = data
    db_data = {k: v for k, v in data.items() if k != "content"}
    db_data["content_length"] = len(data.get("content") or "")
    try:
        await session_store.set(session_id, SKILL_NAME, stage, db_data)
    except Exception as exc:
        logger.warning(f"_save_session failed: {exc}")


async def _delete_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
    try:
        await session_store.delete(session_id, SKILL_NAME)
    except Exception as exc:
        logger.warning(f"_delete_session failed: {exc}")


class FeishuMinutesReaderSkill(BaseSkill):
    name = SKILL_NAME
    description = "读取飞书妙记（会议纪要），获取转写文本并进行总结、分析、提取要点。"
    triggers = [
        "飞书妙记", "妙记", "会议纪要", "会议记录",
        "读取妙记", "读妙记", "查看妙记", "打开妙记",
    ]
    keywords = ["minutes", "feishu.cn/minutes", "妙记", "飞书妙记"]

    def can_handle(self, message: str) -> bool:
        msg = message.lower()
        # Keyword/trigger match
        if super().can_handle(message):
            return True
        # Active session → keep context for follow-up questions
        if any(s.get("stage") == "minutes_loaded" for s in _sessions.values()):
            return True
        # Raw minutes URL
        if "feishu.cn/minutes/" in msg or "minutes/" in msg:
            return True
        return False

    async def execute(self, context: SkillContext) -> SkillResult:
        session_id = context.session_id or "default"
        msg = context.user_message.strip()
        session = _sessions.get(session_id)

        if not _sessions:
            n = await _restore_sessions()
            if n > 0:
                session = _sessions.get(session_id)

        # Recover active session when session_id is lost
        if not session:
            for sid, s in _sessions.items():
                if s.get("stage") == "minutes_loaded":
                    session = s
                    session_id = sid
                    break

        if self._is_exit(msg):
            await _delete_session(session_id)
            return SkillResult(success=True, message="已退出妙记阅读。发送新的妙记链接可以重新开始。")

        # Already have loaded minutes → handle follow-up action
        if session and session.get("stage") == "minutes_loaded":
            return await self._handle_loaded(context, session_id, msg)

        # Extract URL
        url = self._extract_url(msg)
        if not url:
            await _save_session(session_id, {"stage": "awaiting_url"})
            return SkillResult(success=True, message=self._help_message())

        return await self._read_minutes(session_id, url)

    # ── Read ─────────────────────────────────────────────────────────

    async def _read_minutes(self, session_id: str, url: str) -> SkillResult:
        user_token = await FeishuTokenManager.get_valid_access_token()

        try:
            if user_token:
                result = await feishu_service.get_doc_content_debug(url, user_access_token=user_token)
            else:
                result = await feishu_service.get_doc_content_debug_with_fallback(url)
        except Exception as exc:
            return SkillResult(
                success=False,
                message=f"调用飞书 API 失败：{exc.__class__.__name__}: {str(exc) or '无详细错误文本'}",
            )

        if result.get("ok"):
            content = result.get("content") or ""
            title = (result.get("minute_info") or {}).get("title") or "飞书妙记"
            await _save_session(session_id, {
                "stage": "minutes_loaded", "url": url,
                "content": content, "title": title,
            })
            preview = content[:DISPLAY_LIMIT]
            remaining = len(content) - len(preview)
            suffix = f"\n\n[内容较长，已展示前 {DISPLAY_LIMIT} 字，剩余 {remaining} 字未展开]" if remaining > 0 else ""
            return SkillResult(
                success=True,
                message=(
                    f"✅ 妙记读取成功：**{title}**\n\n"
                    f"正文长度：{len(content)} 字符\n\n"
                    f"{preview}{suffix}\n\n---\n"
                    "💡 你可以继续：**总结** · **提取要点** · **分析/提问** · "
                    "**生成PPT大纲** · **保存到知识库** · 或发送另一篇妙记。"
                ),
                data={"stage": "minutes_loaded", "title": title},
            )

        if user_token:
            return SkillResult(
                success=False,
                message=(
                    "读取妙记失败。可能原因：\n"
                    "1. 当前用户 token 缺少妙记权限，需要重新授权\n"
                    "2. 妙记链接不正确\n"
                    "3. 该妙记未完成转写\n\n"
                    "请确认链接正确，或发送「飞书授权」重新授权。"
                ),
            )

        return SkillResult(
            success=False,
            message=(
                "读取妙记需要飞书用户授权。\n\n"
                "请发送 **飞书授权** 获取授权链接，\n"
                "或在前端知识库页面完成飞书授权后再试。"
            ),
        )

    # ── Follow-up actions ───────────────────────────────────────────

    async def _handle_loaded(self, context: SkillContext, session_id: str, msg: str) -> SkillResult:
        session = _sessions.get(session_id) or {}
        content = session.get("content") or ""

        url = self._extract_url(msg)
        if url:
            return await self._read_minutes(session_id, url)

        if not content:
            await _delete_session(session_id)
            return SkillResult(success=True, message="当前没有保留的妙记内容。请发送飞书妙记链接。")

        if self._wants_summary(msg):
            return await self._summarize(session)
        if self._wants_key_points(msg):
            return await self._extract_key_points(session)
        if self._wants_ppt(msg):
            return await self._ppt_outline(session, msg)
        if self._wants_save_kb(msg):
            return await self._save_to_kb(session_id, session)

        return await self._answer_question(session, msg)

    async def _summarize(self, session: dict) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书妙记"
        prompt = (
            "请总结下面这篇会议纪要，输出：\n"
            "1. 一句话结论\n2. 核心要点（3-5条）\n"
            "3. 关键决策和行动项\n4. 参会人员（如有提及）\n\n"
            f"会议标题：{title}\n\n会议内容：\n{content[:60000]}"
        )
        try:
            resp = await llm_service.chat(
                system_prompt="你是严谨的会议总结助手，输出简洁、结构清楚、不编造信息。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000, temperature=0.2, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(resp)
        except Exception as exc:
            return SkillResult(success=False, message=f"总结失败：{exc}")
        return SkillResult(success=True, message=text, data={"stage": "minutes_loaded"})

    async def _extract_key_points(self, session: dict) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书妙记"
        prompt = (
            "请从下面会议纪要中提取关键要点。要求：\n"
            "- 按主题分组\n- 保留重要数据、名词、结论\n"
            "- 不要添加内容中没有的信息\n\n"
            f"会议标题：{title}\n\n会议内容：\n{content[:60000]}"
        )
        try:
            resp = await llm_service.chat(
                system_prompt="你是严谨的信息抽取助手。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000, temperature=0.2, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(resp)
        except Exception as exc:
            return SkillResult(success=False, message=f"提取要点失败：{exc}")
        return SkillResult(success=True, message=text, data={"stage": "minutes_loaded"})

    async def _ppt_outline(self, session: dict, user_hint: str = "") -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书妙记"
        hint = f"\n用户额外要求：{user_hint}" if user_hint and "PPT" not in user_hint else ""
        prompt = (
            "你是一个资深的演示文稿策划专家。请根据下面会议纪要的内容，生成一份专业的 PPT 大纲。\n\n"
            "要求：\n1. **封面**：PPT 标题、副标题\n2. **目录**：3-6 个章节标题\n"
            "3. **每章内容**：每个章节 2-5 页，每页给出标题、要点、建议视觉形式\n"
            "4. **总结页**：关键结论和下一步行动\n"
            "5. 保留会议中的关键数据、案例、引用\n6. 不要添加会议中没有的信息\n\n"
            f"会议标题：{title}{hint}\n\n会议内容：\n{content[:60000]}"
        )
        try:
            resp = await llm_service.chat(
                system_prompt="你是资深的演示文稿策划专家，输出专业、结构化的大纲。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000, temperature=0.3, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(resp)
        except Exception as exc:
            return SkillResult(success=False, message=f"生成PPT大纲失败：{exc}")
        return SkillResult(
            success=True,
            message=f"📊 **PPT 大纲已生成**（基于：{title}）\n\n{text}",
            data={"stage": "minutes_loaded"},
        )

    async def _answer_question(self, session: dict, question: str) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书妙记"
        prompt = (
            "请根据下面会议纪要的内容，回答用户的问题。\n"
            "要求：\n- 严格基于会议内容，不要编造信息\n"
            "- 如果会议中没有相关信息，诚实说明\n"
            "- 引用会议中的具体内容作为依据\n\n"
            f"会议标题：{title}\n\n会议内容：\n{content[:60000]}\n\n"
            f"用户问题：{question}"
        )
        try:
            resp = await llm_service.chat(
                system_prompt="你是严谨的会议分析助手。严格基于提供的会议内容回答问题，不编造信息。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000, temperature=0.2, thinking={"type": "disabled"},
            )
            text = self.extract_text_from_llm_response(resp)
        except Exception as exc:
            return SkillResult(success=False, message=f"分析失败：{exc}")
        return SkillResult(success=True, message=text, data={"stage": "minutes_loaded"})

    async def _save_to_kb(self, session_id: str, session: dict) -> SkillResult:
        content = session.get("content") or ""
        title = session.get("title") or "飞书妙记"
        url = session.get("url") or ""
        doc_id = hashlib.md5(url.encode()).hexdigest()[:12]

        await rag_service.initialize()
        metadata = {
            "source": title, "file_path": url,
            "doc_id": doc_id, "doc_type": "feishu_minutes",
        }
        try:
            chunk_ids = await rag_service.index_text(content, metadata)
        except Exception as exc:
            return SkillResult(success=False, message=f"保存失败：{exc}")

        return SkillResult(
            success=True,
            message=f"已保存到知识库：{title}\n写入分片数：{len(chunk_ids)}",
            data={"stage": "minutes_loaded"},
        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _help_message(self) -> str:
        return (
            "🎙️ **飞书妙记助手** 已激活\n\n"
            "请发送飞书妙记链接，例如：\n"
            "`https://xxx.feishu.cn/minutes/xxxxx`\n\n"
            "读取成功后，你可以：\n"
            "- 📝 **总结** — 生成会议摘要\n"
            "- 🔑 **提取要点** — 按主题分组\n"
            "- 💬 **提问** — 基于会议内容回答任何问题\n"
            "- 📊 **生成PPT大纲** — 制作演示文稿框架\n"
            "- 💾 **保存到知识库** — 存入本地知识库\n"
            "发送 **退出** 结束妙记阅读。"
        )

    @staticmethod
    def _is_exit(msg: str) -> bool:
        norm = msg.strip().lower().replace(" ", "")
        return len(norm) <= 12 and norm in {"退出", "返回", "不读了", "取消", "结束"}

    @staticmethod
    def _extract_url(msg: str) -> str:
        m = re.search(r"https?://[^\s)）>]+", msg)
        if not m:
            return ""
        return m.group(0).strip().strip("\"'<>").rstrip(".,;:!?）)")

    def _wants_summary(self, msg: str) -> bool:
        return any(k in msg for k in ("总结", "概括", "摘要", "summarize", "summary"))

    def _wants_key_points(self, msg: str) -> bool:
        return any(k in msg for k in ("要点", "重点", "关键点", "提取"))

    def _wants_ppt(self, msg: str) -> bool:
        return any(k in msg for k in ("PPT", "ppt", "大纲", "幻灯片", "演示文稿"))

    def _wants_save_kb(self, msg: str) -> bool:
        return any(k in msg for k in ("保存知识库", "存入知识库", "保存到知识库", "加入知识库"))
