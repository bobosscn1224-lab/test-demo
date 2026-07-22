"""Rich Response Formatter — transforms plain text into structured HTML.

Converts LLM plain-text output into visually structured, easy-to-read HTML with:
  - Section cards with headers
  - Key-point callouts
  - Structured lists and tables
  - Action-item checklists
  - Visual hierarchy (color-coded priorities, dividers)

Also includes the Interactive Follow-up module:
  - Goal-met check
  - Related question suggestions
  - Deep-dive predictions
"""
from __future__ import annotations

import json
import logging
import re

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

CSS_TEMPLATE = """<style>
.ai-response { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; line-height: 1.9; color: #1a1a2e; max-width: 800px; font-size: 15px; }
.ai-response h2 { color: #1e3a5f; border-left: 5px solid #3b82f6; padding: 4px 0 4px 16px; margin: 28px 0 14px; font-size: 1.25em; letter-spacing: 0.02em; }
.ai-response h3 { color: #334155; margin: 20px 0 10px; font-size: 1.08em; font-weight: 600; }
.ai-response p { margin: 8px 0; }
.ai-response strong { color: #1e40af; }
.ai-response .card { border-radius: 10px; padding: 16px 20px; margin: 14px 0; border: 1px solid #e2e8f0; }
.ai-response .card.summary { background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border-left: 5px solid #3b82f6; }
.ai-response .card.summary::before { content: '📋 摘要'; display: block; font-weight: 700; color: #1e40af; margin-bottom: 8px; font-size: 0.95em; }
.ai-response .card.highlight { background: #fffbeb; border-left: 5px solid #f59e0b; }
.ai-response .card.highlight::before { content: '💡 关键要点'; display: block; font-weight: 700; color: #92400e; margin-bottom: 8px; font-size: 0.95em; }
.ai-response .card.action { background: #f0fdf4; border-left: 5px solid #22c55e; }
.ai-response .card.action::before { content: '✅ 行动建议'; display: block; font-weight: 700; color: #166534; margin-bottom: 8px; font-size: 0.95em; }
.ai-response .card.warning { background: #fef2f2; border-left: 5px solid #ef4444; }
.ai-response .card.warning::before { content: '⚠️ 注意事项'; display: block; font-weight: 700; color: #991b1b; margin-bottom: 8px; font-size: 0.95em; }
.ai-response .card.info { background: #f0f9ff; border-left: 5px solid #0ea5e9; }
.ai-response .card.info::before { content: '📌 补充信息'; display: block; font-weight: 700; color: #075985; margin-bottom: 8px; font-size: 0.95em; }
.ai-response .card.steps { background: #faf5ff; border-left: 5px solid #a855f7; }
.ai-response .card.steps::before { content: '🔢 步骤流程'; display: block; font-weight: 700; color: #6b21a8; margin-bottom: 8px; font-size: 0.95em; }
.ai-response ol { padding-left: 24px; margin: 8px 0; }
.ai-response ol li { margin: 8px 0; padding: 4px 0; }
.ai-response ul { padding-left: 20px; margin: 8px 0; list-style: none; }
.ai-response ul li { margin: 6px 0; padding: 2px 0 2px 20px; position: relative; }
.ai-response ul li::before { content: '●'; color: #3b82f6; position: absolute; left: 0; font-size: 0.55em; top: 6px; }
.ai-response ul.checklist { list-style: none; padding-left: 4px; }
.ai-response ul.checklist li { padding-left: 24px; }
.ai-response ul.checklist li::before { content: '☐'; color: #22c55e; font-size: 1em; top: 2px; left: 0; }
.ai-response table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 0.93em; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.ai-response th { background: #f1f5f9; padding: 12px 16px; text-align: left; font-weight: 600; color: #334155; border-bottom: 2px solid #cbd5e0; }
.ai-response td { padding: 10px 16px; border-bottom: 1px solid #f1f5f9; }
.ai-response tr:last-child td { border-bottom: none; }
.ai-response em { color: #64748b; font-style: italic; }
.ai-response hr { border: none; border-top: 1px solid #e2e8f0; margin: 24px 0; }
.ai-response .tag { display: inline-block; padding: 3px 12px; border-radius: 14px; font-size: 0.82em; margin: 2px 4px; font-weight: 500; }
.ai-response .tag.primary { background: #dbeafe; color: #1e40af; }
.ai-response .tag.success { background: #dcfce7; color: #166534; }
.ai-response .tag.warn { background: #fef3c7; color: #92400e; }
.ai-response .tag.danger { background: #fee2e2; color: #991b1b; }
.ai-response .followup { background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%); border-radius: 12px; padding: 18px 22px; margin: 24px 0 4px; border: 1px solid #bfdbfe; }
.ai-response .followup h4 { margin: 0 0 12px; color: #1e40af; font-size: 1em; }
.ai-response .followup .btn { display: inline-block; padding: 7px 16px; margin: 4px 6px 4px 0; background: white; border: 1px solid #93c5fd; border-radius: 20px; cursor: pointer; font-size: 0.9em; color: #1e40af; transition: all 0.15s; }
.ai-response .followup .btn:hover { background: #3b82f6; color: white; border-color: #3b82f6; }
.ai-response .stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 14px 0; }
.ai-response .stat-card { background: #f8fafc; border-radius: 10px; padding: 16px; text-align: center; border: 1px solid #e2e8f0; }
.ai-response .stat-card .num { font-size: 1.8em; font-weight: 700; color: #1e40af; }
.ai-response .stat-card .label { font-size: 0.85em; color: #64748b; margin-top: 4px; }
</style>"""

