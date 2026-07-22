"""Mandatory paid text-model quality gate.

The public model service delegates every call here.  Business code declares an
``interaction_name``; this module loads the persistent specification, enriches
the prompt, validates input and output, retries with concrete feedback, writes
an audit record, and releases only a passing response.
"""
from __future__ import annotations

import copy
import inspect
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

logger = logging.getLogger(__name__)
_SPEC_PATH = Path(__file__).parent / "llm_interaction_spec.yaml"


def _load_specs() -> dict:
    with _SPEC_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise RuntimeError("llm_interaction_spec.yaml must contain a mapping")
    return data


INTERACTION_SPECS = _load_specs()


@dataclass
class QualityResult:
    passed: bool
    check_name: str = ""
    fail_feedback: str = ""
    details: str = ""


@dataclass
class GuardedResponse:
    response: Any
    content: str
    retries_used: int = 0
    checks_passed: list[str] = field(default_factory=list)


@dataclass
class InteractionResult:
    success: bool
    content: str = ""
    error: str = ""
    retries_used: int = 0
    quality_failures: list[str] = field(default_factory=list)
    checks_passed: list[str] = field(default_factory=list)


class ModelQualityGateError(RuntimeError):
    """Raised when a paid model response cannot pass its persisted contract."""

    def __init__(self, interaction_name: str, failures: list[str], attempts: int):
        self.interaction_name = interaction_name
        self.failures = failures
        self.attempts = attempts
        summary = "; ".join(failures[-3:]) or "unknown quality failure"
        super().__init__(
            f"Quality gate rejected '{interaction_name}' after {attempts} attempt(s): {summary}"
        )


def _merge_spec_layer(target: dict, layer: dict) -> None:
    for key, value in layer.items():
        if key in {"profile", "description"}:
            target[key] = value
        elif key in {"prompt_requirements", "quality_checks"}:
            target.setdefault(key, [])
            target[key].extend(copy.deepcopy(value or []))
        else:
            target[key] = copy.deepcopy(value)


def get_spec(interaction_name: str) -> dict:
    """Resolve defaults + profile + named interaction into one immutable copy."""
    raw = INTERACTION_SPECS.get(interaction_name)
    if not raw or interaction_name.startswith("_"):
        available = sorted(k for k in INTERACTION_SPECS if not k.startswith("_") and k != "version")
        raise ValueError(
            f"Unknown LLM interaction '{interaction_name}'. Available: {available}"
        )
    result: dict = {}
    _merge_spec_layer(result, INTERACTION_SPECS.get("_defaults", {}))
    profile = raw.get("profile")
    if profile:
        profile_spec = (INTERACTION_SPECS.get("_profiles") or {}).get(profile)
        if not profile_spec:
            raise ValueError(f"Unknown profile '{profile}' for interaction '{interaction_name}'")
        _merge_spec_layer(result, profile_spec)
    _merge_spec_layer(result, raw)
    return result


def validate_specs() -> list[str]:
    """Validate every persisted interaction without invoking a model."""
    errors: list[str] = []
    for name, raw in INTERACTION_SPECS.items():
        if name.startswith("_") or name == "version":
            continue
        try:
            spec = get_spec(name)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if not spec.get("description"):
            errors.append(f"{name}: description missing")
        if not spec.get("quality_checks"):
            errors.append(f"{name}: quality_checks missing")
        if int(spec.get("max_retries", -1)) < 0 or int(spec.get("max_retries", 0)) > 3:
            errors.append(f"{name}: max_retries must be between 0 and 3")
        for check in spec.get("quality_checks", []):
            if not isinstance(check, dict) or not check.get("name") or not check.get("type"):
                errors.append(f"{name}: invalid quality check {check!r}")
            if "check" in check:
                errors.append(f"{name}: executable check expressions are forbidden")
    return errors


_SPEC_ERRORS = validate_specs()
if _SPEC_ERRORS:
    raise RuntimeError("Invalid LLM interaction specs: " + " | ".join(_SPEC_ERRORS))


