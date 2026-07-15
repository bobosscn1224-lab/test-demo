"""Multi-dimensional Perception Engine (MPF).

Analyzes each user message across 5 perception dimensions before the LLM
generates a response.  The perception summary enriches the system prompt,
enabling the assistant to respond with better contextual awareness.

Dimensions:
  1. Emotion     — 情绪感知 (anxiety/excitement/defensiveness/confidence)
  2. Intent      — 意图推断 (consult/complain/negotiate/learn/decide)
  3. Subtext     — 潜台词感知 (what is NOT said but implied)
  4. Truth       — 真实性校验 (factual consistency, exaggeration cues)
  5. Logic       — 逻辑链追踪 (argument structure, reasoning path)

Architecture aligns with: Perception Layer → Reasoning Layer → Expression Layer
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


@dataclass
class PerceptionResult:
    """Structured output of a perception analysis."""
    emotion: dict = field(default_factory=lambda: {"primary": "neutral", "vector": {}, "confidence": 0.5})
    intent: dict = field(default_factory=lambda: {"primary": "咨询", "secondary": "", "confidence": 0.5})
    subtext: str = ""
    truth_flags: list[str] = field(default_factory=list)
    logic_pattern: str = ""
    stage: str = "exploration"  # opening/exploration/discussion/decision/closing
    contradictions: list[str] = field(default_factory=list)
    summary: str = ""


PERCEPTION_PROMPT = """分析以下用户消息，从5个维度进行感知。基于对话历史和当前消息。

## 对话历史（最近3轮）
{history}

## 当前用户消息
{message}

## 分析维度

1. **情绪感知**：识别用户的情绪状态。情绪：积极/消极/中性；特征：焦虑/兴奋/防御/犹豫/果断/不满/满意
2. **意图推断**：用户发起对话的核心目的。类型：咨询/投诉/谈判/学习/决策/验证/闲聊
3. **潜台词感知**：用户可能没说出来的真实需求或顾虑是什么？
4. **真实性校验**：用户表述中是否存在矛盾、夸大（"绝对""100%"）或模糊回避（"可能""大概"）等信号？
5. **逻辑链追踪**：用户的论证结构是什么？（先肯定后否定/先否定后探索/因果链/对比分析/直接断言）
6. **对话阶段**：当前处于对话的哪个阶段？opening/exploration/discussion/decision/closing
7. **矛盾检测**：不同维度之间是否存在矛盾？（如：言语积极但情绪防御，或声称满意但逻辑上在回避）

返回严格JSON（不要markdown）：
{{
  "emotion": {{"primary": "积极|消极|中性", "features": ["焦虑","兴奋","防御"...], "confidence": 0.0-1.0}},
  "intent": {{"primary": "咨询|投诉|谈判|学习|决策|验证|闲聊", "secondary": "...", "confidence": 0.0-1.0}},
  "subtext": "潜台词描述（一句话），没有则为空字符串",
  "truth_flags": ["绝对化词汇", "模糊回避", "具体数据可信"...],
  "logic_pattern": "论证结构描述（一句话），没有则为空字符串",
  "stage": "opening|exploration|discussion|decision|closing",
  "contradictions": ["矛盾描述"...],
  "summary": "综合感知摘要（50字内）"
}}"""


class PerceptionEngine:
    """Analyzes user messages across multiple dimensions before LLM generation."""

    # ── public API ────────────────────────────────────────────────────

    async def perceive(
        self,
        message: str,
        history: list[dict] | None = None,
    ) -> PerceptionResult:
        """Run full multi-dimensional perception on a user message."""
        if len(message) < 3:
            return PerceptionResult()

        # Build history context (last 3 turns)
        hist_text = ""
        if history:
            recent = history[-6:]  # last 3 user+assistant pairs
            for m in recent:
                role = "用户" if m.get("role") == "user" else "助手"
                hist_text += f"{role}: {m.get('content', '')[:200]}\n"

        prompt = PERCEPTION_PROMPT.format(
            history=hist_text or "（无历史）",
            message=message[:1000],
        )

        try:
            resp = await llm_service.chat(
                system_prompt="你是用户感知分析专家。从多个维度分析用户消息。严格返回JSON。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.1,
                thinking={"type": "disabled"},
            )
            text = self._extract(resp)
            data = json.loads(text)
        except Exception as exc:
            logger.debug("Perception analysis failed: %s", exc)
            return PerceptionResult(summary="感知分析暂时不可用")

        # Build structured result
        emo = data.get("emotion", {})
        intent = data.get("intent", {})

        result = PerceptionResult(
            emotion={
                "primary": emo.get("primary", "neutral"),
                "features": emo.get("features", []),
                "confidence": float(emo.get("confidence", 0.5)),
            },
            intent={
                "primary": intent.get("primary", "咨询"),
                "secondary": intent.get("secondary", ""),
                "confidence": float(intent.get("confidence", 0.5)),
            },
            subtext=str(data.get("subtext", "") or ""),
            truth_flags=list(data.get("truth_flags", []) or []),
            logic_pattern=str(data.get("logic_pattern", "") or ""),
            stage=str(data.get("stage", "exploration") or "exploration"),
            contradictions=list(data.get("contradictions", []) or []),
            summary=str(data.get("summary", "") or ""),
        )
        return result

    # ── context injection ─────────────────────────────────────────────

    def to_context(self, p: PerceptionResult) -> str:
        """Convert perception result to a compact context string for system prompt."""
        if not p.summary:
            return ""

        parts = [f"## 用户感知分析\n{p.summary}"]

        if p.emotion.get("primary") and p.emotion["primary"] != "neutral":
            features = "、".join(p.emotion.get("features", [])[:3])
            parts.append(f"- 情绪：{p.emotion['primary']}（{features}）")

        if p.intent.get("primary"):
            secondary = f" / {p.intent['secondary']}" if p.intent.get("secondary") else ""
            parts.append(f"- 意图：{p.intent['primary']}{secondary}")

        if p.subtext:
            parts.append(f"- 潜台词：{p.subtext}")

        if p.truth_flags:
            parts.append(f"- 真实性信号：{'、'.join(p.truth_flags[:3])}")

        if p.logic_pattern:
            parts.append(f"- 论证模式：{p.logic_pattern}")

        if p.contradictions:
            parts.append(f"- ⚠️ 感知矛盾：{'；'.join(p.contradictions[:2])}")

        # Stage-based guidance
        stage_guidance = {
            "opening": "用户处于开场阶段，优先建立信任和明确需求",
            "exploration": "用户处于探索阶段，提供结构化信息和对比分析",
            "discussion": "用户处于讨论阶段，聚焦方案细节和可行性",
            "decision": "用户处于决策阶段，提供确定性、风险提示和行动建议",
            "closing": "对话收尾阶段，确认满意度并提供后续路径",
        }
        if p.stage in stage_guidance:
            parts.append(f"- 对话阶段：{stage_guidance[p.stage]}")

        parts.append("\n请基于以上感知调整回答策略：对准用户意图、回应情绪、破解潜台词。")
        return "\n".join(parts)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract(response) -> str:
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()


# Singleton
perception_engine = PerceptionEngine()
