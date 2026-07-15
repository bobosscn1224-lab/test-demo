"""Weekly report LLM operations — prompt building, generation, parsing."""

import json
import logging
import re
from datetime import datetime, timedelta

from app.services.llm_service import llm_service
from .constants import DAY_NAMES, HOLIDAYS_2026, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def call_llm_for_json(prompt: str) -> list[dict]:
    """Call LLM and parse JSON response."""
    response = await llm_service.chat(
        system_prompt=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        temperature=0.2,
        timeout=180.0,
        thinking={"type": "disabled"},
    )

    text = extract_llm_text(response)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if not text:
        logger.warning("LLM returned empty text.")
        return []
    try:
        return json.loads(text)
    except Exception as e:
        logger.warning("Failed to parse LLM JSON: %s. Raw: %s...", e, text[:300])
        return []


def extract_llm_text(response) -> str:
    """Extract plain text from LLM response blocks."""
    text = ""
    if not response or not response.content:
        return text
    for block in response.content:
        block_type = getattr(block, "type", "unknown")
        if hasattr(block, "text") and block.text:
            text += block.text
        elif block_type in ("thinking", "redacted_thinking"):
            continue
    return text


async def search_knowledge_base() -> str:
    """Search RAG for workflow patterns and common tasks."""
    try:
        from app.services.rag_service import rag_service
        ctx = await rag_service.search("周工作总结 日常工作 流程优化")
        return ctx or ""
    except Exception:
        return ""


def build_time_hints(ws, day_map: dict, week_start: datetime, user_input: str, day_start: int, day_end: int) -> str:
    """Parse user input for time mentions and generate explicit row assignment hints."""
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


async def generate_updated_content(
    wb, sheet_name: str, start_date: str, end_date: str,
    user_input: str, kb_patterns: str,
    get_day_map_fn, read_structure_fn,
) -> tuple[list[dict], dict[int, tuple[int, int]]]:
    """Generate fill data with day->row mapping."""
    ws = wb[sheet_name]
    structure_sample = read_structure_fn(ws)

    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")

    day_map = get_day_map_fn(ws)

    # Write dates directly
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
        if mmdd in HOLIDAYS_2026:
            holidays_in_week.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    # Generate per batch: 0-1 (Mon-Tue), 2-3 (Wed-Thu), 4 (Fri)
    batches = [(0, 2), (2, 4), (4, 5)]
    all_data = []

    for day_start, day_end in batches:
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

        time_hints = build_time_hints(ws, day_map, s, user_input, day_start, day_end)
        if time_hints:
            prompt_parts.append(f"\n## 时间→行号强制匹配\n{time_hints}")

        prompt_parts.append("""
## 更新要求（两层策略）
**第一层 — 用户明确内容（最高优先级）**：
1. 严格按时段匹配到对应行号
2. 原文保留，不扩展不润色。用户说"开会"就写"开会"
3. 用户明确提到的时段必须精准填入

**第二层 — 空白时段（智能补全）**：
4. 用户没说到的时段，参考「日常工作参考」中的历史模式补全
5. 日常固定工作（如流程L2/L3 PO日常支持、部门AI项目统筹管理）按惯例填入对应时段
6. 补全内容必须与历史周报风格一致，不编造不存在的工作
7. 补全时D列（本周计划）和E列（本周总结）都要填，D列写计划事项，E列写完成情况
8. 遇到法定节假日所有D/E列留空

**通用**：
9. 同一天内每个时段D/E列内容不同，严禁相邻行重复
10. A列已填好不更新，不碰总结区域
11. 返回JSON数组: [{"cell": "D2", "value": "xxx"}, {"cell": "E2", "value": "xxx"}, ...]""")

        batch_data = await call_llm_for_json("\n".join(prompt_parts))
        all_data.extend(batch_data)

    return all_data, day_map


async def generate_summary(
    ws, day_map: dict, start_date: str, end_date: str,
    user_input: str, kb_patterns: str,
    find_summary_row_fn,
) -> list[dict]:
    """Generate summary section: B column (进展成果) and C column (下周计划)."""
    summary_row = find_summary_row_fn(ws, day_map)
    max_data_row = max(r[1] for r in day_map.values()) if day_map else ws.max_row

    daily_context = []
    for r in range(2, max_data_row + 1):
        d_val = str(ws.cell(r, 4).value or "").strip()
        e_val = str(ws.cell(r, 5).value or "").strip()
        if d_val or e_val:
            daily_context.append(f"第{r}行 D={d_val} E={e_val}")
    context_text = "\n".join(daily_context[-30:])

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

### C列（下周计划与目标）
紧凑格式，每条一行：
```
1、[大模块名称]
1.1 [重点动作]，目标：[预期结果]
1.2 ...
```
约束：C列3-5个模块，每条30-60字，一行写完不换行

只返回2个单元格的JSON数组: [{{"cell": "B{summary_row}", "value": "..."}}, {{"cell": "C{summary_row}", "value": "..."}}]"""

    return await call_llm_for_json(prompt)