def extract_response_text(response: Any) -> str:
    if isinstance(response, str):
        return response.strip()
    pieces: list[str] = []
    for block in getattr(response, "content", None) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            pieces.append(str(block.get("text", "")))
        elif hasattr(block, "text"):
            pieces.append(str(block.text))
    return "".join(pieces).strip()


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return str(content or "")


def validate_input(system_prompt: str, messages: list[dict], spec: dict) -> list[str]:
    failures: list[str] = []
    if not str(system_prompt or "").strip():
        failures.append("system_prompt 为空")
    if not messages:
        failures.append("messages 为空")
        return failures
    user_text = "\n".join(
        _message_text(m.get("content")) for m in messages if m.get("role") == "user"
    ).strip()
    if len(user_text) < int(spec.get("min_input_chars", 1)):
        failures.append(
            f"用户输入不足 {spec.get('min_input_chars')} 字，实际 {len(user_text)} 字"
        )
    if len(user_text) > int(spec.get("max_input_chars", 30000)):
        failures.append(
            f"用户输入超过 {spec.get('max_input_chars')} 字，实际 {len(user_text)} 字"
        )
    return failures


def build_guarded_system_prompt(system_prompt: str, spec: dict) -> str:
    requirements = [str(x).strip() for x in spec.get("prompt_requirements", []) if str(x).strip()]
    if not requirements:
        return system_prompt
    rendered = "\n".join(f"{idx}. {rule}" for idx, rule in enumerate(requirements, 1))
    return f"{system_prompt.rstrip()}\n\n━━━ 持久化质量要求（必须遵守）━━━\n{rendered}"


def _extract_json(output: str) -> Any:
    text = output.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
        if not starts:
            raise
        start = min(starts)
        end_obj, end_arr = text.rfind("}"), text.rfind("]")
        end = max(end_obj, end_arr)
        if end <= start:
            raise
        return json.loads(text[start:end + 1])


def _json_path(data: Any, path: str) -> Any:
    current = data
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(path)
    return current


def _regex_flags(value: str) -> int:
    flags = 0
    for name in str(value or "").split("|"):
        name = name.strip().upper()
        if name == "IGNORECASE":
            flags |= re.IGNORECASE
        elif name == "MULTILINE":
            flags |= re.MULTILINE
        elif name == "DOTALL":
            flags |= re.DOTALL
    return flags


