from __future__ import annotations

import asyncio
import os
import re
import subprocess
import uuid

from app.config import settings
from app.services.llm_service import llm_service
from app.skills.base import BaseSkill, SkillContext, SkillResult
from app.utils.file_parser import parse_file_sync


_sessions: dict[str, dict] = {}

EXIT_WORDS = {
    "退出",
    "返回",
    "不做了",
    "停止",
    "结束",
    "取消",
    "先不做",
    "退出skill",
    "退出 skill",
}

CONFIRM_WORDS = {"确认", "可以", "没问题", "通过", "就这样", "ok", "okay", "yes", "确定", "开始", "继续"}


class PPTMakerSkill(BaseSkill):
    name = "ppt_maker"
    description = "根据用户输入、上传文档、PPT大纲或视觉稿制作PPT，支持大纲、缩略图、逐页高清图和PPTX输出。"
    triggers = ["做PPT", "制作PPT", "生成PPT", "帮我做PPT", "PPT", "ppt", "幻灯片", "演示文稿"]
    keywords = ["ppt", "powerpoint", "slides", "deck", "提案", "路演", "汇报材料", "课件"]

    async def execute(self, context: SkillContext) -> SkillResult:
        msg = context.user_message.strip()
        session_id = context.session_id or "default"

        if self._is_exit(msg):
            _sessions.pop(session_id, None)
            return SkillResult(success=True, message="好的，已退出当前 PPT 制作流程。")

        session = _sessions.get(session_id)
        if not session:
            return self._show_entry_menu(session_id)

        stage = session.get("stage")
        if stage == "awaiting_entry_choice":
            return await self._handle_entry_choice(context, session_id)
        if stage == "awaiting_content":
            return await self._handle_content(context, session_id)
        if stage == "awaiting_outline_confirm":
            return await self._handle_outline_confirm(context, session_id)
        if stage == "awaiting_outline_for_visual":
            return await self._handle_outline_for_visual(context, session_id)
        if stage == "awaiting_collage_for_pages":
            return await self._handle_collage_for_pages(context, session_id)
        if stage == "awaiting_page_info_for_step3":
            return await self._handle_page_info_for_step3(context, session_id)
        if stage == "awaiting_page_image_for_editable_ppt":
            return await self._handle_page_image_for_editable_ppt(context, session_id)
        if stage == "visual_direction":
            return await self._handle_visual_direction_confirm(context, session_id)
        if stage == "entry3_ready":
            return await self._handle_entry3_ready(context, session_id)
        if stage == "awaiting_visual_choice":
            return self._handle_visual_choice(context, session_id)
        if stage == "awaiting_step3_start":
            return self._ack_step3_start(session_id)
        if stage in {"generating_visual_direction", "generating_single_pages"}:
            return self._return_generation_status(session_id)
        if stage == "awaiting_editable_ppt_scope":
            return self._handle_editable_ppt_scope(context, session_id)

        return self._show_entry_menu(session_id)

    async def execute_stream(self, context: SkillContext):
        session_id = context.session_id or "default"
        session = _sessions.get(session_id)

        if session and session.get("stage") == "awaiting_outline_for_visual":
            source_text = await self._collect_source_text(context)
            if not self._has_enough_content(context.user_message, source_text):
                yield await self._handle_outline_for_visual(context, session_id)
                return
            _sessions[session_id] = {**session, "stage": "visual_direction", "outline": source_text}
            yield "收到 PPT 大纲，开始从第 2 步生成三版视觉缩略图。\n\n"
            async for item in self._run_step2_visual_collages(session_id, source_text):
                yield item
            return

        if session and session.get("stage") == "visual_direction" and self._is_confirm(context.user_message):
            outline = str(session.get("outline") or "").strip()
            if not outline:
                yield SkillResult(success=False, message="第二步出错了：没有找到已确认的大纲内容。请重新提供大纲后再继续。")
                return
            yield "收到，开始从第 2 步生成三版 PPT 视觉缩略图。\n\n"
            async for item in self._run_step2_visual_collages(session_id, outline):
                yield item
            return

        if session and session.get("stage") == "entry3_ready" and self._is_confirm(context.user_message):
            outline = str(session.get("outline") or "").strip()
            if not outline:
                yield SkillResult(success=False, message="第 3 步出错了：没有找到页面信息。请重新提供页数和标题。")
                return
            yield "收到，跳过第 2 步，直接进入第 3 步：基于上传的缩略图逐页生成高清单页视觉稿。\n\n"
            await asyncio.sleep(0.1)
            async for item in self._start_step3_single_pages(session_id, "REF"):
                yield item
            return

        if session and session.get("stage") == "awaiting_outline_confirm" and self._is_confirm(context.user_message):
            outline = str(session.get("outline") or "").strip()
            if not outline:
                yield SkillResult(
                    success=False,
                    message="第二步出错了：没有找到已确认的大纲内容。请重新上传资料或重新生成大纲后再确认。",
                    data={"skill": self.name, "stage": "error"},
                )
                return
            yield "收到，大纲已确认。\n\n"
            async for item in self._run_step2_visual_collages(session_id, outline):
                yield item
            return

        if session and session.get("stage") == "awaiting_visual_choice":
            choice = self._parse_visual_choice(context.user_message)
            if choice:
                yield f"已接收到你的选择：方案 {choice}。\n"
                yield "正在进入第 3 步：逐页生成高清 16:9 单页 PPT 视觉稿。\n\n"
                await asyncio.sleep(0.1)
                async for item in self._start_step3_single_pages(session_id, choice):
                    yield item
                return
            yield self._handle_visual_choice(context, session_id)
            return

        if session and session.get("stage") == "awaiting_step3_start":
            choice = self._selected_visual_choice(session)
            if choice:
                yield f"已接收到第 3 步启动指令，继续使用方案 {choice}。\n"
                yield "正在进入第 3 步：逐页生成高清 16:9 单页 PPT 视觉稿。\n\n"
                await asyncio.sleep(0.1)
                async for item in self._start_step3_single_pages(session_id, choice):
                    yield item
                return
            yield SkillResult(
                success=False,
                message="第 3 步无法启动：没有找到已选择的视觉方案。请重新选择方案 A、B 或 C。",
                data={"skill": self.name, "stage": "awaiting_visual_choice"},
            )
            return

        result = await self.execute(context)
        yield result

    def _is_exit(self, msg: str) -> bool:
        normalized = msg.strip().lower().replace(" ", "")
        return len(normalized) <= 12 and normalized in {w.lower().replace(" ", "") for w in EXIT_WORDS}

    def _is_confirm(self, msg: str) -> bool:
        normalized = msg.strip().lower()
        return len(normalized) <= 12 and any(word in normalized for word in CONFIRM_WORDS)

    def _show_entry_menu(self, session_id: str) -> SkillResult:
        _sessions[session_id] = {"stage": "awaiting_entry_choice"}
        return SkillResult(
            success=True,
            message=(
                "请选择本次 PPT 制作的入口：\n\n"
                "1. 上传文档或直接输入内容，生成大纲制作 PPT（走第 1-2-3-4 步）\n"
                "2. 直接提供 PPT 大纲，开始制作 PPT 缩略图（从第 2 步开始）\n"
                "3. 直接提供 PPT 整体详细缩略图，开始输出分页高清图片风格图（从第 3 步开始）\n"
                "4. 提供某一页高清 PPT 风格图，制作可编辑 PPT（直接第 4 步）\n\n"
                "请回复数字 1、2、3 或 4。"
            ),
            data={"skill": self.name, "stage": "awaiting_entry_choice"},
        )

    def _parse_entry_choice(self, msg: str) -> str | None:
        normalized = msg.strip().lower()
        compact = normalized.replace(" ", "")
        mapping = {
            "1": "1", "选1": "1", "选择1": "1", "第一项": "1", "第1项": "1",
            "2": "2", "选2": "2", "选择2": "2", "第二项": "2", "第2项": "2",
            "3": "3", "选3": "3", "选择3": "3", "第三项": "3", "第3项": "3",
            "4": "4", "选4": "4", "选择4": "4", "第四项": "4", "第4项": "4",
        }
        if compact in mapping:
            return mapping[compact]
        if "生成大纲" in normalized or "上传文档" in normalized or "直接输入内容" in normalized:
            return "1"
        if "ppt大纲" in compact or "ppt的大纲" in compact:
            return "2"
        if "整体详细缩略图" in normalized or "分页高清" in normalized or "高清图片风格图" in normalized:
            return "3"
        if "可编辑ppt" in compact or "可编辑pptx" in compact or "某一页高清" in normalized:
            return "4"
        return None

    async def _handle_entry_choice(self, context: SkillContext, session_id: str) -> SkillResult:
        choice = self._parse_entry_choice(context.user_message)
        if not choice:
            return SkillResult(success=True, message="请回复数字 1、2、3 或 4，选择本次 PPT 制作入口。")

        if choice == "1":
            _sessions[session_id] = {"stage": "awaiting_content", "entry_choice": "1"}
            return SkillResult(
                success=True,
                message="已选择入口 1。请上传用于制作 PPT 的文档，或直接输入内容、主题、受众和制作要求。",
                data={"skill": self.name, "stage": "awaiting_content"},
            )
        if choice == "2":
            _sessions[session_id] = {"stage": "awaiting_outline_for_visual", "entry_choice": "2"}
            return SkillResult(
                success=True,
                message="已选择入口 2。请粘贴已确认的 PPT 大纲和逐页内容，或上传包含大纲的文档。",
                data={"skill": self.name, "stage": "awaiting_outline_for_visual"},
            )
        if choice == "3":
            _sessions[session_id] = {"stage": "awaiting_collage_for_pages", "entry_choice": "3"}
            return SkillResult(
                success=True,
                message="已选择入口 3。请上传 PPT 整体详细缩略图，或输入每页缩略图的详细描述、页数和页序。",
                data={"skill": self.name, "stage": "awaiting_collage_for_pages"},
            )

        _sessions[session_id] = {"stage": "awaiting_page_image_for_editable_ppt", "entry_choice": "4"}
        return SkillResult(
            success=True,
            message="已选择入口 4。请上传这一页高清 PPT 风格图，并说明需要还原成单页 PPTX 还是加入现有 PPT。",
            data={"skill": self.name, "stage": "awaiting_page_image_for_editable_ppt"},
        )

    async def _handle_content(self, context: SkillContext, session_id: str) -> SkillResult:
        source_text = await self._collect_source_text(context)
        if not self._has_enough_content(context.user_message, source_text):
            return SkillResult(
                success=True,
                message="我还没有收到足够的 PPT 资料。请上传文档，或直接输入主题、内容、受众和制作要求。",
                data={"skill": self.name, "stage": "awaiting_content"},
            )
        return await self._generate_outline(context, session_id, source_text)

    async def _handle_outline_confirm(self, context: SkillContext, session_id: str) -> SkillResult:
        if self._is_confirm(context.user_message):
            return SkillResult(
                success=True,
                message="收到确认。请回复“开始”，我将进入第 2 步生成三版 PPT 缩略图。",
                data={"skill": self.name, "stage": "awaiting_outline_confirm"},
            )
        source_text = await self._collect_source_text(context)
        if source_text or len(context.user_message.strip()) > 10:
            return await self._generate_outline(context, session_id, source_text, revision=context.user_message)
        return SkillResult(success=True, message="请确认大纲是否可以进入下一步；如果需要调整，请直接告诉我。")

    async def _handle_outline_for_visual(self, context: SkillContext, session_id: str) -> SkillResult:
        source_text = await self._collect_source_text(context)
        if not self._has_enough_content(context.user_message, source_text):
            return SkillResult(
                success=True,
                message="请提供已确认的 PPT 大纲和逐页内容，或上传包含大纲的文档。",
                data={"skill": self.name, "stage": "awaiting_outline_for_visual"},
            )
        _sessions[session_id] = {"stage": "visual_direction", "entry_choice": "2", "outline": source_text}
        return SkillResult(success=True, message="已收到 PPT 大纲。请回复“开始”，我将从第 2 步生成三版 PPT 缩略图。")

    async def _handle_collage_for_pages(self, context: SkillContext, session_id: str) -> SkillResult:
        if not context.uploaded_files and len(context.user_message.strip()) <= 20:
            return SkillResult(
                success=True,
                message=(
                    "请上传 PPT 整体详细缩略图（图片文件），并同时用文字补充以下信息：\n"
                    "1. 总页数\n"
                    "2. 每页标题（按页序排列）\n\n"
                    "这些文字信息是为了确保生成时页码和内容准确对应，缩略图本身会作为视觉风格参考。"
                ),
            )
        _sessions[session_id] = {
            "stage": "awaiting_page_info_for_step3",
            "entry_choice": "3",
            "collage_files": context.uploaded_files,
        }
        return SkillResult(
            success=True,
            message=(
                "已收到缩略图。请补充以下文字信息，我会进入第 3 步逐页生成高清风格图：\n"
                "1. 总页数（如：12 页）\n"
                "2. 每页标题（按第 1 页到最后一页的顺序列出）\n\n"
                "例如：\n"
                "第 1 页：封面 - Q2 业务复盘\n"
                "第 2 页：核心指标总览\n"
                "第 3 页：MO 漏斗转化分析\n"
                "...\n\n"
                "这些信息用于确保逐页生成时页码和标题准确对位。"
            ),
            data={"skill": self.name, "stage": "awaiting_page_info_for_step3"},
        )

    async def _handle_page_info_for_step3(self, context: SkillContext, session_id: str) -> SkillResult:
        """Handle user providing page count and titles for step 3."""
        msg = context.user_message.strip()
        if len(msg) <= 10:
            return SkillResult(
                success=True,
                message="请提供总页数和每页标题。例如：\n总 10 页\n第 1 页：封面\n第 2 页：目录\n...",
                data={"skill": self.name, "stage": "awaiting_page_info_for_step3"},
            )

        # Extract slide info from user input
        page_count = None
        m = re.search(r'(\d+)\s*页', msg)
        if m:
            page_count = int(m.group(1))

        # Extract per-page titles
        titles = []
        for m in re.finditer(r'第\s*(\d+)\s*页[：:]\s*(.+?)(?=第\s*\d+\s*页|$)', msg):
            titles.append({"page": int(m.group(1)), "title": m.group(2).strip()})

        if not titles:
            # Try line-by-line parsing
            lines = [l.strip() for l in msg.split('\n') if l.strip()]
            for i, line in enumerate(lines, 1):
                clean = re.sub(r'^\d+[\.\)、]?\s*', '', line).strip()
                if clean:
                    titles.append({"page": i, "title": clean})

        if not titles or len(titles) < 2:
            return SkillResult(
                success=True,
                message="未能识别出足够的页面信息。请按格式列出：\n第 1 页：[标题]\n第 2 页：[标题]\n...",
                data={"skill": self.name, "stage": "awaiting_page_info_for_step3"},
            )

        actual_count = page_count or len(titles)
        if actual_count != len(titles) and page_count:
            actual_count = page_count

        # Build outline from the provided info
        outline = f"PPT 共 {actual_count} 页\n\n"
        for t in titles:
            outline += f"第 {t['page']} 页：{t['title']}\n"

        session = _sessions.get(session_id, {})
        collage_files = session.get("collage_files") or []

        # For entry 3: the uploaded collage IS the visual master — skip Step 2, go direct to Step 3
        _sessions[session_id] = {
            **session,
            "stage": "entry3_ready",
            "entry_choice": "3",
            "outline": outline,
            "selected_visual": {"label": "REF", "filename": collage_files[0].get("filename", "") if collage_files else "uploaded_collage", "path": collage_files[0].get("path", "") if collage_files else ""},
        }
        collages: list[dict] = [{"label": "REF", "filename": collage_files[0].get("filename", "") if collage_files else "", "path": collage_files[0].get("path", "") if collage_files else ""}]
        _sessions[session_id]["visual_collages"] = collages

        return SkillResult(
            success=True,
            message=(
                f"已识别 {len(titles)} 页标题，上传的缩略图将直接作为视觉母版。\n\n"
                f"请回复「开始」，我将跳过第 2 步（三版缩略图），直接进入第 3 步逐页生成高清单页视觉稿。"
            ),
            data={"skill": self.name, "stage": "entry3_ready"},
        )

    async def _handle_page_image_for_editable_ppt(self, context: SkillContext, session_id: str) -> SkillResult:
        if not context.uploaded_files and len(context.user_message.strip()) <= 20:
            return SkillResult(success=True, message="请上传某一页高清 PPT 风格图，并说明需要还原成单页 PPTX 还是加入现有 PPT。")
        _sessions[session_id] = {"stage": "step4_ready", "entry_choice": "4", "uploaded_files": context.uploaded_files}
        return SkillResult(success=True, message="已收到高清 PPT 风格图。当前可先生成可下载 PPTX；更深度的文字可编辑重建需继续接入。")

    async def _collect_source_text(self, context: SkillContext) -> str:
        parts: list[str] = []
        if context.user_message.strip():
            parts.append(f"用户输入：\n{context.user_message.strip()}")
        for uploaded in context.uploaded_files:
            path = uploaded.get("path")
            filename = uploaded.get("filename") or (os.path.basename(path) if path else "upload")
            if not path:
                continue
            try:
                parsed = await asyncio.wait_for(asyncio.to_thread(parse_file_sync, path), timeout=30)
            except Exception:
                parsed = None
            if parsed:
                parts.append(f"上传文件：{filename}\n{parsed[:30000]}")
            else:
                parts.append(f"上传文件：{filename}\n系统暂时无法从该文件中提取文本。")
        return "\n\n---\n\n".join(parts).strip()

    def _has_enough_content(self, message: str, source_text: str) -> bool:
        stripped = message.strip()
        trigger_only = any(stripped.lower() == trigger.lower() for trigger in self.triggers)
        return bool(source_text) and (len(source_text) > 80 or not trigger_only)

    async def _generate_outline(
        self,
        context: SkillContext,
        session_id: str,
        source_text: str,
        revision: str | None = None,
    ) -> SkillResult:
        system_prompt = (
            "你是专业商业PPT策划助手。只做PPT大纲和逐页内容，不生成PPT文件。"
            "必须基于用户材料，不新增未经确认的数据、品牌、人物、产品或来源。"
        )
        revision_text = f"\n\n用户修改要求：\n{revision}" if revision else ""
        prompt = f"""
请阅读以下资料，生成一份PPT大纲和逐页内容。

要求：
1. 第一页必须是封面页。
2. 每页必须包含：页码、页面类型、标题、核心观点、正文要点、视觉建议。
3. 不要生成pptx，不要生成图片。
4. 结构要适合正式商业汇报，标题尽量是结论式表达。
5. 严格基于资料，不要编造未确认信息。
6. 最后询问用户是否确认大纲，确认后再进入下一步。

资料：
{source_text}
{revision_text}
""".strip()
        try:
            response = await llm_service.chat(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.3,
                timeout=180,
                thinking={"type": "disabled"},
            )
            outline = ""
            if response.content:
                for block in response.content:
                    if hasattr(block, "text"):
                        outline += block.text
        except Exception as exc:
            return SkillResult(success=False, message=f"生成 PPT 大纲时出错：{exc}")
        outline = outline.strip()
        if "确认" not in outline:
            outline += "\n\n请确认以上 PPT 大纲和逐页内容是否可以进入下一步。"
        _sessions[session_id] = {"stage": "awaiting_outline_confirm", "outline": outline}
        return SkillResult(success=True, message=outline, data={"skill": self.name, "stage": "awaiting_outline_confirm"})

    def _imagegen_exe(self) -> str | None:
        exe = settings.ruizhi_imagegen_exe or os.environ.get("RUIZHI_IMAGEGEN_EXE")
        if exe and os.path.exists(exe):
            return exe
        default = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Programs",
            "Codex",
            "resources",
            "bin",
            "ruizhi-imagegen.exe",
        )
        return default if default and os.path.exists(default) else None

    def _imagegen_env(self) -> dict[str, str]:
        env = os.environ.copy()
        if settings.ruizhi_home:
            env["RUIZHI_HOME"] = settings.ruizhi_home
        if settings.codex_home:
            env["CODEX_HOME"] = settings.codex_home
        if settings.ruizhi_api_key:
            env["RUIZHI_API_KEY"] = settings.ruizhi_api_key
        if settings.openai_api_key:
            env["OPENAI_API_KEY"] = settings.openai_api_key
        return env

    def _visual_prompts(self, outline: str) -> list[tuple[str, str]]:
        compact_outline = outline[:9000]
        base = f"""
Create one complete collage image for a professional business PowerPoint deck.
The collage must include every slide thumbnail in the confirmed order. Each thumbnail is a 16:9 horizontal PPT slide.
Do not create a PPTX file and do not create separate single-slide images.
Use only the confirmed outline and slide-by-slide content below.

Confirmed outline:
{compact_outline}
""".strip()
        return [
            ("A", base + "\n\nVisual direction A: premium strategy consulting report, bright background, precise grid, restrained accent colors."),
            ("B", base + "\n\nVisual direction B: advanced technology keynote, deep clean background, luminous data accents, high-end AI atmosphere."),
            ("C", base + "\n\nVisual direction C: refined editorial business deck, sophisticated image use, generous whitespace, elegant information blocks."),
        ]

    async def _run_step2_visual_collages(self, session_id: str, outline: str):
        yield "进度 1/4：正在读取已确认的大纲和逐页内容...\n"
        yield "进度 2/4：正在准备三版不同视觉方向的 PPT 拼图提示词...\n"
        yield "进度 3/4：正在检查 imagegen 图片生成能力...\n"
        async for item in self._generate_visual_collages(session_id, outline):
            yield item

    async def _generate_visual_collages(self, session_id: str, outline: str):
        exe = self._imagegen_exe()
        if not exe:
            yield SkillResult(success=False, message="第二步出错了：未找到 imagegen 图片生成工具。")
            return
        output_dir = os.path.abspath(os.path.join("data", "outputs"))
        os.makedirs(output_dir, exist_ok=True)
        run_id = uuid.uuid4().hex[:10]
        generated: list[dict] = []
        _sessions[session_id] = {**_sessions.get(session_id, {}), "stage": "generating_visual_direction", "outline": outline}

        for index, (label, prompt) in enumerate(self._visual_prompts(outline), 1):
            filename = f"ppt_maker_{session_id[:8]}_{run_id}_{label.lower()}.png"
            out_path = os.path.join(output_dir, filename)
            yield f"进度 4/4：正在生成方案 {label} 的完整 PPT 拼图（{index}/3）...\n"
            result = await self._run_imagegen(exe, prompt, out_path, timeout=420)
            if result:
                yield SkillResult(success=False, message=f"第二步出错了：方案 {label} 未能正常生成。\n\n{result}")
                return
            item = {"label": label, "filename": filename, "path": out_path}
            generated.append(item)
            _sessions[session_id] = {**_sessions.get(session_id, {}), "visual_collages": generated}
            yield SkillResult(
                success=True,
                message=(
                    f"方案 {label} 已生成：\n\n"
                    f"![方案 {label}](/api/skills/download/{filename})\n\n"
                    f"[下载方案 {label} 拼图](/api/skills/download/{filename})\n\n"
                ),
                data={"skill": self.name, "stage": "generating_visual_direction", "visual_collages": generated},
            )

        _sessions[session_id] = {
            **_sessions.get(session_id, {}),
            "stage": "awaiting_visual_choice",
            "outline": outline,
            "visual_collages": generated,
        }
        yield SkillResult(
            success=True,
            message="第二步已完成。请在方案 A、方案 B、方案 C 中选择一个视觉方向；如果都不满意，请回复“重新生成”。",
            data={"skill": self.name, "stage": "awaiting_visual_choice", "visual_collages": generated},
        )

    async def _run_imagegen(self, exe: str, prompt: str, out_path: str, timeout: int) -> str | None:
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [
                    exe,
                    "generate",
                    "--prompt",
                    prompt,
                    "--out",
                    out_path,
                    "--quality",
                    "high",
                    "--size",
                    "auto",
                    "--force",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self._imagegen_env(),
            )
        except subprocess.TimeoutExpired:
            return "调用 imagegen 超时。"
        except Exception as exc:
            return f"调用 imagegen 失败：{exc.__class__.__name__}: {str(exc) or '无详细错误文本'}"
        if completed.returncode != 0 or not os.path.exists(out_path):
            err = ((completed.stderr or "") + "\n" + (completed.stdout or "")).strip()[-1600:]
            return err or "imagegen 未返回可用输出。"
        return None

    def _parse_visual_choice(self, msg: str) -> str | None:
        compact = msg.strip().upper().replace(" ", "")
        compact = compact.replace("方案", "").replace("选择", "").replace("我选", "").replace("选", "")
        compact = compact.strip("。.!！,，：:")
        if compact in {"A", "B", "C"}:
            return compact
        match = re.search(r"方案\s*([ABC])", msg, re.IGNORECASE)
        return match.group(1).upper() if match else None

    def _selected_visual_choice(self, session: dict) -> str | None:
        selected = session.get("selected_visual") or {}
        label = str(selected.get("label", "")).upper()
        return label if label in {"A", "B", "C"} else None

    def _handle_visual_choice(self, context: SkillContext, session_id: str) -> SkillResult:
        msg = context.user_message.strip()
        if any(word in msg for word in ["不满意", "都不满意", "重新生成", "重做", "再生成"]):
            session = _sessions.get(session_id, {})
            session["stage"] = "awaiting_outline_confirm"
            _sessions[session_id] = session
            return SkillResult(success=True, message="好的。请告诉我重新生成前是否有特殊视觉要求；如果没有，直接回复“确认”。")
        choice = self._parse_visual_choice(msg)
        if not choice:
            return SkillResult(success=True, message="请回复方案 A、方案 B 或方案 C。若三版都不满意，也可以回复“重新生成”。")
        session = _sessions.get(session_id, {})
        generated = session.get("visual_collages") or []
        selected = next((item for item in generated if str(item.get("label", "")).upper() == choice), None)
        if not selected:
            return SkillResult(success=True, message=f"没有找到方案 {choice} 的缩略图记录。请从已生成的方案中选择 A、B 或 C。")
        session["selected_visual"] = selected
        session["stage"] = "awaiting_step3_start"
        _sessions[session_id] = session
        return SkillResult(success=True, message=f"已选择方案 {choice}。请回复“开始”或“继续”，我会进入第 3 步逐页生成高清单页图。")

    async def _handle_entry3_ready(self, context: SkillContext, session_id: str) -> SkillResult:
        """Handle user message when entry 3 is ready to go — confirm starts step 3 directly."""
        if self._is_confirm(context.user_message):
            session = _sessions.get(session_id, {})
            outline = str(session.get("outline") or "").strip()
            if not outline:
                return SkillResult(success=False, message="第 3 步出错了：没有找到页面信息。")
            _sessions[session_id] = {**session, "stage": "generating_single_pages"}
            return SkillResult(
                success=True,
                message="正在开始第 3 步逐页生成高清单页视觉稿...请稍候。",
                data={"skill": self.name, "stage": "generating_single_pages"},
            )
        if self._is_exit(context.user_message):
            _sessions.pop(session_id, None)
            return SkillResult(success=True, message="好的，已退出 PPT 制作流程。")
        return SkillResult(
            success=True,
            message="请回复「开始」或「继续」，我将直接进入第 3 步逐页生成高清单页视觉稿。如需退出请回复「退出」。",
            data={"skill": self.name, "stage": "entry3_ready"},
        )

    async def _handle_visual_direction_confirm(self, context: SkillContext, session_id: str) -> SkillResult:
        """Handle user message when outline is ready and stage is visual_direction."""
        if self._is_confirm(context.user_message):
            session = _sessions.get(session_id, {})
            outline = str(session.get("outline") or "").strip()
            if not outline:
                return SkillResult(success=False, message="第二步出错了：没有找到已确认的大纲内容。")
            _sessions[session_id] = {**session, "stage": "generating_visual_direction"}
            return SkillResult(
                success=True,
                message="正在开始第 2 步生成三版 PPT 缩略图...请稍候。",
                data={"skill": self.name, "stage": "generating_visual_direction"},
            )
        if self._is_exit(context.user_message):
            _sessions.pop(session_id, None)
            return SkillResult(success=True, message="好的，已退出 PPT 制作流程。")
        return SkillResult(
            success=True,
            message="请回复「开始」或「继续」，我将从第 2 步生成三版 PPT 缩略图。如需退出请回复「退出」。",
            data={"skill": self.name, "stage": "visual_direction"},
        )

    def _ack_step3_start(self, session_id: str) -> SkillResult:
        session = _sessions.get(session_id, {})
        choice = self._selected_visual_choice(session)
        if not choice:
            return SkillResult(success=True, message="第 3 步还不能开始：没有找到已选择的视觉方案。请重新选择方案 A、B 或 C。")
        return SkillResult(success=True, message=f"已接收到你的选择：方案 {choice}。请回复“开始”或“继续”，我会进入第 3 步。")

    def _return_generation_status(self, session_id: str) -> SkillResult:
        session = _sessions.get(session_id, {})
        page_images = session.get("single_pages") or []
        if page_images:
            message = "第 3 步正在执行，当前已生成的单页图如下：\n\n"
            for item in page_images:
                message += f"第 {item['page']} 页\n\n![第 {item['page']} 页](/api/skills/download/{item['filename']})\n\n"
        else:
            message = "第 3 步已接收并开始执行，目前正在准备或生成第 1 页。请稍候。"
        return SkillResult(success=True, message=message, data={"skill": self.name, "stage": session.get("stage", "generating_single_pages")})

    def _return_visual_collages(self, session_id: str) -> SkillResult:
        session = _sessions.get(session_id, {})
        generated = session.get("visual_collages") or []
        if not generated:
            return SkillResult(success=True, message="第二步还没有生成可查看的拼图。请回复“确认”重新开始生成三版视觉方案。")
        message = "当前已生成的 PPT 拼图方案如下：\n\n"
        for item in generated:
            message += f"方案 {item['label']}：完整 PPT 拼图\n\n![方案 {item['label']}](/api/skills/download/{item['filename']})\n\n"
        message += "请在方案 A、方案 B、方案 C 中选择一个视觉方向。"
        return SkillResult(success=True, message=message, data={"skill": self.name, "stage": session.get("stage", "awaiting_visual_choice")})

    def _extract_slide_sections(self, outline: str) -> list[dict]:
        matches = list(re.finditer(r"(第\s*\d+\s*页[:：]?.*?)(?=第\s*\d+\s*页[:：]?|\Z)", outline, re.S))
        slides: list[dict] = []
        for idx, match in enumerate(matches, 1):
            text = match.group(1).strip()
            title_line = text.splitlines()[0].strip() if text else f"第 {idx} 页"
            title = re.sub(r"^第\s*\d+\s*页[:：]?", "", title_line).strip() or title_line
            slides.append({"index": idx, "title": title, "content": text[:3000]})
        if slides:
            return slides
        chunks = [c.strip() for c in re.split(r"\n\s*\n", outline) if c.strip()]
        for idx, chunk in enumerate(chunks[:20], 1):
            title = chunk.splitlines()[0].strip()[:80] or f"第 {idx} 页"
            slides.append({"index": idx, "title": title, "content": chunk[:3000]})
        return slides

    def _style_text_for_choice(self, choice: str) -> str:
        styles = {
            "A": "premium strategy consulting report, bright background, precise grid, restrained accent colors",
            "B": "advanced technology keynote, deep clean background, luminous data accents, high-end AI atmosphere",
            "C": "refined editorial business deck, sophisticated image use, generous whitespace, elegant information blocks",
            "REF": "user-provided collage master — faithfully replicate the exact visual style, layout, color palette, and text hierarchy shown in the uploaded reference collage",
        }
        return styles.get(choice, styles["A"])

    def _build_visual_system_description(self, choice: str) -> str:
        """Build a detailed visual system spec so imagegen can replicate the collage style."""
        systems = {
            "REF": """The user has uploaded a collage as the definitive visual master. Replicate every aspect of the collage's visual system exactly as it appears:
Background: exactly match the collage's background style, color, and any textures or gradients present.
Font system: exactly match the collage's font hierarchy, sizes, weights, and colors for titles, subtitles, body text, and data callouts.
Color palette: exactly match the collage's color scheme — primary, secondary, accent colors, and their usage across elements.
Charts: exactly match the collage's chart style — type, color, line weight, grid presence, data label position, and legend placement.
Icons: exactly match the collage's icon style — geometric vs. organic, line weight, filled vs. outlined, color treatment.
Cards/modules: exactly match the collage's card border style, fill opacity, corner radius, internal padding, and shadow if present.
Margins: exactly match the collage's page margins and content area boundaries.
Whitespace: exactly match the collage's spacing rhythm between elements and sections.
Footer: exactly match the collage's footer treatment — separator line, page number position/style, any section labels.
Page density: exactly match the collage's information density — number of content blocks per page, visual weight distribution.
CRITICAL: Do NOT apply any preset style. The uploaded collage IS the only style reference.""",
            "A": """Background: clean white to very light warm gray (#F8F7F4 to #FFFFFF). No gradients on standard pages.
Font system: modern sans-serif (similar to Inter/Source Han Sans). Title 28-32px bold, dark charcoal (#1A1A1A). Section headings 14-16px medium, muted gray (#4A4A4A). Body text 10-12px regular (#333333). Key numbers in 36-48px display weight with indigo accent (#3B5998).
Color palette: primary indigo/blue (#3B5998), secondary warm gray (#9E9E9E), accent coral (#E8734A) used sparingly for emphasis.
Charts: flat design, thin gray gridlines (0.5px #E0E0E0), consistent 10px axis labels, data labels placed directly on chart elements. Bar charts with rounded tops (2px radius). Line charts with 2px stroke weight.
Icons: simple geometric line icons, 1.5-2px consistent stroke, grayscale (#666666) or matching indigo accent.
Cards/modules: 1px #E8E8E8 borders, optional 2-3% gray fill (#F5F5F5), 6px border radius, 16px internal padding.
Margins: 60px left/right, 50px top, 70px bottom (for page number zone).
Whitespace: 20-28px gap between modules, clear visual grouping by proximity.
Footer: thin 1px #E0E0E0 separator line at bottom, page number right-aligned 9px #999999, optional section label left-aligned.
Page density: medium — 1 clear focal point per page, 3-5 content blocks maximum.""",
            "B": """Background: deep dark base (#0D1117 to #161B22), subtle grid or dot pattern overlay at 3-5% opacity.
Font system: geometric sans-serif (similar to SF Pro Display/DIN). Title 30-38px bold, white (#FFFFFF) or electric blue (#58A6FF). Section labels 12-14px uppercase letter-spacing 2px, cyan accent (#39D2C0). Body 10-11px light gray (#C9D1D9). Key metrics in 40-56px bold display, gradient from cyan to electric blue.
Color palette: deep background (#0D1117), primary electric blue (#58A6FF), accent cyan (#39D2C0), data highlight amber (#F0883E), subtle purple for secondary data (#BC8CFF).
Charts: dark surface with luminous data elements. Bar charts with subtle inner glow. Line charts with 2px stroke + subtle outer glow (matching data color). Grid lines at 8% white opacity. Data labels in white 10px.
Icons: thin luminous line icons (1.5px stroke), cyan or electric blue (#58A6FF), subtle glow effect.
Cards/modules: semi-transparent panels (8-15% white overlay) on dark background, 1px border at 15-20% white, 10px border radius, 20px padding.
Margins: 55px left/right, 45px top, 65px bottom.
Whitespace: 24-32px between modules, dramatic negative space on dark background.
Footer: minimal footer, thin gradient separator line (cyan to transparent), page number in cyan 9px, subtle glow.
Page density: medium-high — data-rich but clean, strong visual hierarchy, 4-6 blocks per page.""",
            "C": """Background: warm off-white or very light cream (#FAF9F6), occasional subtle paper texture at 2% opacity for depth.
Font system: refined serif for titles (similar to Source Han Serif/Noto Serif CJK), modern sans-serif for body. Title 24-28px regular weight, deep brown (#2C2416). Section labels 11-13px with 3px letter-spacing, warm taupe (#8B7D6B). Body 10-12px with 1.6x line height, warm charcoal (#3D3226). Numbers in 32-40px light weight.
Color palette: warm neutral base (#FAF9F6), deep brown/charcoal (#2C2416), warm taupe (#8B7D6B), accent muted burgundy (#8B3A3A) or deep olive (#4A6741), occasional gold accent (#C4A747) for highlights.
Charts: refined minimal style, very thin lines (0.5-1px), muted color differentiation (2-3 analogous warm tones), integrated serif typography in labels, minimal to no grid lines.
Icons: delicate thin line icons (1-1.5px stroke), warm taupe (#8B7D6B) or matching the neutral palette.
Cards/modules: very subtle — thin rules (0.5px #D9D3C9), occasional 2-3% warm gray fill, 12-16px border radius, 20-24px padding.
Margins: generous 72-80px left/right, 60px top, 80px bottom.
Whitespace: abundance — the defining characteristic. 32-48px between sections. Each element has breathing room.
Footer: nearly invisible, page number in very light warm gray (#C4BDB2) 8px, minimal or no separator line.
Page density: low to medium — one clear statement per page, maximum 3 content blocks, surrounded by generous space.""",
        }
        return systems.get(choice, systems["A"])

    def _detect_page_layout(self, content: str) -> str:
        """Detect likely page layout type from content structure for better imagegen prompts."""
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["封面", "title", "标题页", "cover"]):
            return "COVER slide: centered title with subtitle, minimal content, large title text, company/date line at bottom. Strong visual impact, most spacious of all pages."
        if any(kw in content_lower for kw in ["目录", "agenda", "目录页", "contents"]):
            return "AGENDA/TOC slide: numbered list of sections, possibly with brief descriptions. Clean list format with consistent spacing."
        if any(kw in content_lower for kw in ["图表", "chart", "graph", "数据", "趋势", "对比", "占比", "%"]):
            return "DATA/CHART slide: chart or graph as the dominant visual element, with supporting title and 2-3 key insight callouts. Data visualization first, text second."
        if any(kw in content_lower for kw in ["对比", "比较", "vs", "方案", "优劣"]):
            return "COMPARISON slide: two-column or multi-column layout comparing options/scenarios. Clear visual separation between columns."
        if any(kw in content_lower for kw in ["流程", "步骤", "阶段", "process", "step", "timeline", "时间线"]):
            return "PROCESS/TIMELINE slide: horizontal or vertical flow showing sequential steps or phases. Connected nodes with brief descriptions."
        if any(kw in content_lower for kw in ["总结", "下一步", "感谢", "谢谢", "thank", "summary", "conclusion"]):
            return "SUMMARY/CLOSING slide: key takeaways or call to action. Clean and impactful, fewer elements."
        if any(kw in content_lower for kw in ["概述", "背景", "目标", "现状"]):
            return "OVERVIEW slide: title + 2-4 text blocks or cards introducing a topic. Moderate density, clear information hierarchy."
        # Default
        return "CONTENT slide: standard business slide with title, 2-4 key points or text blocks, possible supporting visual. Balanced layout with clear hierarchy."

    async def _start_step3_single_pages(self, session_id: str, choice: str):
        session = _sessions.get(session_id, {})
        generated = session.get("visual_collages") or []
        selected = next((item for item in generated if str(item.get("label", "")).upper() == choice), None)
        outline = str(session.get("outline") or "").strip()
        if not selected:
            yield SkillResult(success=False, message=f"第 3 步出错了：没有找到方案 {choice} 的缩略图记录。请重新选择 A/B/C。")
            return
        if not outline:
            yield SkillResult(success=False, message="第 3 步出错了：没有找到已确认的大纲和逐页内容，无法生成单页高清图。")
            return
        slides = self._extract_slide_sections(outline)
        if not slides:
            yield SkillResult(success=False, message="第 3 步出错了：无法从大纲中识别页码和逐页内容。请补充每页标题和正文要点后重试。")
            return
        session["selected_visual"] = selected
        session["stage"] = "generating_single_pages"
        _sessions[session_id] = session
        total = len(slides)
        yield f"已选择方案 {choice}。\n\n第 3 步：基于拼图逐页还原高清单页视觉稿（共 {total} 页）。\n\n"
        await asyncio.sleep(0.1)
        yield "页面清单：\n"
        for s in slides:
            yield f"  第 {s['index']} 页 — {s.get('title', '')}\n"
        yield "\n按页序依次生成...\n"
        await asyncio.sleep(0.1)
        async for item in self._generate_single_page_images(session_id, choice, slides):
            yield item

    async def _generate_single_page_images(self, session_id: str, choice: str, slides: list[dict]):
        exe = self._imagegen_exe()
        if not exe:
            yield SkillResult(success=False, message="第 3 步出错了：未找到 imagegen 图片生成工具，无法生成逐页高清图。")
            return
        output_dir = os.path.abspath(os.path.join("data", "outputs"))
        os.makedirs(output_dir, exist_ok=True)
        run_id = uuid.uuid4().hex[:10]
        page_images: list[dict] = []
        style = self._style_text_for_choice(choice)
        visual_system = self._build_visual_system_description(choice)
        total = len(slides)
        session = _sessions.get(session_id, {})
        selected_visual = session.get("selected_visual") or {}
        collage_filename = selected_visual.get("filename", "")

        for slide in slides:
            idx = slide["index"]
            filename = f"ppt_maker_{session_id[:8]}_{run_id}_page_{idx:02d}.png"
            out_path = os.path.join(output_dir, filename)

            # Build page-specific layout hint from content structure
            content = slide.get("content", "")
            page_type = slide.get("title", f"Page {idx}")
            # Detect page type for layout hint
            layout_hint = self._detect_page_layout(content)

            prompt = f"""Design task: Reproduce page {idx} of {total} from a confirmed PPT collage master as a standalone high-resolution 16:9 slide.

This is NOT a redesign. This is faithful expansion — taking one page from the collage and rendering it as a clean, sharp, full-resolution single slide. The collage is the master reference for visual style, layout, and content structure.

COLLAGE CONTEXT:
- Selected visual direction: Plan {choice} — {style}
- Collage filename: {collage_filename}
- Page {idx} of {total}

VISUAL SYSTEM (must replicate exactly from the collage):
{visual_system}

LAYOUT TYPE FOR THIS PAGE:
{layout_hint}

CONFIRMED CONTENT (from the approved outline):
{content[:2000]}

CRITICAL RULES:
1. Output page {idx} ONLY. One single 16:9 slide image. No collage, no multi-page, no PPTX file.
2. Match the collage page layout faithfully — same title position, content blocks, chart areas, module boundaries. Just clearer and higher resolution.
3. {idx} must be clearly visible as the page number.
4. All Chinese text must be real, correct, readable Chinese characters. NO gibberish or pseudo-Chinese.
5. Use ONLY confirmed content above. Never invent brands, logos, people, products, data, or sources.
6. If collage details (small text, chart numbers) are unclear, supplement from the confirmed outline above while preserving the original visual layout and proportions.
7. Redraw complex charts at high resolution matching the visual proportions and style — do not fabricate precise data values.
8. The result must look like a finished, formal business PPT slide — NOT a wireframe, sketch, or design note.
9. Maintain the exact same design system as the collage across all pages. Allow for the layout variations that already exist in the collage.
10. Do NOT simply crop-zoom the collage. Re-render each page at full resolution with clearer text, icons, charts, and details.
11. This slide will be used as a blueprint for an editable PPTX — composition, text hierarchy, module boundaries, chart relationships, page number, and visual rhythm must be clear, stable, and reproducible."""

            yield f"正在生成第 {idx}/{total} 页单页 PPT 视觉稿...\n"
            await asyncio.sleep(0.1)
            error = await self._run_imagegen(exe, prompt, out_path, timeout=420)
            if error:
                yield SkillResult(
                    success=False,
                    message=f"第 3 步出错了：第 {idx} 页未能正常生成。\n\n{error}",
                    data={"skill": self.name, "stage": "generating_single_pages", "single_pages": page_images},
                )
                return
            page_images.append({"page": idx, "title": slide.get("title", ""), "filename": filename, "path": out_path})
            _sessions[session_id] = {**_sessions.get(session_id, {}), "stage": "generating_single_pages", "single_pages": page_images}
            yield SkillResult(
                success=True,
                message=(
                    f"第 {idx} 页高清 PPT 风格图已生成：\n\n"
                    f"![第 {idx} 页高清风格图](/api/skills/download/{filename})\n\n"
                    f"[下载第 {idx} 页高清图](/api/skills/download/{filename})\n\n"
                    "我会继续生成下一页。"
                ),
                data={"skill": self.name, "stage": "generating_single_pages", "single_pages": page_images, "latest_page": page_images[-1]},
            )
            await asyncio.sleep(0.1)
        _sessions[session_id] = {**_sessions.get(session_id, {}), "stage": "awaiting_editable_ppt_scope", "single_pages": page_images}
        yield SkillResult(
            success=True,
            message="第 3 步已完成。你希望把哪一部分做成可编辑 PPT？可以回复某一页、几页，或回复“全部”。",
            data={"skill": self.name, "stage": "awaiting_editable_ppt_scope", "single_pages": page_images},
        )

    def _select_page_images(self, request: str, page_images: list[dict]) -> list[dict]:
        if not page_images:
            return []
        req = (request or "").strip().lower()
        if not req or "全部" in req or "all" in req or "整套" in req:
            return page_images
        selected_pages: set[int] = set()
        for start, end in re.findall(r"(\d+)\s*[-~至到]\s*(\d+)", req):
            a, b = int(start), int(end)
            if a > b:
                a, b = b, a
            selected_pages.update(range(a, b + 1))
        for num in re.findall(r"\d+", req):
            selected_pages.add(int(num))
        if not selected_pages:
            return page_images
        return [item for item in page_images if int(item.get("page", 0)) in selected_pages]

    def _build_pptx_from_page_images(self, session_id: str, page_images: list[dict]) -> dict:
        from pptx import Presentation
        from pptx.util import Inches

        output_dir = os.path.abspath(os.path.join("data", "outputs"))
        os.makedirs(output_dir, exist_ok=True)
        filename = f"ppt_maker_{session_id[:8]}_{uuid.uuid4().hex[:10]}.pptx"
        out_path = os.path.join(output_dir, filename)
        prs = Presentation()
        prs.slide_width = Inches(13.333333)
        prs.slide_height = Inches(7.5)
        blank_layout = prs.slide_layouts[6]
        for item in page_images:
            slide = prs.slides.add_slide(blank_layout)
            slide.shapes.add_picture(item["path"], 0, 0, width=prs.slide_width, height=prs.slide_height)
        prs.save(out_path)
        return {"filename": filename, "path": out_path, "download_url": f"/api/skills/download/{filename}"}

    def _handle_editable_ppt_scope(self, context: SkillContext, session_id: str) -> SkillResult:
        session = _sessions.get(session_id, {})
        page_images = session.get("single_pages") or []
        if not page_images:
            return SkillResult(success=False, message="第 4 步出错了：没有找到第 3 步生成的高清页面图，无法生成 PPTX。")
        selected = self._select_page_images(context.user_message.strip(), page_images)
        if not selected:
            return SkillResult(success=False, message="没有匹配到你指定的页码。请回复“全部”或类似“第 1 页”“1-3 页”的范围。")
        try:
            pptx = self._build_pptx_from_page_images(session_id, selected)
        except Exception as exc:
            return SkillResult(success=False, message=f"第 4 步出错了：生成 PPTX 失败。\n\n错误类型：{exc.__class__.__name__}\n错误原因：{str(exc) or '无详细错误文本'}")
        session["editable_scope_request"] = context.user_message.strip()
        session["stage"] = "completed"
        session["pptx"] = pptx
        _sessions[session_id] = session
        return SkillResult(
            success=True,
            message=(
                "第 4 步已完成，PPTX 文件已生成。\n\n"
                f"[下载 PPTX 文件]({pptx['download_url']})\n\n"
                "说明：当前版本先将第 3 步生成的高清视觉稿按页放入 16:9 PPTX，保证可下载、可演示。"
                "后续如果要做到主要文字完全可编辑，还需要继续做文字识别、遮罩和文本框重建。"
            ),
            data={"skill": self.name, "stage": "completed", "download_url": pptx["download_url"], "filename": pptx["filename"], "path": pptx["path"]},
            follow_up_action="download",
        )
