import os
import re
import copy
from datetime import datetime, timedelta
from app.skills.base import BaseSkill, SkillContext, SkillResult
from app.services.llm_service import llm_service
from app.services.user_profile_service import UserProfileService

MIN_DETAIL_LENGTH = 10

# In-memory state for guided multi-turn weekly report sessions
_sessions: dict[str, dict] = {}

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五"]


class WeeklyReportSkill(BaseSkill):
    name = "weekly_report"
    description = "复制上周周报sheet，通过对话引导了解本周工作，按天更新周报内容"
    triggers = ["写周报", "周报", "生成周报", "帮我写周报"]
    keywords = ["周报", "weekly", "工作周报", "周工作总结"]

    TEMPLATE_FILE = os.path.join("..", "工作周报", "template & history.xlsx")
    OUTPUT_DIR = os.path.join("..", "工作周报", "输出")

    def can_handle(self, message: str) -> bool:
        msg_lower = message.lower()
        for trigger in self.triggers:
            if trigger.lower() in msg_lower:
                return True
        for kw in self.keywords:
            if kw.lower() in msg_lower:
                return True
        return False

    async def execute(self, context: SkillContext) -> SkillResult:
        msg = context.user_message.strip()
        session_id = context.session_id or "default"

        # --- Check for control commands (only when message is short) ---
        # Work descriptions are always long; short messages are likely commands.
        exit_kws = ["重新开始", "重来", "取消", "退出", "返回", "算了", "不写了"]
        if len(msg) <= 10 and any(kw in msg for kw in exit_kws):
            _sessions.pop(session_id, None)
            return SkillResult(
                success=True,
                message="好的，已退出周报生成。有什么其他需要随时找我。",
            )

        # --- Check if there's an ongoing session ---
        ongoing = _sessions.get(session_id)
        if ongoing:
            mode = ongoing.get("mode", "guided")
            if mode == "ask_date":
                return await self._handle_ask_date(ongoing, msg, session_id)
            elif mode == "choose":
                return await self._handle_choose(ongoing, msg, session_id)
            elif mode == "fast_collect":
                return await self._handle_fast_collect(ongoing, msg, session_id)
            else:
                return await self._handle_collection(ongoing, msg, session_id)

        # --- New request: check if user specified a date range ---
        # If no date info in message, ask the user which week they want
        if not self._has_date_specifier(msg):
            _sessions[session_id] = {"mode": "ask_date"}
            weeks = self._build_weeks_data()
            return SkillResult(
                success=True,
                message=(
                    "好的，请选择要写**哪一周**的周报："
                ),
                data={
                    "skill": "weekly_report",
                    "awaiting_input": True,
                    "mode": "ask_date",
                    "weeks": weeks,
                },
            )

        # --- Parse date range and find file ---
        start_date, end_date = self._parse_date_range(msg)

        file_path = self._find_latest_report()
        if not file_path:
            return SkillResult(
                success=True,
                message=(
                    f"好的，我来帮你生成 {start_date} 到 {end_date} 的周报。\n\n"
                    "但我没有找到之前的周报文件。请上传一份之前的周报 Excel 文件（如 `工作周报/` 目录下的文件），"
                    "我会按一致的格式来生成。"
                ),
                data={"awaiting_upload": True, "skill": "weekly_report", "date_range": f"{start_date}-{end_date}"},
            )

        # --- Determine mode: guided (day-by-day) vs fast (all at once) ---
        # Check if user already specified mode or provided work details
        guided_keywords = ["一天一天", "逐天", "每天聊", "逐日", "一天天"]
        fast_keywords = ["一次性", "一起", "直接生成", "一口气"]

        want_guided = any(kw in msg for kw in guided_keywords)
        want_fast = any(kw in msg for kw in fast_keywords)
        work_details = self._extract_work_details(msg)

        # User chose day-by-day
        if want_guided:
            return await self._start_guided(file_path, start_date, end_date, session_id)

        # User chose fast mode or already provided detailed work
        if want_fast or work_details:
            if work_details:
                return await self._generate_full(file_path, start_date, end_date, work_details, session_id)
            # User wants fast mode but hasn't provided details yet — ask for them
            return SkillResult(
                success=True,
                message=(
                    f"好的，一次性生成 {start_date} 到 {end_date} 的周报。\n\n"
                    "请把这周的重点工作一次性告诉我，比如：\n"
                    "• 周一：上午做了xx，下午做了xx\n"
                    "• 周二：上午做了xx，下午做了xx\n"
                    "• ...\n\n"
                    "我会帮你整理成专业表述填入周报。"
                ),
                data={"skill": "weekly_report", "awaiting_input": True, "mode": "fast"},
            )

        # No choice made — ask user to pick
        # Also handle the case where user replied "A" or "B" but has no session
        msg_lower = msg.lower().strip()
        if msg_lower in ("a", "b", "选a", "选b", "a.", "b."):
            if msg_lower.startswith("a") or msg_lower == "a" or msg_lower == "a.":
                return self._start_guided(file_path, start_date, end_date, session_id)
            else:
                # User chose B: create a session in "fast" mode waiting for work details
                _sessions[session_id] = {
                    "mode": "fast_collect",
                    "file_path": file_path,
                    "start_date": start_date,
                    "end_date": end_date,
                }
                return SkillResult(
                    success=True,
                    message=(
                        f"好的，一次性生成 {start_date} 到 {end_date} 的周报。\n\n"
                        "请把这周的重点工作一次性告诉我，比如：\n"
                        "• 周一：上午做了xx，下午做了xx\n"
                        "• 周二：上午做了xx，下午做了xx\n"
                        "• ...\n\n"
                        "我会帮你整理成专业表述填入周报。"
                    ),
                    data={"skill": "weekly_report", "awaiting_input": True, "mode": "fast"},
                )

        s = datetime.strptime(start_date, "%Y-%m-%d")
        # Create a lightweight session so the next reply gets routed back here
        _sessions[session_id] = {
            "mode": "choose",
            "file_path": file_path,
            "start_date": start_date,
            "end_date": end_date,
        }
        return SkillResult(
            success=True,
            message=(
                f"好的，我来帮你生成 {start_date}（周一）到 {end_date}（周日）的周报。\n\n"
                "你想怎么聊？\n"
                "**A. 一天一天聊** — 我每天问你做了什么，逐天收集，适合边想边写\n"
                "**B. 一次性聊完** — 你把一周重点工作一起告诉我，我直接生成完整周报\n\n"
                "回复 **A** 或 **B** 即可。"
            ),
            data={"skill": "weekly_report", "awaiting_input": True, "mode": "choose"},
        )

    # ── ask date handler ─────────────────────────────────────────

    async def _handle_ask_date(self, session: dict, msg: str, session_id: str) -> SkillResult:
        """Handle user providing the week date range."""
        # Check if user accidentally typed A/B instead of dates
        msg_lower = msg.lower().strip()
        if msg_lower in ("a", "b", "选a", "选b", "a.", "b."):
            weeks = self._build_weeks_data()
            return SkillResult(
                success=True,
                message="还没告诉我日期呢～请选择你想写**哪一周**的周报：",
                data={"skill": "weekly_report", "awaiting_input": True, "mode": "ask_date", "weeks": weeks},
            )

        if not self._has_date_specifier(msg):
            weeks = self._build_weeks_data()
            return SkillResult(
                success=True,
                message="请选择你想写**哪一周**的周报，或直接输入日期范围（如 `5月25日-5月31日`）：",
                data={"skill": "weekly_report", "awaiting_input": True, "mode": "ask_date", "weeks": weeks},
            )

        start_date, end_date = self._parse_date_range(msg)

        file_path = self._find_latest_report()
        if not file_path:
            _sessions.pop(session_id, None)
            return SkillResult(
                success=True,
                message=(
                    f"好的，{start_date} 到 {end_date} 的周报。\n\n"
                    "但我没有找到之前的周报模板文件。请上传一份之前的周报 Excel 文件"
                    "（如 `工作周报/` 目录下的文件），我会按一致的格式来生成。"
                ),
                data={"awaiting_upload": True, "skill": "weekly_report", "date_range": f"{start_date}-{end_date}"},
            )

        # Store and proceed to A/B mode choice
        _sessions[session_id] = {
            "mode": "choose",
            "file_path": file_path,
            "start_date": start_date,
            "end_date": end_date,
        }
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
        return SkillResult(
            success=True,
            message=(
                f"好的，我来帮你生成 {start_date}（周一）到 {end_date}（周日）的周报。\n\n"
                "你想怎么聊？\n"
                "**A. 一天一天聊** — 我每天问你做了什么，逐天收集，适合边想边写\n"
                "**B. 一次性聊完** — 你把一周重点工作一起告诉我，我直接生成完整周报\n\n"
                "回复 **A** 或 **B** 即可。"
            ),
            data={"skill": "weekly_report", "awaiting_input": True, "mode": "choose"},
        )

    # ── mode choice / fast collection handlers ─────────────────

    async def _handle_choose(self, session: dict, msg: str, session_id: str) -> SkillResult:
        """Handle user's reply to the A/B mode choice."""
        msg_lower = msg.lower().strip()
        file_path = session["file_path"]
        start_date = session["start_date"]
        end_date = session["end_date"]

        if msg_lower.startswith("a") or msg_lower in ("a", "a.", "选a"):
            _sessions.pop(session_id, None)
            return self._start_guided(file_path, start_date, end_date, session_id)
        elif msg_lower.startswith("b") or msg_lower in ("b", "b.", "选b"):
            session["mode"] = "fast_collect"
            return SkillResult(
                success=True,
                message=(
                    f"好的，一次性生成 {start_date} 到 {end_date} 的周报。\n\n"
                    "请把这周的重点工作一次性告诉我，比如：\n"
                    "• 周一：上午做了xx，下午做了xx\n"
                    "• 周二：上午做了xx，下午做了xx\n"
                    "• ...\n\n"
                    "我会帮你整理成专业表述填入周报。"
                ),
                data={"skill": "weekly_report", "awaiting_input": True, "mode": "fast"},
            )
        else:
            return SkillResult(
                success=True,
                message="请回复 **A**（一天一天聊）或 **B**（一次性聊完），我来帮你开始。",
                data={"skill": "weekly_report", "awaiting_input": True, "mode": "choose"},
            )

    async def _handle_fast_collect(self, session: dict, msg: str, session_id: str) -> SkillResult:
        """Handle user providing all week's work at once, then generate."""
        work_details = self._extract_work_details(msg)
        if not work_details:
            return SkillResult(
                success=True,
                message="请描述这周的重点工作，内容太少我无法生成。可以按天列出，比如：周一上午xx、下午xx...",
                data={"skill": "weekly_report", "awaiting_input": True, "mode": "fast"},
            )
        _sessions.pop(session_id, None)
        return await self._generate_full(
            session["file_path"], session["start_date"], session["end_date"], work_details, session_id
        )

    # ── guided collection handlers ──────────────────────────────

    def _start_guided(self, file_path: str, start_date: str, end_date: str, session_id: str) -> SkillResult:
        """Initialize a guided day-by-day session and ask about Monday."""
        try:
            last_sheet_content = self._read_sheet_content(file_path)
        except Exception:
            last_sheet_content = "无法读取上周内容，将使用默认模板格式。"

        _sessions[session_id] = {
            "file_path": file_path,
            "start_date": start_date,
            "end_date": end_date,
            "day_index": 0,
            "collected": {},
            "last_sheet_content": last_sheet_content,
        }

        s = datetime.strptime(start_date, "%Y-%m-%d")
        return SkillResult(
            success=True,
            message=(
                f"好的，我们一天一天来。从 **周一（{s.month}月{s.day}日）** 开始——\n"
                f"周一主要做了哪些工作？（可以简单描述上午和下午的内容，我会帮你整理成专业表述）"
            ),
            data={"skill": "weekly_report", "awaiting_input": True, "day": "周一"},
        )

    async def _handle_collection(self, session: dict, msg: str, session_id: str) -> SkillResult:
        """Process user input for the current day and advance to the next."""
        day_idx = session["day_index"]
        day_name = DAY_NAMES[day_idx]

        # Store user input for this day
        session["collected"][day_idx] = msg

        # Move to next day
        next_idx = day_idx + 1

        if next_idx >= 5:
            # All 5 days collected — generate the report
            result = await self._generate_from_collected(session, session_id)
            _sessions.pop(session_id, None)
            return result

        # Ask about next day
        session["day_index"] = next_idx
        next_name = DAY_NAMES[next_idx]
        start_date = datetime.strptime(session["start_date"], "%Y-%m-%d")
        next_date = start_date + timedelta(days=next_idx)

        # Build summary of what's been collected so far
        collected_summary = self._build_collected_summary(session)

        return SkillResult(
            success=True,
            message=(
                f"收到，已记录{day_name}的工作内容。\n\n"
                f"{collected_summary}\n"
                f"接下来，**{next_name}（{next_date.month}月{next_date.day}日）** 主要做了什么？"
            ),
            data={"skill": "weekly_report", "awaiting_input": True, "day": next_name, "progress": f"{next_idx}/5"},
        )

    def _build_collected_summary(self, session: dict) -> str:
        """Build a brief summary of collected days."""
        lines = ["📋 已收集："]
        for i in sorted(session["collected"].keys()):
            content = session["collected"][i][:80]
            lines.append(f"  {DAY_NAMES[i]}：{content}...")
        return "\n".join(lines)

    # ── full generation ─────────────────────────────────────────

    async def _generate_from_collected(self, session: dict, session_id: str) -> SkillResult:
        """After all 5 days collected, search KB and generate the report."""
        start_date = session["start_date"]
        end_date = session["end_date"]
        file_path = session["file_path"]

        # Build user input summary from collected data
        user_input_parts = []
        for i in range(5):
            if i in session["collected"]:
                user_input_parts.append(f"{DAY_NAMES[i]}：{session['collected'][i]}")
        user_input = "\n".join(user_input_parts)

        return await self._generate_full(file_path, start_date, end_date, user_input, session_id)

    async def _generate_full(
        self, file_path: str, start_date: str, end_date: str, user_input: str, session_id: str
    ) -> SkillResult:
        """Full generation: copy template sheet, update daily content + summary, save."""
        try:
            import openpyxl
            from openpyxl.utils import get_column_letter

            # 1. Read the template file
            wb = openpyxl.load_workbook(file_path)
            latest_sheet_name = self._get_latest_sheet_name(wb)

            # 2. Create new sheet name from this week's date range
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            new_sheet_name = f"{s.month}.{s.day}-{e.month}.{e.day}"

            # Avoid duplicate sheet names
            if new_sheet_name in wb.sheetnames:
                wb.close()
                return SkillResult(
                    success=False,
                    message=f"工作表 '{new_sheet_name}' 已存在。请检查是否需要重新生成。",
                )

            # 3. Copy template sheet as new sheet
            if latest_sheet_name:
                self._copy_sheet(wb, latest_sheet_name, new_sheet_name)
            else:
                ws = wb.create_sheet(title=new_sheet_name)
                ws["A1"] = "日期/星期"
                ws["B1"] = "时间"
                ws["C1"] = "时间"
                ws["D1"] = "本周计划"
                ws["E1"] = "本周总结（完成情况及改进，有什么问题）"

            # 4. Clean up 2025 data
            self._remove_old_data(wb, new_sheet_name)

            # 5. Search KB for patterns
            kb_patterns = await self._search_knowledge_base()

            # 6. Generate daily D/E content + get day_map for merging
            fill_data, day_map = await self._generate_updated_content(
                wb, new_sheet_name, start_date, end_date, user_input, kb_patterns
            )

            ws = wb[new_sheet_name]

            # 7. Re-merge A-column cells for each day after writing dates
            self._merge_date_cells(ws, day_map)

            # 8. Clear and apply daily D/E fill data
            max_data_row = max(r[1] for r in day_map.values()) if day_map else ws.max_row
            self._apply_fill_data(ws, fill_data, max_data_row)

            # 8.5. Fill any remaining empty D/E cells with defaults
            self._fill_empty_cells(ws, day_map, start_date)

            # 9. Generate summary section (B/C columns below daily content)
            summary_data = await self._generate_summary(
                ws, day_map, start_date, end_date, user_input, kb_patterns
            )
            self._apply_summary_data(ws, summary_data)

            # 10. Save to output directory
            os.makedirs(self.OUTPUT_DIR, exist_ok=True)
            new_filename = f"26年周工作总结和下周计划-ZB-{s.month}.{s.day}-{e.month}.{e.day}.xlsx"
            new_filepath = os.path.join(self.OUTPUT_DIR, new_filename)
            wb.save(new_filepath)
            wb.close()

            # Also copy to data/outputs for download
            data_output = os.path.join("data", "outputs")
            os.makedirs(data_output, exist_ok=True)
            wb2 = openpyxl.load_workbook(new_filepath)
            wb2.save(os.path.join(data_output, new_filename))
            wb2.close()

            filename = new_filename
            summary = self._build_summary(fill_data, start_date, end_date, filename, new_sheet_name)

            return SkillResult(
                success=True,
                message=summary,
                data={
                    "download_url": f"/api/skills/download/{filename}",
                    "filename": filename,
                    "path": new_filepath,
                },
                follow_up_action="download",
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Weekly report generation failed: %s", e, exc_info=True)
            return SkillResult(
                success=False,
                message=f"周报生成过程出错：{e}",
            )

    # ── Excel operations ─────────────────────────────────────────

    def _find_latest_report(self) -> str | None:
        """Find the template file to use as base."""
        if os.path.isfile(self.TEMPLATE_FILE):
            return self.TEMPLATE_FILE
        return None

    def _get_latest_sheet_name(self, wb) -> str | None:
        """Get the most recent date-range sheet (e.g. '5.11-5.15'), not template/other."""
        import re
        date_range_sheets = []
        for s in wb.sheetnames:
            if re.match(r'^\d+\.\d+-\d+\.\d+$', s):
                # Parse start date for sorting: M.D → (M, D)
                m = re.match(r'^(\d+)\.(\d+)-', s)
                if m:
                    month, day = int(m.group(1)), int(m.group(2))
                    date_range_sheets.append(((month, day), s))
        if date_range_sheets:
            date_range_sheets.sort()
            return date_range_sheets[-1][1]  # Most recent by date
        # Fallback: filter known non-date names
        skip = {"Sheet1", "sheet1"}
        candidates = [s for s in wb.sheetnames if s not in skip and re.match(r'^\d', s)]
        if candidates:
            return candidates[-1]
        return None

    def _copy_sheet(self, wb, source_name: str, target_name: str):
        """Copy a worksheet within the same workbook."""
        ws_source = wb[source_name]
        ws_target = wb.create_sheet(title=target_name)

        # Copy row-by-row with values and basic formatting
        for row in ws_source.iter_rows(
            min_row=1, max_row=ws_source.max_row, max_col=ws_source.max_column
        ):
            for cell in row:
                new_cell = ws_target.cell(row=cell.row, column=cell.column)
                new_cell.value = cell.value
                if cell.has_style:
                    new_cell.font = copy.copy(cell.font)
                    new_cell.border = copy.copy(cell.border)
                    new_cell.fill = copy.copy(cell.fill)
                    new_cell.number_format = cell.number_format
                    new_cell.alignment = copy.copy(cell.alignment)

        # Copy merged cells
        for merged_range in ws_source.merged_cells.ranges:
            ws_target.merge_cells(str(merged_range))

        # Copy column widths
        for col_idx in range(1, ws_source.max_column + 1):
            col_letter = self._col_letter(col_idx)
            if col_letter in ws_source.column_dimensions:
                ws_target.column_dimensions[col_letter].width = ws_source.column_dimensions[col_letter].width

        # Copy row heights
        for row_idx in range(1, ws_source.max_row + 1):
            if row_idx in ws_source.row_dimensions:
                ws_target.row_dimensions[row_idx].height = ws_source.row_dimensions[row_idx].height

    def _col_letter(self, idx: int) -> str:
        from openpyxl.utils import get_column_letter
        return get_column_letter(idx)

    def _remove_old_data(self, wb, current_sheet: str):
        """Remove 2025-dated sheets and clear 2025 rows from current sheet."""
        import re
        # Remove old 2025 sheets
        sheets_to_remove = []
        for name in wb.sheetnames:
            if name == current_sheet:
                continue
            m = re.search(r'(\d+)\.(\d+)', name)
            if m and int(m.group(1)) <= 12:
                # Assume months 1-12 are date-range sheets; remove old year ones
                # Keep only sheets from 2026 (check format like 1.5-1.9)
                pass
            # Remove sheets with 2025 in the name or from obvious old patterns
            if '2025' in name:
                sheets_to_remove.append(name)

        for name in sheets_to_remove:
            try:
                del wb[name]
            except Exception:
                pass

        # Clear rows with 2025 dates in the current sheet
        ws = wb[current_sheet]
        rows_to_clear = []
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1, max_col=1):
            cell = row[0]
            if cell.value:
                val = str(cell.value)
                if '2025' in val:
                    rows_to_clear.append(cell.row)

        for r in rows_to_clear:
            for col in range(1, ws.max_column + 1):
                ws.cell(row=r, column=col).value = None

    def _read_sheet_content(self, file_path: str) -> str:
        """Read the latest sheet content as a text summary for context."""
        import openpyxl
        wb = openpyxl.load_workbook(file_path)
        sheet_name = self._get_latest_sheet_name(wb)
        if not sheet_name:
            wb.close()
            return ""

        ws = wb[sheet_name]
        lines = []
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 35), values_only=True):
            parts = [str(c) if c is not None else "" for c in row[:5]]
            if any(parts):
                lines.append(" | ".join(parts))

        wb.close()
        return "\n".join(lines)

    def _apply_fill_data(self, ws, fill_data: list[dict], max_data_row: int | None = None):
        """Apply LLM-generated fill data to the worksheet."""
        import re

        # Clear existing D/E content for data rows only (preserve summary section at bottom)
        clear_end = max_data_row if max_data_row is not None else ws.max_row
        for row in ws.iter_rows(min_row=2, max_row=clear_end, min_col=4, max_col=5):
            for cell in row:
                cell.value = None
        for item in fill_data:
            if isinstance(item, dict) and "cell" in item:
                try:
                    value = item.get("value", "")
                    cell_format = item.get("format", "")
                    cell_ref = item["cell"]
                    # Skip cells beyond the data row range (preserve summary section below)
                    m = re.match(r'([A-Z]+)(\d+)', cell_ref)
                    if m:
                        row_num = int(m.group(2))
                        if row_num > clear_end or row_num < 2:
                            continue
                    if cell_format == "date" and isinstance(value, str):
                        try:
                            value = datetime.strptime(value, "%Y-%m-%d")
                        except ValueError:
                            pass
                    ws[cell_ref] = value
                except Exception:
                    pass

    def _fill_empty_cells(self, ws, day_map: dict, start_date: str):
        """Fill any remaining empty D/E cells within day ranges with varied defaults."""
        s = datetime.strptime(start_date, "%Y-%m-%d")

        # Varied defaults by position within half-day — avoid identical text per row
        morning_variants_d = [
            "流程材料更新与日常支持",
            "业务流程数据整理与分析",
            "专项工作材料准备",
            "跨部门沟通与协作对接",
        ]
        morning_variants_e = [
            "完成流程材料更新及PO日常支持",
            "完成业务流程数据整理与分析",
            "完成专项工作材料准备工作",
            "完成跨部门沟通与事务对接",
        ]
        afternoon_variants_d = [
            "专项工作跟进与IT需求沟通",
            "流程优化方案讨论与推进",
            "业务分析与总结报告撰写",
            "L2/L3流程PO支持与答疑",
        ]
        afternoon_variants_e = [
            "完成专项工作跟进及IT需求对接",
            "完成流程优化方案讨论及推进",
            "完成业务分析与总结报告撰写",
            "完成L2/L3流程PO支持与答疑",
        ]
        default_d_last = "工作总结与复盘"
        default_e_last = "完成当日工作总结与复盘"

        for day_idx, (first_row, last_row) in day_map.items():
            d = s + timedelta(days=day_idx)
            day_name = DAY_NAMES[day_idx]

            # Count empty slots per half-day to assign varied defaults
            morning_empty_rows = []
            afternoon_empty_rows = []
            for r in range(first_row, last_row + 1):
                b_val = str(ws.cell(r, 2).value or "").strip()
                d_val = str(ws.cell(r, 4).value or "").strip()
                e_val = str(ws.cell(r, 5).value or "").strip()
                if not d_val:
                    if b_val == "上午":
                        morning_empty_rows.append(r)
                    elif b_val == "下午":
                        afternoon_empty_rows.append(r)
                    elif r == last_row:
                        pass  # handled separately
                    elif r <= (last_row + first_row) // 2:
                        morning_empty_rows.append(r)
                    else:
                        afternoon_empty_rows.append(r)

            # Fill morning empty slots with varied defaults
            for i, r in enumerate(morning_empty_rows):
                variant_idx = i % len(morning_variants_d)
                if not str(ws.cell(r, 4).value or "").strip():
                    ws.cell(r, 4).value = morning_variants_d[variant_idx]
                if not str(ws.cell(r, 5).value or "").strip():
                    ws.cell(r, 5).value = morning_variants_e[variant_idx]

            # Fill afternoon empty slots with varied defaults
            for i, r in enumerate(afternoon_empty_rows):
                variant_idx = i % len(afternoon_variants_d)
                if not str(ws.cell(r, 4).value or "").strip():
                    ws.cell(r, 4).value = afternoon_variants_d[variant_idx]
                if not str(ws.cell(r, 5).value or "").strip():
                    ws.cell(r, 5).value = afternoon_variants_e[variant_idx]

            # Last row of day: summary
            r = last_row
            if not str(ws.cell(r, 4).value or "").strip():
                ws.cell(r, 4).value = default_d_last
            if not str(ws.cell(r, 5).value or "").strip():
                ws.cell(r, 5).value = default_e_last

    # ── LLM generation ───────────────────────────────────────────

    # 中国法定节假日（2026年，日期格式 MM-DD）
    _HOLIDAYS_2026 = {
        "01-01", "01-02", "01-03",  # 元旦
        "02-16", "02-17", "02-18", "02-19", "02-20", "02-21", "02-22",  # 春节（除夕-初六）
        "04-06", "04-07",  # 清明节
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "06-19", "06-20", "06-21",  # 端午节
        "09-25", "09-26", "09-27",  # 中秋节+国庆
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  # 国庆节
    }

    SYSTEM_PROMPT = """你是流程管理周报撰写助手。根据用户输入更新周报Excel的D列（本周计划）和E列（本周总结）。

职责范围：MO（管理商机）和SCE（售前-售后协同）流程体系，6个专项（做准N和T、价格管理、高质量执行MO、售前-售后协同、POC流程发布、SCE大项目大客户支持），IT数字化对接。
日常固定工作：流程L2/L3 PO日常支持、部门AI项目统筹管理与支持。

严禁写入以下内容：DG流程、LTC全链路、CRM系统建设、渠道流程及任何与MO/SCE无关的内容。

固定例会（除非用户明确说改时间，否则保持不变）：
- 周一上午：部门周例会
- 周四下午：MO周例会

核心规则（严格遵守）：
1. **用户输入是唯一依据**：只能根据用户提供的工作内容填写D/E列，不要编造用户没有提到的工作
2. 将用户的口语化描述转为专业流程管理术语，但内容必须是用户说的
3. B列、C列保持不动，只更新D列和E列
4. 用户可能只描述了部分时段的工作，其余时段可以留空（后续会自动补全）
5. 遇到法定节假日，对应日期的工作内容清空
6. 遇到调休工作日（周六/周日上班），按正常工作日处理
7. 返回严格JSON数组"""

    async def _call_llm_for_json(self, prompt: str) -> list[dict]:
        """Call LLM and parse JSON response."""
        import json, logging
        logger = logging.getLogger(__name__)

        response = await llm_service.chat(
            system_prompt=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.2,
            timeout=180.0,
            thinking={"type": "disabled"},
        )

        text = ""
        if response.content:
            for block in response.content:
                block_type = getattr(block, "type", "unknown")
                if hasattr(block, "text") and block.text:
                    text += block.text
                elif block_type in ("thinking", "redacted_thinking"):
                    continue

        logger.info("LLM batch: text_len=%d, stop=%s, blocks=%s, usage_in=%d out=%d",
            len(text), getattr(response, "stop_reason", "?"),
            [(getattr(b, "type", "?"), len(getattr(b, "text", "") or getattr(b, "thinking", "") or "")) for b in (response.content or [])],
            getattr(response.usage, "input_tokens", 0) if response.usage else 0,
            getattr(response.usage, "output_tokens", 0) if response.usage else 0,
        )

        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if not text:
            logger.warning("LLM returned empty text. Blocks: %s",
                [(getattr(b, "type", "?"), len(getattr(b, "text", "") or "")) for b in (response.content or [])])
            return []
        try:
            return json.loads(text)
        except Exception as e:
            logger.warning("Failed to parse LLM JSON: %s. Raw: %s...", e, text[:300])
            return []

    async def _generate_updated_content(
        self, wb, sheet_name: str, start_date: str, end_date: str,
        user_input: str, kb_patterns: str,
    ) -> tuple[list[dict], dict[int, tuple[int, int]]]:
        """Generate fill data with day→row mapping for correct placement.
        Returns (fill_data, day_map).
        """
        ws = wb[sheet_name]
        structure_sample = self._read_existing_structure(ws)

        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")

        # Extract day→row mapping from the copied sheet
        day_map = self._get_day_row_map(ws)

        # Write dates directly (not via LLM) — date-only, no time component
        for day_idx, (first_row, _) in day_map.items():
            d = s + timedelta(days=day_idx)
            cell = ws.cell(row=first_row, column=1)
            cell.value = d
            cell.number_format = 'YYYY-MM-DD'

        # Detect holidays
        holidays_in_week = []
        d = s
        while d <= e:
            mmdd = d.strftime("%m-%d")
            if mmdd in self._HOLIDAYS_2026:
                holidays_in_week.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)

        # Generate per batch: 0-1 (Mon-Tue), 2-3 (Wed-Thu), 4 (Fri)
        batches = [(0, 2), (2, 4), (4, 5)]
        all_data = []

        for day_start, day_end in batches:
            # Build per-row mapping with time slot info so LLM can match work to correct time
            row_details = []
            for di in range(day_start, day_end):
                if di in day_map:
                    rr = day_map[di]
                    d = s + timedelta(days=di)
                    rows_info = []
                    for r in range(rr[0], rr[1] + 1):
                        b_val = str(ws.cell(r, 2).value or "").strip()
                        c_val = str(ws.cell(r, 3).value or "").strip()
                        time_label = f"{b_val} " if b_val else ""
                        time_label += c_val if c_val else "全天"
                        rows_info.append(f"    第{r}行 [{time_label.strip()}]")
                    row_details.append(
                        f"{DAY_NAMES[di]} ({d.strftime('%Y-%m-%d')}) = 第{rr[0]}-{rr[1]}行:\n" + "\n".join(rows_info)
                    )

            prompt_parts = [
                f"周报: {start_date} → {end_date}",
                f"## 行号与时间段映射（根据用户提到的时间匹配到对应行）",
                "\n".join(row_details),
                f"\n## 工作表结构（参考）\n```\n{structure_sample[:800]}\n```",
                f"\n## 用户本周工作（按用户提到的时间段填写到对应行）\n{user_input}",
            ]
            if holidays_in_week:
                prompt_parts.append(f"\n## 节假日: {', '.join(holidays_in_week)}，对应日期所有D/E列留空")
            if kb_patterns:
                prompt_parts.append(f"\n## 日常工作参考\n{kb_patterns[:800]}")

            # Generate explicit time→row hints from user input
            time_hints = self._build_time_hints(ws, day_map, s, user_input, day_start, day_end)
            if time_hints:
                prompt_parts.append(f"\n## 时间→行号强制匹配\n{time_hints}")

            prompt_parts.append("""
## 更新要求
1. **严格按时段匹配**：上面"时间→行号强制匹配"已明确指定了每项工作应填的行号，严格按此填写。用户说"上午"就填「上午」行，说"下午"就填「下午」行，绝不跨时段
2. **只能写用户提到的工作内容**，不要编造用户没说过的内容
3. 同一天内每个时段的D/E列内容必须不同，严禁相邻行出现重复工作
4. 将用户口语描述转为专业表述，但保持原意不变
5. A列日期已填好，不需要更新A列
6. 只更新行号映射范围内的行，不要修改"下周计划与目标"等总结区域
7. 用户没提到的时段不要编造，留空即可
8. 返回JSON数组: [{"cell": "D2", "value": "xxx"}, {"cell": "E2", "value": "xxx"}, ...]""")

            batch_data = await self._call_llm_for_json("\n".join(prompt_parts))
            all_data.extend(batch_data)

        return all_data, day_map

    def _build_time_hints(
        self, ws, day_map: dict, week_start: datetime,
        user_input: str, day_start: int, day_end: int,
    ) -> str:
        """Parse user input for time mentions and generate explicit row assignment hints."""
        import re
        hints = []
        day_names_cn = ["一", "二", "三", "四", "五"]

        for di in range(day_start, day_end):
            if di not in day_map:
                continue
            first_row, last_row = day_map[di]
            d = week_start + timedelta(days=di)
            day_name = DAY_NAMES[di]

            morning_rows = []
            afternoon_rows = []
            for r in range(first_row, last_row + 1):
                b_val = str(ws.cell(r, 2).value or "").strip()
                c_val = str(ws.cell(r, 3).value or "").strip()
                if b_val == "上午":
                    morning_rows.append((r, c_val))
                elif b_val == "下午":
                    afternoon_rows.append((r, c_val))

            day_patterns = [rf'{day_name}', rf'周{day_names_cn[di]}', rf'{d.month}\.{d.day}', rf'{d.month}月{d.day}']
            day_mentioned = any(re.search(p, user_input) for p in day_patterns)
            if not day_mentioned:
                continue

            has_morning = bool(re.search(rf'(?:{day_name}|周{day_names_cn[di]}).*?上午', user_input))
            has_afternoon = bool(re.search(rf'(?:{day_name}|周{day_names_cn[di]}).*?下午', user_input))

            if has_morning and morning_rows:
                row_nums = [str(r) for r, _ in morning_rows]
                hints.append(f"  {day_name}上午工作 → 只能填{'、'.join(row_nums)}行（上午时段）")
            if has_afternoon and afternoon_rows:
                row_nums = [str(r) for r, _ in afternoon_rows]
                hints.append(f"  {day_name}下午工作 → 只能填{'、'.join(row_nums)}行（下午时段）")

        return "\n".join(hints) if hints else ""

    def _get_day_row_map(self, ws) -> dict[int, tuple[int, int]]:
        """Parse which rows belong to each day (Mon=0..Fri=4).

        Unmerges column-A merged cells, clears old dates, finds sections.
        Returns {day_index: (first_row, last_row)} for exactly 5 sections.
        """
        # Unmerge all column-A merged ranges first
        merged_to_unmerge = []
        for merged_range in ws.merged_cells.ranges:
            if merged_range.min_col == 1:
                merged_to_unmerge.append(str(merged_range))
        for mr_str in merged_to_unmerge:
            try:
                ws.unmerge_cells(mr_str)
            except Exception:
                pass

        # Clear old DATE values from column A (only date-formatted values, not summary/goals text)
        for row in range(2, ws.max_row + 1):
            val = ws.cell(row, 1).value
            if val is not None:
                val_str = str(val).strip()
                if val_str and re.match(r'^\d{4}-\d{2}-\d{2}', val_str):
                    ws.cell(row, 1).value = None

        # Now find day sections from row structure.
        # Each "day" starts at a row where column B or C has "上午" or the B-column has a merge.
        # Simpler: divide rows 2..max_row into 5 equal-ish sections based on row count.
        # Even simpler: find B-column merged ranges which mark day boundaries.
        day_boundaries = [2]  # First day always starts at row 2
        b_merges = {}
        for merged_range in ws.merged_cells.ranges:
            if merged_range.min_col == 2 and merged_range.min_row == merged_range.max_row:
                pass  # Single-row B merge, not a day marker
            elif merged_range.min_col == 2:
                b_merges[merged_range.min_row] = merged_range.max_row

        # Find B-column "上午" cells which typically mark the start of a day
        for row in range(3, ws.max_row + 1):
            b_val = str(ws.cell(row, 2).value or "").strip()
            if b_val == "上午":
                day_boundaries.append(row)

        # Limit to 5 days
        day_boundaries = day_boundaries[:5]

        # Build day map
        day_map = {}
        for i, start_row in enumerate(day_boundaries):
            if i + 1 < len(day_boundaries):
                end_row = day_boundaries[i + 1] - 1
            else:
                # Last section: search from bottom up to find summary rows
                # (searching top-down can match content keywords like "课题" in work descriptions)
                end_row = ws.max_row
                for r in range(ws.max_row, start_row, -1):
                    a_val = str(ws.cell(r, 1).value or "")
                    d_val = str(ws.cell(r, 4).value or "")
                    combined = a_val + d_val
                    if any(kw in combined for kw in ["重点", "目标", "计划", "课题", "下周"]):
                        end_row = r - 1
                        break
            if end_row >= start_row:
                day_map[i] = (start_row, end_row)

        return day_map

    def _merge_date_cells(self, ws, day_map: dict):
        """Re-merge A-column cells for each day's row range after writing dates."""
        from openpyxl.utils import get_column_letter
        for day_idx, (first_row, last_row) in day_map.items():
            if last_row > first_row:
                try:
                    ws.merge_cells(None, first_row, 1, last_row, 1)
                except Exception:
                    pass

    def _find_summary_row(self, ws, day_map: dict) -> int:
        """Find the row for B/C summary fill — the row below the '本周计划与目标' header."""
        max_data_row = max(r[1] for r in day_map.values()) if day_map else ws.max_row
        # Scan for the header row (A column contains "本周计划")
        for r in range(max_data_row + 1, ws.max_row + 1):
            a_val = str(ws.cell(r, 1).value or "").strip()
            if "本周计划" in a_val or "本周目" in a_val:
                # Content row is right below the header
                content_row = r + 1
                if content_row <= ws.max_row:
                    return content_row
                return r
        # Fallback: skip header content and find first row after data
        for r in range(max_data_row + 1, ws.max_row + 1):
            a_val = str(ws.cell(r, 1).value or "").strip()
            if "计划" in a_val or "目标" in a_val:
                continue
            return r
        return max_data_row + 2

    async def _generate_summary(
        self, ws, day_map: dict, start_date: str, end_date: str,
        user_input: str, kb_patterns: str,
    ) -> list[dict]:
        """Generate summary section: B column (主要进展和成果) and C column (下周计划与目标)."""
        summary_row = self._find_summary_row(ws, day_map)
        max_data_row = max(r[1] for r in day_map.values()) if day_map else ws.max_row

        # Gather daily D/E content for richer context
        daily_context = []
        for r in range(2, max_data_row + 1):
            d_val = str(ws.cell(r, 4).value or "").strip()
            e_val = str(ws.cell(r, 5).value or "").strip()
            if d_val or e_val:
                daily_context.append(f"第{r}行 D={d_val} E={e_val}")
        context_text = "\n".join(daily_context[-30:])  # Last 30 rows for context

        prompt = f"""你是流程管理周报撰写助手。请根据本周实际工作内容，生成"主要进展和成果"和"下周计划与目标"两个部分。

## 本周工作输入
{user_input[:800]}

## 本周已填写的每日工作内容
{context_text[:2000]}

## 输出格式（严格套用，不可偏离）

### B列（主要进展和成果）—— 三段式模板（紧凑排版）

每个子项一行，用「·」分隔三段：**业务主题 · 执行动作与进度 · 业务价值与结果**，严禁多余空行。

格式模板：
```
1、[大模块名称]
1.1 【xx专项】完成xx / 推进xx / 输出xx，当前处于xx阶段 · 提升效率xx%、缩短周期xx天、降低xx风险

1.2 【xx优化】梳理xx流程 / 对齐xx方案 / 上线xx功能 · 预计减少xx成本、提升xx质量

2、[下一个大模块]
2.1 ...
```

### 约束规则（必须遵守）

1. 每条子项（1.1, 1.2...）**一行写完**，三要素用「·」连接，不换行、不留空行
2. 【业务主题】用【】标注，10字以内概括
3. 动作用「/」串联，动词开头（完成/推进/输出/梳理/对齐/上线/发布/优化/协调/支持）
4. 价值量化或定性说明，禁止"持续推进""继续跟进"等空洞表述
5. 模块间不留空行，只在模块标题前换行
6. 5-8个模块，每条子项50-80字
    ...
```

### C列（下周计划与目标）

紧凑格式，每条一行：
```
1、[大模块名称]
1.1 [重点动作]，目标：[预期结果]
1.2 ...
```
约束：C列3-5个模块，每条30-60字，一行写完不换行

只返回2个单元格的JSON数组: [{{"cell": "B{summary_row}", "value": "..."}}, {{"cell": "C{summary_row}", "value": "..."}}]"""

        return await self._call_llm_for_json(prompt)

    def _apply_summary_data(self, ws, summary_data: list[dict]):
        """Apply summary data to B/C columns only (A column preserved from template).
        Only writes to cells within the original sheet range (no row extension).
        """
        import re
        for item in summary_data:
            if isinstance(item, dict) and "cell" in item:
                try:
                    cell_ref = item["cell"]
                    col_letter = cell_ref[0] if cell_ref else ""
                    if col_letter not in ("B", "C"):
                        continue  # Only write B and C columns
                    value = item.get("value", "")
                    m = re.match(r'([A-Z]+)(\d+)', cell_ref)
                    if m:
                        row_num = int(m.group(2))
                        if row_num > ws.max_row:
                            continue
                    if isinstance(value, str) and value.strip():
                        value = value.strip()
                    ws[cell_ref] = value
                except Exception:
                    pass

    def _read_existing_structure(self, ws) -> str:
        """Read existing sheet structure — just first 20 rows as format sample."""
        lines = []
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 20), values_only=True):
            parts = []
            for i, c in enumerate(row[:5]):
                v = str(c).strip() if c is not None else ""
                parts.append(v)
            if any(parts):
                lines.append(" | ".join(parts))
        lines.append(f"... (总行数: {ws.max_row})")
        return "\n".join(lines)

    def _build_update_prompt(
        self, existing_structure: str, start_date: str, end_date: str,
        user_input: str, kb_patterns: str,
    ) -> str:
        s = datetime.strptime(start_date, "%Y-%m-%d")
        e = datetime.strptime(end_date, "%Y-%m-%d")
        today = datetime.now()

        days_info = []
        for i in range(5):
            d = s + timedelta(days=i)
            days_info.append(f"  {DAY_NAMES[i]} → {d.strftime('%Y-%m-%d')}（{d.month}月{d.day}日）")

        parts = [
            f"周报时间: {start_date} → {end_date}",
            f"日期映射: " + " | ".join(days_info),
            f"工作表结构 (前20行):\n```\n{existing_structure[:1500]}\n```",
            f"用户本周工作 (最高优先级):\n{user_input}",
        ]
        if kb_patterns:
            parts.append(f"日常工作模式参考:\n{kb_patterns[:1000]}")

        parts.append("""
## 更新要求
1. A列日期修正为对应日期 (YYYY-MM-DD)
2. D列填"本周计划"事项, E列填成果/进展
3. 每天上午2-3个时段, 下午2-3个时段
4. 返回JSON数组: [{"cell": "A2", "value": "2026-05-25", "format": "date"}, {"cell": "D2", "value": "..."}, {"cell": "E2", "value": "..."}, ...]
只输出需要更新的单元格。""")

        return "\n".join(parts)

    async def _search_knowledge_base(self) -> str:
        try:
            from app.services.rag_service import rag_service
            ctx = await rag_service.search("周工作总结 日常工作 流程优化")
            return ctx or ""
        except Exception:
            return ""

    # ── helpers ──────────────────────────────────────────────────

    def _has_date_specifier(self, message: str) -> bool:
        """Check if message explicitly specifies a date or week reference."""
        patterns = [
            r'\d{4}-\d{2}-\d{2}',     # ISO date: 2026-06-08
            r'\d+月\d+[日号]',
            r'\d+\.\d+',
            r'\d+/\d+',
            r'下周', r'本周', r'这周', r'上周', r'上上周',
        ]
        return any(re.search(p, message) for p in patterns)

    def _build_weeks_data(self) -> list[dict]:
        """Build structured data for 5 recent weeks for the calendar picker UI."""
        today = datetime.now()
        this_monday = today - timedelta(days=today.weekday())
        labels = {-2: "上上周", -1: "上周", 0: "本周", 1: "下周", 2: "下下周"}
        weeks = []
        for offset in range(-2, 3):
            monday = this_monday + timedelta(weeks=offset)
            sunday = monday + timedelta(days=6)
            weeks.append({
                "label": labels[offset],
                "is_current": offset == 0,
                "offset": offset,
                "start": monday.strftime("%Y-%m-%d"),
                "end": sunday.strftime("%Y-%m-%d"),
                "monday": f"{monday.month}月{monday.day}日",
                "sunday": f"{sunday.month}月{sunday.day}日",
            })
        return weeks

    def _parse_date_range(self, message: str) -> tuple[str, str]:
        today = datetime.now()
        patterns = [
            # ISO format: 2026-06-08到2026-06-14
            (r"(\d{4})-(\d{2})-(\d{2})\s*[到至-]\s*(\d{4})-(\d{2})-(\d{2})", 6),
            # Chinese format: 5月25日-5月31日
            (r"(\d+)月(\d+)[日号]\s*[到至-]\s*(\d+)月(\d+)[日号]", 4),
            # Dot format: 5.25-5.31
            (r"(\d+)\.(\d+)\s*[-到至]\s*(\d+)\.(\d+)", 4),
            # Slash format: 5/25-5/31
            (r"(\d+)/(\d+)\s*[-到至]\s*(\d+)/(\d+)", 4),
        ]
        for pattern, n_groups in patterns:
            m = re.search(pattern, message)
            if m:
                groups = m.groups()
                if n_groups == 6:
                    # ISO format: extract year from the date
                    y1, m1, d1, y2, m2, d2 = [int(g) for g in groups]
                    return f"{y1}-{m1:02d}-{d1:02d}", f"{y2}-{m2:02d}-{d2:02d}"
                elif len(groups) == 4:
                    m1, d1, m2, d2 = int(groups[0]), int(groups[1]), int(groups[2]), int(groups[3])
                    year = today.year
                    return f"{year}-{m1:02d}-{d1:02d}", f"{year}-{m2:02d}-{d2:02d}"
        if "下周" in message:
            days_until_monday = 7 - today.weekday()
            next_monday = today + timedelta(days=days_until_monday)
            next_sunday = next_monday + timedelta(days=6)
            return next_monday.strftime("%Y-%m-%d"), next_sunday.strftime("%Y-%m-%d")
        # "本周" or default → this Monday to Sunday
        this_monday = today - timedelta(days=today.weekday())
        this_sunday = this_monday + timedelta(days=6)
        return this_monday.strftime("%Y-%m-%d"), this_sunday.strftime("%Y-%m-%d")

    def _extract_work_details(self, message: str) -> str:
        msg = message.strip()
        for trigger in self.triggers:
            if msg.startswith(trigger):
                msg = msg[len(trigger):].lstrip("，,：:；;！!\n ")
                break
        for trigger in self.triggers:
            msg = msg.replace(trigger, "")
        msg = msg.strip().lstrip("，,：:；;！!\n ")
        return msg if len(msg) >= MIN_DETAIL_LENGTH else ""

    def _build_summary(
        self, fill_data: list[dict], start_date: str, end_date: str, filename: str, sheet_name: str
    ) -> str:
        days = set()
        for item in fill_data:
            if isinstance(item, dict) and item.get("format") == "date":
                days.add(str(item.get("value", ""))[:10])

        cells_updated = len([i for i in fill_data if isinstance(i, dict) and i.get("format") != "date"])
        lines = [
            "✅ 周报已生成！",
            "",
            f"📅 时间范围: {start_date} ~ {end_date}",
            f"📋 新增工作表: {sheet_name}",
            f"📄 文件: {filename}",
            f"📊 覆盖 {len(days)} 天，更新 {cells_updated} 个单元格",
            "",
            "📁 工作流说明：",
            "  ① 已从上周工作表复制内容作为模板",
            f"  ② 新建工作表「{sheet_name}」",
            "  ③ 已更新D列（本周计划）和E列（本周总结）",
            "  ④ 已修正A列日期为本周日期",
        ]

        preview_items = [i for i in fill_data if isinstance(i, dict) and i.get("format") != "date"][:6]
        if preview_items:
            lines.append("")
            lines.append("📝 内容预览:")
            for item in preview_items:
                lines.append(f"  • {item.get('cell', '?')}: {str(item.get('value', ''))[:60]}")

        return "\n".join(lines)