def _check_output(output: str, check: dict) -> tuple[bool, str]:
    kind = check["type"]
    if kind == "min_length":
        return len(output) >= int(check["value"]), f"length={len(output)}"
    if kind == "min_non_whitespace":
        count = len(re.sub(r"\s+", "", output))
        return count >= int(check["value"]), f"non_whitespace={count}"
    if kind == "max_length":
        return len(output) <= int(check["value"]), f"length={len(output)}"
    if kind == "contains_all":
        missing = [str(x) for x in check.get("values", []) if str(x) not in output]
        return not missing, f"missing={missing}"
    if kind == "contains_any":
        values = [str(x) for x in check.get("values", [])]
        return any(x in output for x in values), f"expected_any={values}"
    if kind in {"regex", "not_regex", "regex_count"}:
        pattern = str(check.get("pattern", ""))
        flags = _regex_flags(check.get("flags", ""))
        matches = re.findall(pattern, output, flags)
        if kind == "regex":
            return bool(matches), f"pattern={pattern}"
        if kind == "not_regex":
            return not bool(matches), f"matches={len(matches)}"
        count = len(matches)
        minimum = int(check.get("min", 0))
        maximum = int(check.get("max", 10**9))
        return minimum <= count <= maximum, f"count={count}, expected={minimum}..{maximum}"
    if kind == "svg_valid":
        try:
            root = ET.fromstring(output.strip())
            local = root.tag.split("}")[-1]
            view_box = root.attrib.get("viewBox", "")
            passed = local == "svg" and view_box.replace(",", " ").split() == ["0", "0", "1920", "1080"]
            return passed, f"tag={local}, viewBox={view_box}"
        except ET.ParseError as exc:
            return False, str(exc)

    data = _extract_json(output)
    if kind == "json_valid":
        return True, "valid JSON"
    if kind == "json_no_wrapper":
        # Tolerate code fences — _extract_json strips them before parsing.
        # deepseek-v4 reliably wraps JSON in ```fences even after retry prompts
        # ask it to stop. The fence-tolerant parse is the same one json_valid uses.
        _extract_json(output)
        return True, "valid JSON (tolerant of code fences)"
    if kind == "json_type":
        expected = check.get("value")
        passed = (expected == "object" and isinstance(data, dict)) or (
            expected == "array" and isinstance(data, list)
        )
        return passed, f"actual={type(data).__name__}"
    if kind == "json_required_keys":
        missing = [k for k in check.get("keys", []) if not isinstance(data, dict) or k not in data]
        return not missing, f"missing={missing}"
    if kind == "json_conditional_required":
        if not isinstance(data, dict) or data.get(check.get("if_key")) != check.get("if_value"):
            return True, "condition not active"
        alternatives = check.get("keys_any", [])
        passed = any(all(k in data and data.get(k) not in (None, "") for k in keys) for keys in alternatives)
        return passed, f"required_alternatives={alternatives}"
    if kind == "json_path_enum":
        value = _json_path(data, check["path"])
        return value in check.get("values", []), f"actual={value!r}"
    if kind == "json_path_number_range":
        value = _json_path(data, check["path"])
        passed = isinstance(value, (int, float)) and not isinstance(value, bool)
        passed = passed and math.isfinite(float(value))
        passed = passed and float(check.get("min", -math.inf)) <= float(value) <= float(check.get("max", math.inf))
        return passed, f"actual={value!r}"
    if kind == "json_array_length":
        count = len(data) if isinstance(data, list) else -1
        return int(check.get("min", 0)) <= count <= int(check.get("max", 10**9)), f"length={count}"
    if kind == "json_array_items_type":
        expected = check.get("value")
        types = {"string": str, "object": dict, "array": list, "number": (int, float)}
        py_type = types.get(expected)
        passed = isinstance(data, list) and py_type is not None and all(isinstance(x, py_type) for x in data)
        return passed, f"expected_items={expected}"
    if kind == "json_array_item_keys":
        if not isinstance(data, list):
            return False, "not an array"
        if not data and check.get("allow_empty", False):
            return True, "empty allowed"
        keys = check.get("keys", [])
        bad = [idx for idx, item in enumerate(data) if not isinstance(item, dict) or any(k not in item for k in keys)]
        return not bad, f"invalid_items={bad[:10]}"
    if kind == "json_path_array_min":
        value = _json_path(data, check["path"])
        count = len(value) if isinstance(value, list) else -1
        return count >= int(check.get("min", 0)), f"length={count}"
    raise ValueError(f"Unsupported quality check type: {kind}")


def validate_output(output: str, spec: dict) -> list[QualityResult]:
    results: list[QualityResult] = []
    for check in spec.get("quality_checks", []):
        try:
            passed, details = _check_output(output, check)
        except Exception as exc:
            passed, details = False, f"validator error: {exc}"
        results.append(QualityResult(
            passed=bool(passed),
            check_name=str(check.get("name", check.get("type", "unknown"))),
            fail_feedback=str(check.get("fail_feedback", "请修复输出格式或内容。")),
            details=details,
        ))
    return results


def build_retry_prompt(spec: dict, failures: list[QualityResult], original_prompt: str) -> str:
    items = "\n".join(
        f"- [{item.check_name}] {item.fail_feedback}（{item.details}）" for item in failures
    )
    template = spec.get("retry_prompt_template")
    if template:
        return str(template).format(failures=items, original_prompt=original_prompt[:5000])
    return (
        "上一次输出未通过质量门禁。请根据以下可执行反馈重新生成完整结果：\n\n"
        f"{items}\n\n"
        "必须重新输出完整结果，不要解释修复过程，也不要省略原任务要求。"
    )


