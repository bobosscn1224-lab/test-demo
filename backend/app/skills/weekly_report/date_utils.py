"""Weekly report date parsing and week calculation utilities."""

import re
from datetime import datetime, timedelta


def has_date_specifier(message: str) -> bool:
    """Check if message explicitly specifies a date or week reference."""
    patterns = [
        r'\d{4}-\d{2}-\d{2}',
        r'\d+月\d+[日号]',
        r'\d+\.\d+',
        r'\d+/\d+',
        r'下周', r'本周', r'这周', r'上周', r'上上周',
    ]
    return any(re.search(p, message) for p in patterns)


def build_weeks_data() -> list[dict]:
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


def parse_date_range(message: str) -> tuple[str, str]:
    """Extract start and end dates from a user message."""
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

    # Default: this Monday to Sunday
    this_monday = today - timedelta(days=today.weekday())
    this_sunday = this_monday + timedelta(days=6)
    return this_monday.strftime("%Y-%m-%d"), this_sunday.strftime("%Y-%m-%d")


def extract_work_details(message: str, triggers: list[str]) -> str:
    """Extract work details from message, stripping trigger prefixes."""
    from .constants import MIN_DETAIL_LENGTH
    msg = message.strip()
    for trigger in triggers:
        if msg.startswith(trigger):
            msg = msg[len(trigger):].lstrip("，,：:；;！!\n ")
            break
    for trigger in triggers:
        msg = msg.replace(trigger, "")
    msg = msg.strip().lstrip("，,：:；;！!\n ")
    return msg if len(msg) >= MIN_DETAIL_LENGTH else ""