ICON_MAP = {
    "总结": "📋", "摘要": "📋", "概述": "📋", "背景": "📌",
    "要点": "💡", "关键": "💡", "核心": "💡", "重点": "💡",
    "建议": "✅", "行动": "✅", "方案": "✅", "推荐": "✅",
    "注意": "⚠️", "风险": "⚠️", "警告": "⚠️", "问题": "⚠️",
    "步骤": "🔢", "流程": "🔢", "方法": "🔢", "指南": "🔢",
    "补充": "📌", "参考": "📌", "说明": "📌",
    "定义": "📖", "概念": "📖", "解释": "📖",
    "示例": "📝", "案例": "📝", "举例": "📝",
    "优势": "🌟", "价值": "🌟", "好处": "🌟",
    "对比": "📊", "比较": "📊", "区别": "📊",
    "数据": "📈", "指标": "📈", "统计": "📈",
    "时间": "📅", "日程": "📅", "计划": "📅",
    "问题": "❓", "疑问": "❓", "FAQ": "❓",
    "工具": "🔧", "资源": "🔧", "平台": "🔧",
}

STRUCTURE_PROMPT = """将以下纯文本内容转换为结构化的HTML片段。要求：

1. 识别逻辑结构，用<h2>/<h3>建立层次
2. 关键结论用 <div class="card highlight"> 包裹
3. 行动建议用 <div class="card action"> + 清单格式
4. 风险提示用 <div class="card risk">
5. 对比/参考信息可用 <table>
6. 普通段落保持 <p>
7. 重点词汇用 <strong>
8. 仅输出body内的HTML，不要输出<html>/<head>/<body>标签
9. 不要编造原文没有的内容

原文：
{text}

HTML片段："""

INTERACTION_PROMPT = """根据以下对话内容，生成3-5个互动追问建议：

用户问题：{user_message}
助手回答摘要：{reply_summary}

要求：
1. 第1个：询问是否达到目标/是否满意
2. 第2-3个：预测用户可能关心的相关问题
3. 第4-5个（可选）：进一步深挖的方向

返回JSON数组：
["追问1", "追问2", "追问3"]"""