def _last_user_prompt(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return _message_text(message.get("content"))
    return ""


def _usage_dict(response: Any) -> dict:
    usage = getattr(response, "usage", None)
    if not usage:
        return {}
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def _audit(**record: Any) -> None:
    try:
        from app.services.llm_logger import log_model_attempt
        log_model_attempt(**record)
    except Exception:
        logger.warning("Failed to write model audit record", exc_info=True)


async def execute_guarded_response(
    *,
    interaction_name: str,
    system_prompt: str,
    messages: list[dict],
    raw_call: Callable[..., Any],
    extra_context: dict | None = None,
    model: str | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
    thinking: dict | None = None,
) -> GuardedResponse:
    spec = get_spec(interaction_name)
    input_failures = validate_input(system_prompt, messages, spec)
    if input_failures:
        _audit(interaction_name=interaction_name, attempt=0, model=model or spec.get("model", ""),
               status="input_rejected", failures=input_failures, checks=[], usage={},
               system_prompt=system_prompt, user_prompt=_last_user_prompt(messages), output="")
        raise ModelQualityGateError(interaction_name, input_failures, 0)

    guarded_system = build_guarded_system_prompt(system_prompt, spec)
    original_messages = copy.deepcopy(messages)
    current_messages = copy.deepcopy(messages)
    original_prompt = _last_user_prompt(messages)
    failures_seen: list[str] = []
    max_retries = int(spec.get("max_retries", 1))
    resolved = {
        "model": spec.get("model") or model,
        "max_tokens": int(spec.get("max_tokens", max_tokens or 4096)),
        "temperature": float(spec.get("temperature", temperature if temperature is not None else 0.2)),
        "timeout": float(spec.get("timeout", timeout or 180)),
        "thinking": spec.get("thinking", thinking),
    }

    for attempt in range(max_retries + 1):
        try:
            response = raw_call(system_prompt=guarded_system, messages=current_messages, **resolved)
            if inspect.isawaitable(response):
                response = await response
            output = extract_response_text(response)
            results = validate_output(output, spec)
            failed = [item for item in results if not item.passed]
            passed = [item.check_name for item in results if item.passed]
            _audit(
                interaction_name=interaction_name, attempt=attempt + 1,
                model=resolved["model"] or "", status="passed" if not failed else "quality_failed",
                failures=[f"{x.check_name}: {x.fail_feedback}" for x in failed],
                checks=passed, usage=_usage_dict(response), system_prompt=guarded_system,
                user_prompt=_last_user_prompt(current_messages), output=output,
            )
            if not failed:
                return GuardedResponse(response=response, content=output, retries_used=attempt, checks_passed=passed)
            failures_seen.extend(f"{x.check_name}: {x.fail_feedback}" for x in failed)
            if attempt < max_retries:
                feedback = build_retry_prompt(spec, failed, original_prompt)
                current_messages = copy.deepcopy(original_messages)
                if output:
                    current_messages.append({"role": "assistant", "content": output[:6000]})
                current_messages.append({"role": "user", "content": feedback})
        except ModelQualityGateError:
            raise
        except Exception as exc:
            failure = f"模型调用异常：{exc.__class__.__name__}: {exc}"
            failures_seen.append(failure)
            _audit(interaction_name=interaction_name, attempt=attempt + 1,
                   model=resolved["model"] or "", status="call_failed", failures=[failure],
                   checks=[], usage={}, system_prompt=guarded_system,
                   user_prompt=_last_user_prompt(current_messages), output="")
            if attempt >= max_retries:
                break

    raise ModelQualityGateError(interaction_name, failures_seen, max_retries + 1)


def execute_guarded_response_sync(**kwargs: Any) -> GuardedResponse:
    """Synchronous equivalent for document ingestion worker threads."""
    interaction_name = kwargs["interaction_name"]
    system_prompt = kwargs["system_prompt"]
    messages = kwargs["messages"]
    raw_call = kwargs["raw_call"]
    spec = get_spec(interaction_name)
    input_failures = validate_input(system_prompt, messages, spec)
    if input_failures:
        raise ModelQualityGateError(interaction_name, input_failures, 0)
    guarded_system = build_guarded_system_prompt(system_prompt, spec)
    original_messages = copy.deepcopy(messages)
    current_messages = copy.deepcopy(messages)
    original_prompt = _last_user_prompt(messages)
    failures_seen: list[str] = []
    max_retries = int(spec.get("max_retries", 1))
    resolved = {
        "model": spec.get("model") or kwargs.get("model"),
        "max_tokens": int(spec.get("max_tokens", kwargs.get("max_tokens") or 4096)),
        "temperature": float(spec.get("temperature", kwargs.get("temperature", 0.2))),
        "timeout": float(spec.get("timeout", kwargs.get("timeout", 180))),
        "thinking": spec.get("thinking", kwargs.get("thinking")),
    }
    for attempt in range(max_retries + 1):
        try:
            response = raw_call(system_prompt=guarded_system, messages=current_messages, **resolved)
            output = extract_response_text(response)
            results = validate_output(output, spec)
            failed = [x for x in results if not x.passed]
            passed = [x.check_name for x in results if x.passed]
            _audit(interaction_name=interaction_name, attempt=attempt + 1,
                   model=resolved["model"] or "", status="passed" if not failed else "quality_failed",
                   failures=[f"{x.check_name}: {x.fail_feedback}" for x in failed], checks=passed,
                   usage=_usage_dict(response), system_prompt=guarded_system,
                   user_prompt=_last_user_prompt(current_messages), output=output)
            if not failed:
                return GuardedResponse(response=response, content=output, retries_used=attempt, checks_passed=passed)
            failures_seen.extend(f"{x.check_name}: {x.fail_feedback}" for x in failed)
            if attempt < max_retries:
                current_messages = copy.deepcopy(original_messages)
                if output:
                    current_messages.append({"role": "assistant", "content": output[:6000]})
                current_messages.append({"role": "user", "content": build_retry_prompt(spec, failed, original_prompt)})
        except Exception as exc:
            failures_seen.append(f"模型调用异常：{exc.__class__.__name__}: {exc}")
            if attempt >= max_retries:
                break
    raise ModelQualityGateError(interaction_name, failures_seen, max_retries + 1)


async def execute_with_quality_gate(
    *, interaction_name: str, system_prompt: str,
    user_prompt: str | None = None, messages: list[dict] | None = None,
    llm_service=None, raw_call: Callable[..., Any] | None = None,
    extra_context: dict | None = None, thinking: dict | None = None,
    model: str | None = None, max_tokens: int | None = None,
    temperature: float | None = None, timeout: float | None = None,
    return_guarded_response: bool = False,
) -> InteractionResult | GuardedResponse:
    """The one public entry point for every paid text-model interaction."""
    call = raw_call or getattr(llm_service, "_chat_raw", None)
    if call is None:
        raise ValueError("execute_with_quality_gate requires llm_service or raw_call")
    actual_messages = messages or [{"role": "user", "content": user_prompt or ""}]
    try:
        guarded = await execute_guarded_response(
            interaction_name=interaction_name,
            system_prompt=system_prompt,
            messages=actual_messages,
            raw_call=call,
            extra_context=extra_context,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            thinking=thinking,
        )
        if return_guarded_response:
            return guarded
        return InteractionResult(success=True, content=guarded.content,
                                 retries_used=guarded.retries_used,
                                 checks_passed=guarded.checks_passed)
    except ModelQualityGateError as exc:
        if return_guarded_response:
            raise
        return InteractionResult(success=False, error=str(exc),
                                 retries_used=max(0, exc.attempts - 1),
                                 quality_failures=exc.failures)


def validate_output_sync(output: str, interaction_name: str) -> list[QualityResult]:
    return validate_output(output, get_spec(interaction_name))
