"""Quality Self-Check Engine — reviews LLM output before delivery.

Runs a structured self-assessment against 7 dimensions before the response
reaches the user.  Low-scoring outputs are auto-corrected and re-evaluated.

Architecture aligns with the agent self-improvement framework:
  Mechanism 2 (质量自检) + Evaluation Layer (评估层)
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

CHECK_DIMENSIONS = [
    ("goal_clarity", "目标是否明确", "是否准确回答了用户真正的问题，没有偏离主题"),
    ("logic_completeness", "逻辑是否完整", "是否有背景、分析、结论，结构是否清晰"),
    ("business_fit", "业务是否贴合", "是否结合了具体的业务场景、流程、角色或项目"),
    ("actionability", "内容是否可执行", "是否能转化为具体的动作、标准或下一步建议"),
    ("professionalism", "表达是否专业", "语言是否正式得体，是否适合汇报、评审或文档输出"),
    ("risk_awareness", "风险是否提示", "是否识别并提示了潜在的合规、数据、业务风险"),
    ("format_quality", "格式是否符合", "排版是否清晰，是否使用了适当的标题、列表、表格等结构"),
]

PASS_THRESHOLD = 4   # Average score >= 4 passes (out of 5)
CRITICAL_LOW = 3     # Any single dimension < 3 triggers mandatory fix


@dataclass
class QualityReport:
    """Result of a self-check run."""
    scores: dict[str, int] = field(default_factory=dict)
    comments: dict[str, str] = field(default_factory=dict)
    average: float = 0.0
    passed: bool = False
    fixed: bool = False
    fixed_output: str = ""
    elapsed_ms: int = 0


class QualityChecker:
    """Runs quality self-assessment on assistant responses."""

    def __init__(self, pass_threshold: int = PASS_THRESHOLD, critical_low: int = CRITICAL_LOW):
        self.pass_threshold = pass_threshold
        self.critical_low = critical_low

    # ── public API ────────────────────────────────────────────────────

    async def check(
        self,
        user_message: str,
        assistant_reply: str,
        mode: str = "enhanced",
        attempt: int = 1,
    ) -> QualityReport:
        """Run a full quality check. Returns report with scores + optional fix."""
        t0 = time.monotonic()

        if len(assistant_reply) < 20:
            report = QualityReport(passed=True, elapsed_ms=0)
            logger.debug("Quality check skipped: reply too short")
            return report

        # Step 1: Score
        scores, comments = await self._score(user_message, assistant_reply, mode)
        average = sum(scores.values()) / len(CHECK_DIMENSIONS) if scores else 0
        any_critical = any(v < self.critical_low for v in scores.values())
        passed = average >= self.pass_threshold and not any_critical

        report = QualityReport(
            scores=scores,
            comments=comments,
            average=round(average, 1),
            passed=passed,
            elapsed_ms=int((time.monotonic() - t0) * 1000),
        )

        if not passed and attempt == 1:
            # Step 2: Fix
            logger.info(
                "Quality check FAILED (avg %.1f), attempting auto-fix", average
            )
            fixed = await self._fix(user_message, assistant_reply, scores, comments)
            if fixed:
                # Step 3: Re-check the fix
                recheck = await self.check(user_message, fixed, mode, attempt=2)
                if recheck.passed:
                    report.fixed = True
                    report.fixed_output = fixed
                    report.average = recheck.average
                    report.scores = recheck.scores
                    report.comments = recheck.comments
                    report.passed = True
                    logger.info(
                        "Auto-fix succeeded, new score: %.1f", recheck.average
                    )
                else:
                    logger.info("Auto-fix did not pass (%.1f), keeping original", recheck.average)

        return report

    # ── scoring ──────────────────────────────────────────────────────

    async def _score(
        self, user_message: str, reply: str, mode: str
    ) -> tuple[dict[str, int], dict[str, str]]:
        """Score the reply against all 7 dimensions."""
        dims_text = "\n".join(
            f"{i+1}. {label}：{desc}" for i, (key, label, desc) in enumerate(CHECK_DIMENSIONS)
        )
        prompt = (
            "你是一个输出质量评估专家。请对以下回答进行评分。\n\n"
            "## 用户问题\n"
            f"{user_message[:500]}\n\n"
            "## 助手回答\n"
            f"{reply[:3000]}\n\n"
            "## 评分维度（每项1-5分）\n"
            f"{dims_text}\n\n"
            "模式：{'知识库模式-回答必须严格基于知识库' if mode == 'kb_only' else '增强模式-可补充最佳实践'}\n\n"
            "返回严格JSON（不要markdown）：\n"
            '{"scores":{"goal_clarity":4,"logic_completeness":5,...},'
            '"comments":{"goal_clarity":"一句话评语",...}}'
        )
        try:
            resp = await llm_service.chat(
                interaction_name="quality_scoring",
                system_prompt="你是输出质量评估专家。严格返回JSON格式。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.1,
                thinking={"type": "disabled"},
            )
            text = self._extract(resp)
            data = json.loads(text)
            scores = {k: int(data.get("scores", {}).get(k, 3)) for k, _, _ in CHECK_DIMENSIONS}
            comments = {k: str(data.get("comments", {}).get(k, "")) for k, _, _ in CHECK_DIMENSIONS}
            return scores, comments
        except Exception as exc:
            logger.warning("Quality scoring failed: %s", exc)
            return (
                {k: 3 for k, _, _ in CHECK_DIMENSIONS},
                {k: "评分异常" for k, _, _ in CHECK_DIMENSIONS},
            )

    # ── fixing ───────────────────────────────────────────────────────

    async def _fix(
        self,
        user_message: str,
        original: str,
        scores: dict[str, int],
        comments: dict[str, str],
    ) -> str:
        """Ask LLM to rewrite the reply, addressing the low-scoring dimensions."""
        low_dims = [
            f"- {label}（{scores.get(key, 0)}分）：{comments.get(key, '需改进')}"
            for key, label, _ in CHECK_DIMENSIONS
            if scores.get(key, 0) < PASS_THRESHOLD
        ]

        prompt = (
            "请根据以下质量反馈，优化你的回答。\n\n"
            "## 用户原问题\n"
            f"{user_message[:500]}\n\n"
            "## 原始回答\n"
            f"{original[:3000]}\n\n"
            "## 需要改进的维度\n"
            f"{chr(10).join(low_dims)}\n\n"
            "要求：\n"
            "- 保持原回答的核心信息和正确部分\n"
            "- 重点改进评分低的维度\n"
            "- 结构清晰、专业得体\n"
            "- 直接输出优化后的完整回答，不要加解释"
        )
        try:
            resp = await llm_service.chat(
                interaction_name="quality_fix",
                system_prompt="你是一个内容优化专家。根据反馈改进回答质量。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.3,
                thinking={"type": "disabled"},
            )
            return self._extract(resp)
        except Exception as exc:
            logger.warning("Quality fix failed: %s", exc)
            return ""

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract(response) -> str:
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        return text.strip()


# Module-level singleton
quality_checker = QualityChecker()