class ResponseFormatter:
    """Transforms plain text into rich HTML + generates follow-up interactions."""

    # ── HTML formatting ───────────────────────────────────────────────

    async def to_html(self, text: str, use_llm: bool = False) -> str:
        """Convert plain text to rich HTML using smart formatting."""
        # Smart formatter is fast and reliable — LLM formatting optional
        if not use_llm:
            return self._simple_format(text)

        try:
            resp = await llm_service.chat(
                interaction_name="html_formatting",
                system_prompt="你是内容排版专家。将文本转换为结构化HTML片段。只输出HTML。",
                messages=[{"role": "user", "content": STRUCTURE_PROMPT.format(text=text[:6000])}],
                max_tokens=3000,
                temperature=0.2,
                thinking={"type": "disabled"},
            )
            html_body = self._extract(resp)
            if html_body and len(html_body) > 50:
                return CSS_TEMPLATE + f'<div class="ai-response">\n{html_body}\n</div>'
        except Exception as exc:
            logger.warning("HTML formatting failed: %s", exc)

        return self._simple_format(text)

    def _simple_format(self, text: str) -> str:
        """Smart markdown→rich HTML with auto-detected cards and icons."""
        # Split into sections by ## headers
        sections = re.split(r'\n(?=## )', text)
        html_parts: list[str] = []

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Extract top-level heading
            h2_match = re.match(r'^## (.+)$', section, re.MULTILINE)
            heading = h2_match.group(1).strip() if h2_match else ""
            body = section[h2_match.end():].strip() if h2_match else section

            if heading:
                icon = self._pick_icon(heading)
                html_parts.append(f'<h2>{icon} {heading}</h2>')

            # Detect content type and wrap in appropriate card
            card_type = self._detect_card_type(heading, body)
            if card_type:
                body_html = self._format_body(body)
                html_parts.append(f'<div class="card {card_type}">\n{body_html}\n</div>')
            else:
                html_parts.append(self._format_body(body))

        result = '\n'.join(html_parts) if html_parts else self._format_body(text)
        return CSS_TEMPLATE + f'<div class="ai-response">\n{result}\n</div>'

    def _format_body(self, text: str) -> str:
        """Format body text: bold, lists, tables, paragraphs."""
        html = text
        # Tables: detect |---|---| pattern
        if '|' in html and '---' in html:
            html = self._format_table(html)
        # ### headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        # Numbered items like "1. " "2. " → ordered list
        if re.search(r'^\d+\.\s', html, re.MULTILINE):
            html = self._format_ordered_list(html)
        # Bullet points
        html = re.sub(r'^[-*•]\s+(.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        # Wrap consecutive <li> in <ul>
        html = re.sub(r'(<li>.*?</li>\n?)+', lambda m: f'<ul>\n{m.group(0)}</ul>\n', html)
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        # Italic
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        # Inline code
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
        # Horizontal rules
        html = re.sub(r'^---+\s*$', r'<hr>', html, flags=re.MULTILINE)
        # Tags: #tag-name → <span class="tag primary">
        html = re.sub(r'#(\w+)', r'<span class="tag primary">\1</span>', html)
        # Paragraphs: blank lines
        html = re.sub(r'\n\n+', '</p><p>', html)
        if not html.startswith('<'):
            html = f'<p>{html}'
        if not html.endswith('>'):
            html += '</p>'
        # Clean empty <p></p>
        html = re.sub(r'<p>\s*</p>', '', html)
        return html

    def _format_table(self, text: str) -> str:
        """Convert markdown table to HTML table."""
        lines = text.strip().split('\n')
        result = ['<table>']
        in_header = True
        for line in lines:
            if '---' in line and '|' in line:
                in_header = False
                continue
            if '|' not in line:
                continue
            cells = [c.strip() for c in line.split('|') if c.strip()]
            tag = 'th' if in_header else 'td'
            result.append('<tr>' + ''.join(f'<{tag}>{c}</{tag}>' for c in cells) + '</tr>')
        result.append('</table>')
        # Remove the table lines from original text, return surrounding text + table
        clean = re.sub(r'\|.+\|\n?', '', text)
        clean = re.sub(r'\n\s*\n', '\n\n', clean).strip()
        return clean + '\n' + '\n'.join(result) if clean else '\n'.join(result)

    def _format_ordered_list(self, text: str) -> str:
        """Convert numbered items to <ol>."""
        lines = text.split('\n')
        in_list = False
        result = []
        for line in lines:
            m = re.match(r'^(\d+)[\.\)]\s+(.+)', line)
            if m:
                if not in_list:
                    result.append('<ol>')
                    in_list = True
                result.append(f'<li>{m.group(2)}</li>')
            else:
                if in_list:
                    result.append('</ol>')
                    in_list = False
                result.append(line)
        if in_list:
            result.append('</ol>')
        return '\n'.join(result)

    def _pick_icon(self, heading: str) -> str:
        """Pick an emoji icon based on heading keywords."""
        for kw, icon in sorted(ICON_MAP.items(), key=lambda x: -len(x[0])):
            if kw in heading:
                return icon
        return '📌'

    def _detect_card_type(self, heading: str, body: str) -> str:
        """Detect the semantic type of a section for card wrapping."""
        combined = heading + body
        if any(kw in combined for kw in ['总结', '摘要', '概述', '一句话']):
            return 'summary'
        if any(kw in combined for kw in ['要点', '关键', '核心', '重点']):
            return 'highlight'
        if any(kw in combined for kw in ['建议', '行动', '下一步', '方案', '推荐']):
            return 'action'
        if any(kw in combined for kw in ['注意', '风险', '警告', '避免', '不要']):
            return 'warning'
        if any(kw in combined for kw in ['步骤', '流程', '方法', '指南', '操作']):
            return 'steps'
        if any(kw in combined for kw in ['补充', '说明', '注释', '参考', '背景']):
            return 'info'
        return ""  # no card

    # ── interactive follow-up ─────────────────────────────────────────

    async def generate_followups(self, user_message: str, reply: str) -> list[str]:
        """Generate interactive follow-up questions based on the conversation."""
        try:
            summary = reply[:500] + ("..." if len(reply) > 500 else "")
            resp = await llm_service.chat(
                interaction_name="followup_generation",
                system_prompt="你是用户体验专家。生成自然的追问建议。严格返回JSON数组。",
                messages=[{"role": "user", "content": INTERACTION_PROMPT.format(
                    user_message=user_message[:300],
                    reply_summary=summary,
                )}],
                max_tokens=300,
                temperature=0.4,
                thinking={"type": "disabled"},
            )
            text = self._extract(resp)
            if text.startswith("["):
                questions = json.loads(text)
                return questions[:5]
        except Exception as exc:
            logger.debug("Follow-up generation failed: %s", exc)
        return ["这个回答是否解决了你的问题？", "还有其他需要了解的吗？"]

    def format_followups_html(self, questions: list[str]) -> str:
        """Render follow-up questions as clickable HTML buttons."""
        if not questions:
            return ""
        buttons = "\n".join(
            f'<span class="btn" onclick="this.style.background=\'#bee3f8\'">{q}</span>'
            for q in questions
        )
        return (
            '<div class="followup">\n'
            '<h4>💬 继续探索</h4>\n'
            f'{buttons}\n'
            '</div>'
        )

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract(response) -> str:
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        return text.strip()
