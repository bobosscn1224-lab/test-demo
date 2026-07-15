"""Stage: briefing — understand PPT goals BEFORE generating outline."""

from app.skills.base import SkillContext, SkillResult

BRIEFING_PROMPT = """好的！在开始制作之前，先了解几个关键信息，帮你把 PPT 做得更精准。

请回复以下 5 个问题（可以直接在问题后面写答案，也可以给一个综合描述）：

**Q1: 应用场景和目的？**
A. 业务汇报  B. 项目方案  C. 产品宣讲
D. 培训辅导  E. 复盘总结  F. 故事讲解/路演
G. 其他（请简述）

**Q2: 主要听众是谁？**
A. 老板/管理层  B. 客户/外部合作方
C. 一线团队/员工  D. 投资人  E. 混合

**Q3: 期望的PPT规模和深度？**
A. 精简版（8-12页）
B. 标准版（15-20页）
C. 完整版（25-35页）

**Q4: 视觉风格偏好？**
A. 专业严谨  B. 科技感  C. 简约商务  D. 你定

**Q5: 听众必须记住的 3-5 个关键信息？**
（可先给大概方向，后面再细化）

---
例如可以这样回复：
Q1-B 给老板申请预算 | Q2-A | Q3-B | Q4-C | Q5-降本增效、追赶竞品、AI价值"""


async def handle(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """Parse user's briefing answers and confirm."""
    msg = context.user_message.strip()
    briefing = session.get("briefing", {})

    # Check if user has provided answers (message contains Q labels or pipe separators)
    parsed = _parse_briefing(msg)
    if parsed:
        briefing.update(parsed)
        sessions[session_id] = {**session, "briefing": briefing, "stage": "briefing_confirm"}
        return _confirm_briefing(briefing)

    # No answers parsed — show questions (first time or re-prompt)
    sessions[session_id] = {**session, "briefing": {}}
    return SkillResult(
        success=True,
        message=BRIEFING_PROMPT,
        data={"skill": "ppt_maker", "stage": "briefing"},
    )

    # Couldn't parse well — ask again with the example
    return SkillResult(
        success=True,
        message="没太看清楚，请按这个格式回复：\n\nQ1-选项 | Q2-选项 | Q3-选项 | Q4-选项 | Q5-关键信息\n\n例如：Q1-B | Q2-A | Q3-B | Q4-C | Q5-降本增效、追赶竞品",
        data={"skill": "ppt_maker", "stage": "briefing"},
    )


async def handle_confirm(context: SkillContext, session: dict, sessions: dict, session_id: str) -> SkillResult:
    """User confirms or modifies briefing."""
    msg = context.user_message.strip()
    briefing = session.get("briefing", {})

    if _is_confirm(msg):
        sessions[session_id] = {**session, "stage": "outline"}
        return SkillResult(
            success=True,
            message="需求已确认！请上传文档或直接输入内容，我将基于你的需求生成专业大纲。",
            data={"skill": "ppt_maker", "stage": "outline"},
        )

    # Modification — parse new answers
    parsed = _parse_briefing(msg)
    if parsed:
        briefing.update(parsed)

    sessions[session_id] = {**session, "briefing": briefing}
    return _confirm_briefing(briefing)


def _confirm_briefing(briefing: dict) -> SkillResult:
    """Summarize and ask for confirmation."""
    lines = [
        "## PPT 需求确认\n",
        f"**场景目的**：{briefing.get('purpose', '未填写')}",
        f"**目标听众**：{briefing.get('audience', '未填写')}",
        f"**期望规模**：{briefing.get('scope', '未填写')}",
        f"**视觉风格**：{briefing.get('style', '未填写')}",
        f"**关键信息**：{briefing.get('key_message', '未填写')}\n",
        "---\n",
        "确认无误请回复「**确认**」，需要修改请直接说明。\n",
        "确认后将提示你上传素材或输入内容。",
    ]
    return SkillResult(
        success=True,
        message="\n".join(lines),
        data={"skill": "ppt_maker", "stage": "briefing_confirm"},
    )


def _parse_briefing(msg: str) -> dict:
    """Parse briefing answers from user message. Returns dict with found fields."""
    result = {}
    m = msg.strip()

    # Try structured format: Q1-xxx | Q2-xxx | ...
    import re

    # Map Q numbers to keys
    q_map = {"1": "purpose", "2": "audience", "3": "scope", "4": "style", "5": "key_message"}
    # Also match Chinese labels
    patterns = [
        (r'Q?\s*1[：:\- ]\s*(.+?)(?=Q?\s*2[：:\- ]|\||$)', 'purpose'),
        (r'Q?\s*2[：:\- ]\s*(.+?)(?=Q?\s*3[：:\- ]|\||$)', 'audience'),
        (r'Q?\s*3[：:\- ]\s*(.+?)(?=Q?\s*4[：:\- ]|\||$)', 'scope'),
        (r'Q?\s*4[：:\- ]\s*(.+?)(?=Q?\s*5[：:\- ]|\||$)', 'style'),
        (r'Q?\s*5[：:\- ]\s*(.+?)$', 'key_message'),
    ]
    for pat, key in patterns:
        match = re.search(pat, m, re.S | re.I)
        if match:
            result[key] = match.group(1).strip().rstrip('|').strip()

    # Also try pipe-separated format: A | B | C | D | xxx
    if not result:
        parts = [p.strip() for p in m.split('|')]
        keys = ['purpose', 'audience', 'scope', 'style', 'key_message']
        for i, part in enumerate(parts):
            if i < len(keys) and part:
                result[keys[i]] = part

    # Single letter answers: map A-F to labels
    labels = {
        "A": "业务汇报", "B": "项目方案", "C": "产品宣讲",
        "D": "培训辅导", "E": "复盘总结", "F": "故事讲解/路演", "G": "其他",
    }
    for key in ['purpose', 'audience', 'scope', 'style']:
        val = result.get(key, "").strip().upper()
        if val in labels:
            result[key] = labels[val]

    return result


def _is_confirm(msg: str) -> bool:
    m = msg.strip().lower()
    if len(m) > 10:
        return False
    return any(w in m for w in ["确认", "可以", "ok", "yes", "好", "行", "确定", "没问题"])
