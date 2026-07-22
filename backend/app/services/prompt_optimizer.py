"""Prompt Auto-Optimizer — learns from task reviews to improve system prompts.

Periodically analyzes accumulated task reviews for quality patterns,
then generates targeted prompt adjustments.  Applies changes to persona
system prompts or global rules.

Closes the loop: 任务执行 → 质量自检 → 用户反馈 → 任务复盘 → Prompt优化
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

OPTIMIZATION_LOG = os.path.join("data", "prompt_optimizations.jsonl")
MIN_REVIEWS_FOR_OPTIMIZATION = 3  # Need at least 3 reviews before suggesting changes


@dataclass
class OptimizationSuggestion:
    """A single suggested prompt improvement."""
    target: str  # "global_rules" | "persona_system_prompt"
    issue_pattern: str  # What pattern was detected
    current_text: str  # Relevant current prompt text
    suggested_change: str  # What to change
    rationale: str  # Why this change


@dataclass
class OptimizationReport:
    """Result of an optimization analysis run."""
    reviews_analyzed: int = 0
    patterns_found: list[str] = field(default_factory=list)
    suggestions: list[OptimizationSuggestion] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)


class PromptOptimizer:
    """Analyzes task reviews and suggests/generates prompt improvements."""

    # ── public API ────────────────────────────────────────────────────

    async def analyze(
        self,
        reviews: list[dict],
        current_global_rules: str = "",
        current_persona_prompt: str = "",
    ) -> OptimizationReport:
        """Analyze reviews and generate optimization suggestions."""
        if len(reviews) < MIN_REVIEWS_FOR_OPTIMIZATION:
            return OptimizationReport(reviews_analyzed=len(reviews))

        report = OptimizationReport(reviews_analyzed=len(reviews))

        # Step 1: Extract quality patterns from reviews
        patterns = await self._extract_patterns(reviews)
        report.patterns_found = patterns

        if not patterns:
            return report

        # Step 2: Generate targeted prompt adjustments
        suggestions = await self._generate_suggestions(
            patterns, current_global_rules, current_persona_prompt
        )
        report.suggestions = suggestions

        return report

    async def apply_global_rules_optimization(
        self, suggestion: OptimizationSuggestion
    ) -> str:
        """Apply an optimization to the global rules. Returns updated rules text."""
        prompt = (
            "你是Prompt优化专家。根据以下分析，优化全局行为准则。\n\n"
            f"## 发现的问题模式\n{suggestion.issue_pattern}\n\n"
            f"## 当前规则\n{suggestion.current_text}\n\n"
            f"## 建议修改\n{suggestion.suggested_change}\n\n"
            f"## 修改理由\n{suggestion.rationale}\n\n"
            "请输出优化后的完整规则（保持其他规则不变，只修改相关部分）：\n"
        )
        try:
            resp = await llm_service.chat(
                interaction_name="prompt_rule_optimization",
                system_prompt="你是Prompt优化专家。输出优化后的完整规则文本。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.2,
                thinking={"type": "disabled"},
            )
            text = self._extract(resp)
            self._log_optimization(suggestion)
            return text
        except Exception as exc:
            logger.warning("Prompt optimization failed: %s", exc)
            return suggestion.current_text

    # ── analysis ─────────────────────────────────────────────────────

    async def _extract_patterns(self, reviews: list[dict]) -> list[str]:
        """Extract recurring quality issue patterns from reviews."""
        issues_text = "\n".join(
            f"- 评分{r.get('quality_score','?')}: {r.get('quality_issues','')} | 改进:{r.get('improvement_points','')}"
            for r in reviews[-20:]  # Analyze last 20 reviews
        )

        prompt = (
            "分析以下任务复盘记录，找出反复出现的质量问题模式。\n"
            "只列出出现2次及以上的模式，每种模式一句话概括。\n\n"
            f"{issues_text[:5000]}\n\n"
            "返回JSON数组：\n"
            '["模式1：回答过于全面但缺乏重点（出现3次）", "模式2：..."]\n'
            "如果没有明显的重复模式，返回[]"
        )
        try:
            resp = await llm_service.chat(
                interaction_name="prompt_pattern_extraction",
                system_prompt="你是质量分析专家。识别重复出现的模式。严格返回JSON数组。",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.1,
                thinking={"type": "disabled"},
            )
            text = self._extract(resp)
            return json.loads(text)
        except Exception as exc:
            logger.warning("Pattern extraction failed: %s", exc)
            return []

    async def _generate_suggestions(
        self,
        patterns: list[str],
        current_rules: str,
        current_prompt: str,
    ) -> list[OptimizationSuggestion]:
        """Generate specific prompt changes for each pattern."""
        suggestions: list[OptimizationSuggestion] = []
        for pattern in patterns[:3]:  # Max 3 suggestions per run
            prompt = (
                "根据以下质量问题模式，针对性地提出Prompt修改建议。\n\n"
                f"## 问题模式\n{pattern}\n\n"
                f"## 当前全局规则\n{current_rules[:1500]}\n\n"
                "请给出具体的修改建议：\n"
                "- target: 修改哪个部分（global_rules 或 persona_prompt）\n"
                "- issue_pattern: 问题模式\n"
                "- current_text: 当前相关文本\n"
                "- suggested_change: 建议如何修改\n"
                "- rationale: 修改理由\n\n"
                "返回JSON：\n"
                '{"target":"global_rules","issue_pattern":"...",'
                '"current_text":"...","suggested_change":"...",'
                '"rationale":"..."}'
            )
            try:
                resp = await llm_service.chat(
                    interaction_name="prompt_suggestion",
                    system_prompt="你是Prompt优化专家。给出具体的修改建议。严格返回JSON。",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=600,
                    temperature=0.2,
                    thinking={"type": "disabled"},
                )
                text = self._extract(resp)
                data = json.loads(text)
                suggestions.append(OptimizationSuggestion(
                    target=data.get("target", "global_rules"),
                    issue_pattern=data.get("issue_pattern", pattern),
                    current_text=data.get("current_text", ""),
                    suggested_change=data.get("suggested_change", ""),
                    rationale=data.get("rationale", ""),
                ))
            except Exception as exc:
                logger.warning("Suggestion generation failed: %s", exc)
        return suggestions

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract(response) -> str:
        text = ""
        if response.content:
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
        return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    def _log_optimization(self, suggestion: OptimizationSuggestion) -> None:
        try:
            os.makedirs(os.path.dirname(OPTIMIZATION_LOG), exist_ok=True)
            with open(OPTIMIZATION_LOG, "a", encoding="utf-8") as f:
                json.dump({
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "target": suggestion.target,
                    "issue_pattern": suggestion.issue_pattern,
                    "rationale": suggestion.rationale,
                }, f, ensure_ascii=False)
                f.write("\n")
        except Exception:
            pass


# Module-level singleton
prompt_optimizer = PromptOptimizer()
