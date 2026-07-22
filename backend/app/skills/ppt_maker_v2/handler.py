"""PPT Maker v2 — streamlined multi-turn PPT creation skill.

6 stages: menu → outline → collage → pages → pptx → completed
4 entries: upload docs / direct outline / upload collage / direct image

Session persistence via SkillSessionHelper + SQLite ensures survival
across server restarts. The routing system (chat.py) calls restore() before
checking _sessions to rehydrate sessions from DB.
"""
from __future__ import annotations

import logging

from app.skills.base import BaseSkill, SkillContext, SkillResult
from app.core.skill_session import SkillSessionHelper
from .constants import SKILL_NAME, TRIGGERS, KEYWORDS, EXIT_WORDS, ENTRY_MENU
from .stages import menu, outline, collage, pages, pptx_gen, briefing
from . import image_gen

logger = logging.getLogger(__name__)

_sessions: dict[str, dict] = {}
_helper = SkillSessionHelper(SKILL_NAME, _sessions)


class PPTMakerSkill(BaseSkill):
    name = SKILL_NAME
    description = "根据用户输入、上传文档或PPT大纲制作专业PPT。支持大纲→缩略图→逐页高清图→PPTX全流程。"
    triggers = TRIGGERS
    keywords = KEYWORDS

    # ── Main entry ────────────────────────────────────────────────

    async def execute(self, context: SkillContext) -> SkillResult:
        msg = context.user_message.strip()
        sid = context.session_id or "default"

        await _helper.restore()

        if self._is_exit(msg):
            await _helper.delete(sid)
            return SkillResult(success=True, message="已退出 PPT 制作。可以发送「做PPT」重新开始。")

        session = _sessions.get(sid)
        if not session:
            return await self._start(sid)

        stage = session.get("stage", "")
        result = await self._route_stage(stage, context, session, sid)

        # Persist after every state change
        current = _sessions.get(sid)
        if current:
            await _helper.save(sid, current)

        return result

    async def execute_stream(self, context: SkillContext):
        """Streaming entry — for collage and page generation stages."""
        msg = context.user_message.strip()
        sid = context.session_id or "default"

        await _helper.restore()

        session = _sessions.get(sid)
        if not session:
            result = await self._start(sid)
            yield result
            return

        stage = session.get("stage", "")

        # Collage generation (step 2) — fresh start
        if stage == "collage_confirm" and self._is_start(msg):
            async for item in collage.generate_stream(session, _sessions, sid):
                yield item
            await _helper.save(sid, _sessions.get(sid, {}))
            return

        # Collage generation — RESUME after interruption
        if stage == "collage_generating" and self._is_start(msg):
            existing = session.get("visual_collages", [])
            yield f"检测到之前已生成 {len(existing)}/3 版方案，继续生成剩余方案...\n"
            async for item in collage.resume_stream(session, _sessions, sid):
                yield item
            await _helper.save(sid, _sessions.get(sid, {}))
            return

        # Single-plan regeneration with modifications (from collage_choice)
        if stage == "collage_regenerating":
            async for item in collage.regenerate_single_stream(session, _sessions, sid):
                yield item
            await _helper.save(sid, _sessions.get(sid, {}))
            return

        # Collage choice with single-plan regeneration request (handled via streaming)
        if stage == "collage_choice":
            target_label, _mods = collage._parse_single_regenerate(msg)
            if target_label:
                sessions_dict = _sessions
                sessions_dict[sid] = {
                    **session,
                    "regenerate_target": target_label,
                    "regenerate_modifications": _mods,
                    "stage": "collage_regenerating",
                }
                async for item in collage.regenerate_single_stream(sessions_dict[sid], _sessions, sid):
                    yield item
                await _helper.save(sid, _sessions.get(sid, {}))
                return

        # Page generation (step 3) — fresh start
        if stage == "pages_confirm" and self._is_start(msg):
            async for item in pages.generate_stream(session, _sessions, sid):
                yield item
            await _helper.save(sid, _sessions.get(sid, {}))
            return

        # Page generation — RESUME after interruption
        if stage == "pages_generating" and self._is_start(msg):
            existing_pages = session.get("single_pages", [])
            outline = str(session.get("outline", ""))
            total = len(pages._extract_slides(outline))
            yield f"检测到之前已生成 {len(existing_pages)}/{total} 页，继续生成剩余页面...\n"
            async for item in pages.resume_stream(session, _sessions, sid):
                yield item
            await _helper.save(sid, _sessions.get(sid, {}))
            return

        # Fallback: non-streaming execute
        result = await self.execute(context)
        yield result

    # ── Stage router ──────────────────────────────────────────────

    async def _route_stage(self, stage: str, context: SkillContext, session: dict, sid: str) -> SkillResult:
        """Route to the appropriate stage handler."""
        handlers = {
            "menu":              lambda: menu.handle(context, session, _sessions, sid),
            "briefing":          lambda: briefing.handle(context, session, _sessions, sid),
            "briefing_confirm":  lambda: briefing.handle_confirm(context, session, _sessions, sid),
            "outline":           lambda: outline.handle_outline(context, session, _sessions, sid),
            "outline_confirm":   lambda: outline.handle_confirm(context, session, _sessions, sid),
            "outline_direct":    lambda: outline.handle_outline_direct(context, session, _sessions, sid),
            "collage_confirm":   lambda: collage.handle_collage_confirm(context, session, _sessions, sid),
            "collage_choice":    lambda: collage.handle_visual_choice(context, session, _sessions, sid),
            "collage_generating": lambda: self._handle_interrupted(context.user_message, session, sid, "collage"),
            "collage_regenerating": lambda: self._handle_single_regen_fallback(context, session, sid),
            "collage_upload":    lambda: pages.handle_collage_upload(context, session, _sessions, sid),
            "pages_confirm":     lambda: pages.handle_pages_confirm(context, session, _sessions, sid),
            "pages_generating":  lambda: self._handle_interrupted(context.user_message, session, sid, "pages"),
            "pptx_scope":        lambda: pptx_gen.handle(context, session, _sessions, sid),
            "pptx_direct":       lambda: pages.handle_pptx_direct(context, session, _sessions, sid),
            "completed":         lambda: self._start(sid),
        }

        handler = handlers.get(stage)
        if handler:
            return await handler()

        # Unknown stage — restart
        return await self._start(sid)

    # ── Entry point ───────────────────────────────────────────────

    async def _start(self, sid: str) -> SkillResult:
        """Show the entry menu."""
        _sessions[sid] = {"stage": "menu"}
        await _helper.save(sid, _sessions[sid])
        return SkillResult(
            success=True,
            message=f"欢迎使用 PPT 制作技能！\n\n{ENTRY_MENU}",
            data={"skill": self.name, "stage": "menu"},
        )

    # ── Interruption recovery ────────────────────────────────────

    async def _handle_interrupted(self, msg: str, session: dict, sid: str, step: str) -> SkillResult:
        """Show recovery info when user returns after interruption."""
        # Handle "重新生成" — clear partial results and restart stage
        if any(w in msg for w in ["重新生成", "重做", "从头开始", "重新开始", "重来"]):
            if step == "collage":
                session.pop("visual_collages", None)
                _sessions[sid] = {**session, "stage": "collage_confirm"}
                return SkillResult(
                    success=True,
                    message="已清除部分结果。请回复「开始」重新生成三版缩略图。",
                    data={"skill": self.name, "stage": "collage_confirm"},
                )
            else:
                session.pop("single_pages", None)
                _sessions[sid] = {**session, "stage": "pages_confirm"}
                return SkillResult(
                    success=True,
                    message="已清除部分结果。请回复「开始」重新逐页生成。",
                    data={"skill": self.name, "stage": "pages_confirm"},
                )

        if step == "collage":
            existing = session.get("visual_collages", [])
            labels = [c["label"] for c in existing]
            done = f"已完成方案 {', '.join(labels)}" if labels else "尚未生成任何方案"
            return SkillResult(
                success=True,
                message=(
                    f"⚠️ 上次生成被中断。{done}。\n\n"
                    f"回复「**继续**」从断点续传，或回复「**重新生成**」从头开始。"
                ),
                data={"skill": self.name, "stage": "collage_generating"},
            )
        else:  # pages
            existing = session.get("single_pages", [])
            outline = str(session.get("outline", ""))
            total = len(pages._extract_slides(outline))
            done = f"已完成 {len(existing)}/{total} 页" if existing else "尚未生成任何页面"
            return SkillResult(
                success=True,
                message=(
                    f"⚠️ 上次生成被中断。{done}。\n\n"
                    f"回复「**继续**」从断点续传，或回复「**重新生成**」从头开始。"
                ),
                data={"skill": self.name, "stage": "pages_generating"},
            )

    async def _handle_single_regen_fallback(self, context: SkillContext, session: dict, sid: str) -> SkillResult:
        """Non-streaming fallback for single-plan regeneration — tells user to wait."""
        from .stages import collage as _collage
        target = session.get("regenerate_target", "")
        mods = session.get("regenerate_modifications", "")
        if not target or not mods:
            _sessions[sid] = {**session, "stage": "collage_choice"}
            return SkillResult(
                success=True,
                message="未识别到修改意见。请用「方案 A 重新生成，具体的修改意见」格式输入。",
                data={"skill": self.name, "stage": "collage_choice"},
            )
        return SkillResult(
            success=True,
            message=f"正在重新生成方案 {target}（修改意见：{mods}）...\n\n请稍候，此过程需要几分钟。如果长时间无响应，请刷新页面后发送「继续」。",
            data={"skill": self.name, "stage": "collage_regenerating"},
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _is_exit(self, msg: str) -> bool:
        m = msg.strip().lower().replace(" ", "")
        if len(m) > 12:
            return False
        return any(w.lower().replace(" ", "") == m for w in EXIT_WORDS)

    def _is_start(self, msg: str) -> bool:
        m = msg.strip().lower().replace(" ", "")
        if len(m) > 10:
            return False
        return any(w in m for w in ["开始", "继续", "确认", "可以", "ok", "yes", "好", "行", "确定"])

    # Legacy compatibility — unused but avoid AttributeError
    def _is_confirm(self, msg: str) -> bool:
        return self._is_start(msg)
    def _imagegen_exe(self):
        from .image_gen import find_cli_exe; return find_cli_exe()
    def _imagegen_env(self):
        from .image_gen import _cli_env; return _cli_env()
    async def _run_imagegen(self, exe, prompt, out_path, timeout):
        return await image_gen.generate(
            prompt, out_path, interaction_name="ppt_slide", timeout=timeout,
        )
