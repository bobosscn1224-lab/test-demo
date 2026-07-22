"""Image Generation Service — pluggable backends (OpenAI, RuiZhi CLI).

Unified interface for PPT maker and other skills.
Auto-selects: OpenAI API (if key configured) > RuiZhi CLI (fallback).

Config (.env):
  OPENAI_API_KEY=sk-...      # for DALL-E / gpt-image-2
  IMAGE_GEN_MODEL=gpt-image-2   # model name (default: dall-e-3)
  IMAGE_GEN_BACKEND=openai   # "openai" | "ruizhi" | "auto" (default: auto)
"""
from __future__ import annotations

import asyncio
import base64
import json
import inspect
import logging
import os
import subprocess
import time
import uuid
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _exception_detail(exc: Exception) -> str:
    message = str(exc).strip()
    return f"{exc.__class__.__name__}: {message or 'no detail'}"


def _discard_or_preserve_attempt(path: str, interaction_name: str) -> None:
    if not os.path.exists(path):
        return
    if interaction_name != "ppt_collage":
        os.unlink(path)
        return
    source = Path(path)
    diagnostic_dir = source.parent / "collage_diagnostics"
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    os.replace(path, str(diagnostic_dir / source.name))

OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"


class ImageGenResult:
    def __init__(self, success: bool, path: str = "", error: str = "", backend: str = ""):
        self.success = success
        self.path = path
        self.error = error
        self.backend = backend


def _is_retryable_call_failure(error: str) -> bool:
    """Avoid repeated paid calls for permanent configuration/account errors."""
    message = str(error or "").lower()
    permanent = (
        "billing hard limit", "billing_hard_limit", "insufficient_quota",
        "invalid token", "invalid api key", "not configured", "未找到 ruizhi",
        "http 400", "http 401", "http 403", "http 404", "http 422",
    )
    return not any(token in message for token in permanent)


_BACKEND_CATALOG = (
    ("apiyi", "apiyi_api_key", "API易", "gpt-image-2", "api.apiyi.com"),
    ("tutujin", "tutujin_api_key", "Tutujin", "gpt-image-2", "api.tutujin.com"),
    ("tutujin_vip", "tutujin_api_key", "Tutujin VIP", "gpt-image-2-vip", "api.tutujin.com"),
    ("api0029", "api0029_key", "0029 API", "gpt-image-2", "api.0029.org"),
    ("shiyun", "shiyun_api_key", "诗云/词元之河", "gpt-image-2", "api.tokenriver.cn"),
    ("lovart", "lovart_api_key", "Lovart", "gpt-image-2:stable", "CatRouter"),
    ("agnes", "agnes_api_key", "Agnes", "agnes-2.0-flash", "Agnes AI Hub"),
    ("openai", "openai_api_key", "OpenAI", "dall-e-3/gpt-image-2", "api.openai.com"),
    ("ruizhi", "ruizhi_api_key", "锐智", "ruizhi-imagegen", "锐智本地/云端"),
)
_BACKEND_UNHEALTHY_UNTIL: dict[str, float] = {}
_BACKEND_LAST_ERROR: dict[str, str] = {}


def _backend_runtime_status(backend: str) -> str:
    if _BACKEND_UNHEALTHY_UNTIL.get(backend, 0) > time.time():
        return "temporarily_unavailable"
    return "configured"


def _record_backend_success(backend: str) -> None:
    _BACKEND_UNHEALTHY_UNTIL.pop(backend, None)
    _BACKEND_LAST_ERROR.pop(backend, None)


def _record_backend_failure(backend: str, error: str, *, permanent: bool) -> None:
    if backend == "none":
        return
    _BACKEND_UNHEALTHY_UNTIL[backend] = time.time() + (900 if permanent else 60)
    _BACKEND_LAST_ERROR[backend] = str(error or "")[:300]


def list_configured_backends() -> list[dict[str, str]]:
    """Return every configured backend from the shared settings source."""
    return [
        {
            "key": key,
            "label": label,
            "model": model,
            "desc": desc,
            "status": _backend_runtime_status(key),
        }
        for key, key_field, label, model, desc in _BACKEND_CATALOG
        if bool(getattr(settings, key_field, ""))
        and (key != "ruizhi" or _find_ruizhi_exe() is not None)
    ]


def has_configured_backend() -> bool:
    return bool(list_configured_backends())


def _shiyun_api_base() -> str:
    """Map the retired Shiyun website host to TokenRiver's official API host."""
    configured = settings.shiyun_base_url.rstrip("/")
    if configured in {"https://shiyunapi.com", "http://shiyunapi.com"}:
        return "https://api.tokenriver.cn"
    return configured


def _backends() -> list[str]:
    """Return ordered list of backends to try.

    If IMAGE_GEN_BACKEND is set explicitly, use only that one.
    Otherwise try in priority order: Agnes > Lovart > OpenAI > Ruizhi.
    """
    explicit = getattr(settings, "image_gen_backend", None) or os.environ.get("IMAGE_GEN_BACKEND", "auto")
    if explicit in ("tutujin", "tutujin_vip", "api0029", "shiyun", "lovart", "openai", "ruizhi", "agnes"):
        return [explicit] if _backend_runtime_status(explicit) != "temporarily_unavailable" else ["none"]
    ready = {
        item["key"] for item in list_configured_backends()
        if item["status"] != "temporarily_unavailable"
    }
    # auto: API易 first > tutujin > others
    order: list[str] = []
    if settings.apiyi_api_key and "apiyi" in ready:
        order.append("apiyi")
    if settings.tutujin_api_key and "tutujin" in ready:
        order.append("tutujin")
    if settings.tutujin_api_key and "tutujin_vip" in ready:
        order.append("tutujin_vip")
    if settings.api0029_key and "api0029" in ready:
        order.append("api0029")
    if settings.shiyun_api_key and "shiyun" in ready:
        order.append("shiyun")
    if settings.lovart_api_key and "lovart" in ready:
        order.append("lovart")
    if settings.agnes_api_key and "agnes" in ready:
        order.append("agnes")
    if settings.openai_api_key and "openai" in ready:
        order.append("openai")
    if settings.ruizhi_api_key and _find_ruizhi_exe() is not None and "ruizhi" in ready:
        order.append("ruizhi")
    return order if order else ["none"]


async def generate_image(
    prompt: str,
    output_path: str,
    *,
    interaction_name: str,
    size: str = "1792x1024",
    quality: str = "standard",
    force_backend: str = "",
    reference_url: str = "",
    validation_context: dict | None = None,
    provider_timeout: float | None = None,
    progress_callback=None,
    credential_slot: str = "",
) -> ImageGenResult:
    """Generate, validate, retry and release one image.

    If force_backend is specified, uses ONLY that backend (ignores IMAGE_GEN_BACKEND setting).
    """
    from app.services.image_quality_gate import (
        build_image_retry_prompt,
        enrich_image_prompt,
        get_image_spec,
        validate_image_file,
        validate_image_prompt,
        validate_image_semantics,
    )
    from app.services.llm_logger import log_model_attempt

    validation_context = validation_context or {}
    prompt_failures = validate_image_prompt(prompt, interaction_name, validation_context)
    if prompt_failures:
        return ImageGenResult(
            success=False,
            error="图片 Prompt 门禁未通过：" + "; ".join(prompt_failures),
            backend="gate",
        )

    original_prompt = enrich_image_prompt(prompt, interaction_name)
    image_spec = get_image_spec(interaction_name)
    max_retries = int(image_spec.get("max_retries", 1))
    if interaction_name == "ppt_collage":
        from app.services.collage_prompt_spec import get_generation_runtime
        runtime = get_generation_runtime()
        max_retries = max(0, int(runtime.get("max_paid_calls_per_variant", 2)) - 1)
        cooldown = float(runtime.get("retry_cooldown_seconds", 8))
        provider_timeout = provider_timeout or float(runtime.get("provider_call_timeout_seconds", 300))
    else:
        cooldown = 1.0
    backends_to_try = [force_backend] if force_backend else _backends()
    errors: list[str] = []

    async def emit(status: str, attempt: int, message: str = "") -> None:
        if progress_callback is None:
            return
        value = progress_callback({"status": status, "attempt": attempt, "message": message})
        if inspect.isawaitable(value):
            await value

    async def invoke_backend(backend: str, current_prompt: str, attempt_path: str) -> ImageGenResult:
        tutujin_credential = ""
        if backend in ("tutujin", "tutujin_vip") and credential_slot:
            from app.services.tutujin_credentials import get_image_credential, safe_credential_error
            try:
                tutujin_credential = get_image_credential(credential_slot)
            except Exception as exc:
                return ImageGenResult(
                    False,
                    error=safe_credential_error(credential_slot, exc),
                    backend=backend,
                )
        if backend == "apiyi":
            operation = _generate_apiyi(current_prompt, attempt_path, size, quality)
        elif backend == "tutujin":
            operation = (
                _generate_tutujin(
                    current_prompt, attempt_path, size, "gpt-image-2", reference_url,
                    api_key=tutujin_credential,
                )
                if tutujin_credential else
                _generate_tutujin(current_prompt, attempt_path, size, "gpt-image-2", reference_url)
            )
        elif backend == "tutujin_vip":
            operation = (
                _generate_tutujin(
                    current_prompt, attempt_path, size, "gpt-image-2-vip", reference_url,
                    api_key=tutujin_credential,
                )
                if tutujin_credential else
                _generate_tutujin(current_prompt, attempt_path, size, "gpt-image-2-vip", reference_url)
            )
        elif backend == "api0029":
            operation = _generate_api0029(current_prompt, attempt_path, size)
        elif backend == "shiyun":
            operation = _generate_shiyun(current_prompt, attempt_path, size)
        elif backend == "agnes":
            operation = _generate_agnes(current_prompt, attempt_path, size)
        elif backend == "lovart":
            operation = _generate_lovart(current_prompt, attempt_path, size)
        elif backend == "openai":
            operation = _generate_openai(current_prompt, attempt_path, size, quality)
        elif backend == "ruizhi":
            operation = _generate_ruizhi(current_prompt, attempt_path)
        else:
            return ImageGenResult(False, error="未配置任何图片生成服务", backend="none")
        try:
            if provider_timeout:
                return await asyncio.wait_for(operation, timeout=provider_timeout)
            return await operation
        except asyncio.TimeoutError:
            return ImageGenResult(
                False, error=f"供应商调用超时（上限{provider_timeout:g}秒）", backend=backend,
            )

    for backend in backends_to_try:
        current_prompt = original_prompt
        for attempt in range(max_retries + 1):
            await emit("generating", attempt + 1, f"正在执行第 {attempt + 1} 次生图调用")
            stem, suffix = os.path.splitext(output_path)
            attempt_path = f"{stem}.gate-{uuid.uuid4().hex[:8]}{suffix or '.png'}"
            result = await invoke_backend(backend, current_prompt, attempt_path)
            if result.success:
                result.backend = backend

            if not result.success:
                errors.append(f"[{backend}] {result.error}")
                log_model_attempt(
                    interaction_name=f"image:{interaction_name}", attempt=attempt + 1,
                    model=backend, status="call_failed", failures=[result.error], checks=[], usage={},
                    system_prompt="collage_prompt_spec.yaml", user_prompt=current_prompt,
                    output="",
                )
                _discard_or_preserve_attempt(attempt_path, interaction_name)
                if attempt < max_retries and _is_retryable_call_failure(result.error):
                    await emit("cooling_down", attempt + 1, f"供应商调用未成功，冷却后重试")
                    await asyncio.sleep(cooldown if interaction_name == "ppt_collage" else min(2 ** attempt, 2))
                    continue
                _record_backend_failure(
                    backend, result.error,
                    permanent=not _is_retryable_call_failure(result.error),
                )
                break

            normalization_failure = ""
            if interaction_name == "ppt_collage":
                geometry = image_spec.get("grid_geometry") or {}
                normalization = geometry.get("normalization") or {}
                if normalization.get("enabled", False):
                    from app.services.collage_postprocess import normalize_collage_grid

                    normalized = normalize_collage_grid(
                        attempt_path,
                        attempt_path,
                        total_pages=int(validation_context.get("expected_pages") or 0),
                        columns=int(validation_context.get("columns") or 3),
                        spec=image_spec,
                    )
                    if not normalized and geometry.get("on_detection_failure") == "reject":
                        normalization_failure = "拼图网格无法可靠归一化，候选图不予放行"

            await emit("reviewing", attempt + 1, "正在执行图片质量门禁")
            failures = validate_image_file(
                attempt_path, interaction_name, size, validation_context,
            )
            if normalization_failure:
                failures.insert(0, normalization_failure)
            review: dict = {}
            if not failures:
                semantic_failures, review = await validate_image_semantics(
                    attempt_path, original_prompt, interaction_name, validation_context,
                )
                failures.extend(semantic_failures)

            log_model_attempt(
                interaction_name=f"image:{interaction_name}", attempt=attempt + 1,
                model=backend, status="passed" if not failures else "quality_failed",
                failures=failures,
                checks=["file_integrity", "dimensions", "aspect_ratio", "grid_normalization", "visual_semantics"] if not failures else [],
                usage={}, system_prompt="collage_prompt_spec.yaml",
                user_prompt=current_prompt,
                output=json.dumps({"path": attempt_path, "review": review}, ensure_ascii=False),
            )
            if not failures:
                if review.get("status") == "unavailable":
                    await emit(
                        "passed_with_manual_review", attempt + 1,
                        "结构检查通过，语义检查暂不可用，需人工确认",
                    )
                os.replace(attempt_path, output_path)
                result.path = output_path
                _record_backend_success(backend)
                return result
            _discard_or_preserve_attempt(attempt_path, interaction_name)
            if attempt < max_retries:
                current_prompt = build_image_retry_prompt(original_prompt, interaction_name, failures)
            else:
                errors.append(f"[{backend}] 图片质量门禁未通过：{'；'.join(failures)}")
                _record_backend_failure(backend, errors[-1], permanent=False)

    return ImageGenResult(
        success=False,
        error="; ".join(errors) if errors else "所有图片生成后端均不可用",
        backend="none",
    )


# ── API易 backend (gpt-image-2 via api.apiyi.com) ─────────────────────────

async def _generate_apiyi(prompt: str, output_path: str, size: str, quality: str = "low") -> ImageGenResult:
    """Generate image via API易 — standard gpt-image-2 images/generations endpoint."""
    key = settings.apiyi_api_key
    if not key:
        return ImageGenResult(success=False, error="APIYI_API_KEY not configured", backend="apiyi")

    # Map quality: standard → low (default from caller), otherwise use explicit setting
    quality = quality if quality != "standard" else getattr(settings, "apiyi_quality", None) or os.environ.get("APIYI_QUALITY", "low")
    # Use "auto" to let the model choose canvas size based on prompt layout spec
    if size not in ("1024x1024", "1536x1024", "1024x1536", "2048x2048", "2048x1152", "3840x2160", "2160x3840", "auto"):
        size = "auto"

    payload = {
        "model": "gpt-image-2",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "output_format": "png",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
        try:
            resp = await client.post(
                "https://api.apiyi.com/v1/images/generations",
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )

            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning("APIyi HTTP %s: %s", resp.status_code, err)
                return ImageGenResult(success=False, error=f"APIyi HTTP {resp.status_code}: {err}", backend="apiyi")

            data = resp.json()
            items = data.get("data") or []
            if not items:
                return ImageGenResult(success=False, error="APIyi: no data in response", backend="apiyi")

            b64 = items[0].get("b64_json", "")
            if not b64:
                return ImageGenResult(success=False, error="APIyi: no b64_json in response", backend="apiyi")

            img_bytes = base64.b64decode(b64)
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info("APIyi generated %s (%d bytes, quality=%s)", output_path, len(img_bytes), quality)
            return ImageGenResult(success=True, path=output_path, backend="apiyi")

        except Exception as exc:
            logger.warning("APIyi failed: %s (%s)", exc, exc.__class__.__name__)
            return ImageGenResult(success=False, error=_exception_detail(exc), backend="apiyi")


# ── OpenAI backend ─────────────────────────────────────────────────────

async def _generate_openai(
    prompt: str, output_path: str, size: str, quality: str
) -> ImageGenResult:
    """Call OpenAI image API (gpt-image-2 / dall-e-3)."""
    key = settings.openai_api_key
    if not key:
        return ImageGenResult(success=False, error="OPENAI_API_KEY not configured", backend="openai")

    model = os.environ.get("IMAGE_GEN_MODEL", "gpt-image-2")
    model = model or "gpt-image-2"

    # Map sizes — supported by both dall-e-3 and gpt-image-2
    if size not in ("1024x1024", "1792x1024", "1024x1792", "1536x1024"):
        size = "1792x1024"

    body: dict = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    # quality param only for dall-e-3
    if "dall-e" in model.lower():
        body["quality"] = quality if quality in ("standard", "hd") else "standard"
    # gpt-image-2 does NOT support response_format param — omit it

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                OPENAI_IMAGE_URL,
                json=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning("OpenAI image API error (%s): %s", model, err)
                return ImageGenResult(success=False, error=f"OpenAI {model}: HTTP {resp.status_code} {err}", backend="openai")

            data = resp.json()

            # Response may contain url or b64_json
            image_data = (data.get("data") or [{}])[0]
            image_url = image_data.get("url", "")
            image_b64 = image_data.get("b64_json", "")

            if image_url:
                # Download image to output_path
                img_resp = await client.get(image_url, timeout=60)
                if img_resp.status_code != 200:
                    return ImageGenResult(success=False, error=f"Failed to download image: HTTP {img_resp.status_code}", backend="openai")
                img_bytes = img_resp.content
            elif image_b64:
                img_bytes = base64.b64decode(image_b64)
            else:
                return ImageGenResult(success=False, error=f"OpenAI {model}: no image data in response", backend="openai")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info("OpenAI %s generated: %s (%d bytes)", model, output_path, len(img_bytes))
            return ImageGenResult(success=True, path=output_path, backend="openai")

        except Exception as exc:
            logger.warning("OpenAI image gen failed: %s", exc)
            return ImageGenResult(success=False, error=_exception_detail(exc), backend="openai")


# ── RuiZhi CLI backend ─────────────────────────────────────────────────

def _find_ruizhi_exe() -> str | None:
    exe = settings.ruizhi_imagegen_exe or os.environ.get("RUIZHI_IMAGEGEN_EXE")
    if exe and os.path.exists(exe):
        return exe
    default = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "Codex", "resources", "bin", "ruizhi-imagegen.exe",
    )
    return default if default and os.path.exists(default) else None


def _ruizhi_env() -> dict:
    env = os.environ.copy()
    if settings.ruizhi_home:
        env["RUIZHI_HOME"] = settings.ruizhi_home
    if settings.codex_home:
        env["CODEX_HOME"] = settings.codex_home
    if settings.ruizhi_api_key:
        env["RUIZHI_API_KEY"] = settings.ruizhi_api_key
    return env


async def _generate_ruizhi(prompt: str, output_path: str) -> ImageGenResult:
    exe = _find_ruizhi_exe()
    if not exe:
        return ImageGenResult(success=False, error="未找到 ruizhi-imagegen.exe", backend="ruizhi")

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            [exe, "generate", "--prompt", prompt, "--out", output_path,
             "--quality", "high", "--size", "auto", "--force"],
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=420,
            env=_ruizhi_env(),
        )
    except subprocess.TimeoutExpired:
        return ImageGenResult(success=False, error="RuiZhi 图片生成超时（超过7分钟）", backend="ruizhi")
    except FileNotFoundError:
        return ImageGenResult(success=False, error="未找到 ruizhi-imagegen.exe", backend="ruizhi")

    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "")[:500]
        if "401" in err or "Invalid token" in err:
            return ImageGenResult(success=False, error="RUIZHI_API_KEY 失效，请更新密钥或切换到 OpenAI", backend="ruizhi")
        return ImageGenResult(success=False, error=err or f"exit code {completed.returncode}", backend="ruizhi")

    if not os.path.exists(output_path):
        return ImageGenResult(success=False, error=f"RuiZhi 报告成功但未生成文件", backend="ruizhi")

    return ImageGenResult(success=True, path=output_path, backend="ruizhi")


# ── Lovart / CatRouter backend (gpt-image-2 via OpenAI-compatible API) ──

async def _generate_lovart(prompt: str, output_path: str, size: str) -> ImageGenResult:
    """Generate image via CatRouter (gpt-image-2:stable). OpenAI-compatible."""
    key = settings.lovart_api_key
    if not key:
        return ImageGenResult(success=False, error="LOVART_API_KEY not configured", backend="lovart")

    if size not in ("1024x1024", "1792x1024", "1024x1792", "1536x1024"):
        size = "1792x1024"

    body = {
        "model": "gpt-image-2:stable",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "format": "png",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{settings.lovart_base_url.rstrip('/')}/images/generations",
                json=body,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning("CatRouter API error: %s", err)
                return ImageGenResult(success=False, error=f"CatRouter: HTTP {resp.status_code} {err}", backend="lovart")

            data = resp.json()
            image_data = (data.get("data") or [{}])[0]
            image_url = image_data.get("url", "")
            image_b64 = image_data.get("b64_json", "")

            if image_url:
                img_resp = await client.get(image_url, timeout=60)
                if img_resp.status_code != 200:
                    return ImageGenResult(success=False, error=f"Failed to download image: HTTP {img_resp.status_code}", backend="lovart")
                img_bytes = img_resp.content
            elif image_b64:
                img_bytes = base64.b64decode(image_b64)
            else:
                return ImageGenResult(success=False, error="CatRouter: no image data in response", backend="lovart")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info("CatRouter gpt-image-2:stable generated: %s (%d bytes)", output_path, len(img_bytes))
            return ImageGenResult(success=True, path=output_path, backend="lovart")

        except Exception as exc:
            logger.warning("CatRouter image gen failed: %s", exc)
            return ImageGenResult(success=False, error=_exception_detail(exc), backend="lovart")


# ── Tutujin backend (gpt-image-2 via api.tutujin.com) ──────────────────────

async def _generate_tutujin(prompt: str, output_path: str, size: str, model: str = "gpt-image-2",
                             reference_url: str = "", *, api_key: str = "") -> ImageGenResult:
    """Generate image via api.tutujin.com — uses chat/completions API with optional image reference."""
    import ssl as _ssl, certifi as _certifi, re as _re

    key = api_key or settings.tutujin_api_key
    if not key:
        return ImageGenResult(success=False, error="TUTUJIN_API_KEY not configured", backend="tutujin")

    # Build message content — multimodal if reference image provided
    if reference_url:
        msg_content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": reference_url}},
        ]
    else:
        msg_content = prompt

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": msg_content}],
    }

    _ctx = _ssl.create_default_context(cafile=_certifi.where())

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0), verify=_ctx, follow_redirects=True) as client:
        try:
            resp = await client.post(
                f"{settings.tutujin_base_url}/v1/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )

            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning("Tutujin HTTP %s: %s", resp.status_code, err)
                return ImageGenResult(success=False, error=f"Tutujin HTTP {resp.status_code}: {err}", backend="tutujin")

            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Debug: log full response when content is empty
            if not content or not content.strip():
                choice0 = data.get("choices", [{}])[0]
                msg0 = choice0.get("message", {})
                logger.warning(
                    "Tutujin empty content. Status=%d, finish_reason=%s, model=%s",
                    resp.status_code, choice0.get("finish_reason", "?"), data.get("model", "?"),
                )
                logger.warning("  Message keys: %s", list(msg0.keys()))
                logger.warning("  Choice keys: %s", list(choice0.keys()))
                # Log any non-content fields in message
                for k, v in msg0.items():
                    if k != "content":
                        val_str = str(v)[:300]
                        logger.warning("  msg.%s = %s", k, val_str)

            img_bytes = None

            # Try markdown image URL: ![img](url)
            md_img = _re.search(r'!\[.*?\]\(([^)]+)\)', content)
            if md_img:
                img_url = md_img.group(1)
                if img_url.startswith("data:image"):
                    b64_part = _re.search(r'base64,([A-Za-z0-9+/=]+)', img_url)
                    if b64_part:
                        img_bytes = base64.b64decode(b64_part.group(1))
                elif img_url.startswith("http"):
                    r = await client.get(img_url)
                    if r.status_code == 200:
                        img_bytes = r.content

            # Try base64 image in markdown: ![img](data:image/png;base64,xxx)
            if not img_bytes:
                b64_match = _re.search(r'data:image/\w+;base64,([A-Za-z0-9+/=]+)', content)
                if b64_match:
                    img_bytes = base64.b64decode(b64_match.group(1))

            # Try plain base64 in content
            if not img_bytes and len(content) > 100 and not content.startswith("http"):
                try:
                    img_bytes = base64.b64decode(content.strip())
                except Exception:
                    pass

            # Try images field in response
            if not img_bytes:
                images = data.get("images") or data.get("data") or []
                if images:
                    item = images[0]
                    if item.get("url"):
                        r = await client.get(item["url"])
                        if r.status_code == 200:
                            img_bytes = r.content
                    for b64k in ("b64_json", "base64"):
                        if item.get(b64k):
                            img_bytes = base64.b64decode(item[b64k])
                            break

            if not img_bytes:
                return ImageGenResult(success=False, error=f"Tutujin: no image in response. Content preview: {content[:200]}", backend="tutujin")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info("Tutujin generated %s (%d bytes)", output_path, len(img_bytes))
            return ImageGenResult(success=True, path=output_path, backend="tutujin")

        except Exception as exc:
            logger.warning("Tutujin failed: %s (%s)", exc, exc.__class__.__name__)
            return ImageGenResult(success=False, error=_exception_detail(exc), backend="tutujin")


# ── 0029 API backend (gpt-image-2 via api.0029.org) ────────────────────────

async def _generate_api0029(prompt: str, output_path: str, size: str) -> ImageGenResult:
    """Generate image via api.0029.org — httpx + certifi (avoids Windows CRL issues)."""
    import ssl as _ssl, certifi as _certifi

    key = settings.api0029_key
    if not key:
        return ImageGenResult(success=False, error="API0029_KEY not configured", backend="api0029")

    if size not in ("1024x1024", "1792x1024", "1024x1792", "1536x1024", "auto"):
        size = "1792x1024"

    payload = {
        "model": "gpt-image-2",
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": "auto",
        "output_format": "png",
        "response_format": "b64_json",
    }

    _ctx = _ssl.create_default_context(cafile=_certifi.where())

    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0), verify=_ctx, follow_redirects=True) as client:
        try:
            resp = await client.post(
                f"{settings.api0029_base_url}/v1/images/generations",
                json=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )

            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning("0029 API HTTP %s: %s", resp.status_code, err)
                return ImageGenResult(success=False, error=f"0029 HTTP {resp.status_code}: {err}", backend="api0029")

            data = resp.json()
            items = data.get("data") or []
            if not items:
                return ImageGenResult(success=False, error="0029: no data in response", backend="api0029")

            item = items[0]
            img_bytes = None

            if item.get("url"):
                r = await client.get(item["url"])
                if r.status_code == 200:
                    img_bytes = r.content

            if not img_bytes:
                for b64k in ("b64_json", "base64", "image_base64"):
                    if item.get(b64k):
                        img_bytes = base64.b64decode(item[b64k])
                        break

            if not img_bytes:
                return ImageGenResult(success=False, error="0029: no image url/b64 in response", backend="api0029")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info("0029 generated %s (%d bytes)", output_path, len(img_bytes))
            return ImageGenResult(success=True, path=output_path, backend="api0029")

        except Exception as exc:
            logger.warning("0029 failed: %s (%s)", exc, exc.__class__.__name__)
            return ImageGenResult(success=False, error=_exception_detail(exc), backend="api0029")


# ── ShiyunApi backend (gpt-image-2 via shiyunapi.com) ─────────────────────

async def _generate_shiyun(prompt: str, output_path: str, size: str) -> ImageGenResult:
    """Generate image via ShiyunApi (gpt-image-2). Uses urllib for reliable redirect handling."""
    import urllib.request
    import urllib.error

    key = settings.shiyun_api_key
    if not key:
        return ImageGenResult(success=False, error="SHIYUN_API_KEY not configured", backend="shiyun")

    # Normalize size to ShiyunApi supported values
    valid_sizes = {"1024x1024", "1536x1024", "1024x1536", "2048x2048",
                   "2048x1152", "3840x2160", "2160x3840", "auto"}
    if size not in valid_sizes:
        size = "1536x1024"

    def _do_request(field_name: str) -> tuple[int, str, bytes]:
        payload = {
            field_name: "gpt-image-2",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": "auto",
            "format": "png",
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{_shiyun_api_base()}/v1/images/generations",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.status, resp.headers.get("Content-Type", ""), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type", ""), exc.read()

    try:
        status, content_type, raw = await asyncio.to_thread(_do_request, "model")

        # Retry with "modal" field on validation error
        if status in (400, 422):
            text = raw.decode("utf-8", errors="replace").lower()
            if any(h in text for h in ("model", "modal", "missing", "required", "invalid")):
                status, content_type, raw = await asyncio.to_thread(_do_request, "modal")

        if status != 200:
            err = raw.decode("utf-8", errors="replace")[:500]
            logger.warning("ShiyunApi error (%s): %s", status, err)
            return ImageGenResult(success=False, error=f"ShiyunApi: HTTP {status} {err}", backend="shiyun")

        # Some Shiyun routes return the image body directly with HTTP 200.
        is_image_body = (
            content_type.lower().startswith("image/")
            or raw.startswith(b"\x89PNG\r\n\x1a\n")
            or raw.startswith(b"\xff\xd8\xff")
            or raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
        )
        img_bytes = raw if is_image_body else None
        data: dict = {}
        if not img_bytes:
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                return ImageGenResult(
                    success=False,
                    error=f"ShiyunApi: HTTP 200 empty response (content-type={content_type or 'unknown'})",
                    backend="shiyun",
                )
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                preview = text[:160].replace("\n", " ")
                return ImageGenResult(
                    success=False,
                    error=(f"ShiyunApi: HTTP 200 non-JSON response "
                           f"(content-type={content_type or 'unknown'}, bytes={len(raw)}): {preview}"),
                    backend="shiyun",
                )

        # Parse response — try standard OpenAI format first
        data_items = data.get("data") or []
        if data_items:
            item = data_items[0]
            if item.get("url"):
                async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                    img_resp = await client.get(item["url"])
                    if img_resp.status_code == 200:
                        img_bytes = img_resp.content
            if not img_bytes:
                b64 = item.get("b64_json") or item.get("base64") or item.get("image_base64")
                if b64:
                    img_bytes = base64.b64decode(b64)

        # Fallback: try other response structures
        if not img_bytes:
            for key_name in ("images", "result", "results", "output"):
                nested = data.get(key_name)
                if isinstance(nested, list) and nested:
                    ni = nested[0]
                    if isinstance(ni, dict):
                        if ni.get("url"):
                            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                                img_resp = await client.get(ni["url"])
                                if img_resp.status_code == 200:
                                    img_bytes = img_resp.content
                                    break
                        b64 = ni.get("b64_json") or ni.get("base64")
                        if b64:
                            img_bytes = base64.b64decode(b64)
                            break

        if not img_bytes:
            return ImageGenResult(success=False, error="ShiyunApi: no image data in response", backend="shiyun")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        logger.info("ShiyunApi gpt-image-2 generated: %s (%d bytes)", output_path, len(img_bytes))
        return ImageGenResult(success=True, path=output_path, backend="shiyun")

    except Exception as exc:
        logger.warning("ShiyunApi image gen failed: %s", exc)
        return ImageGenResult(success=False, error=_exception_detail(exc), backend="shiyun")


# ── Agnes backend ────────────────────────────────────────────────────────

async def _generate_agnes(prompt: str, output_path: str, size: str) -> ImageGenResult:
    """Generate image using Agnes Image API (agnes-image-2.1-flash)."""
    key = settings.agnes_api_key
    if not key:
        return ImageGenResult(success=False, error="AGNES_API_KEY not configured", backend="agnes")

    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "n": 1,
        "size": size if size in ("1024x1024", "1792x1024", "1024x1792") else "1024x1024",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{settings.agnes_base_url.rstrip('/')}/images/generations",
                json=payload,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                err = resp.text[:500]
                logger.warning("Agnes image API error: %s", err)
                return ImageGenResult(success=False, error=f"Agnes: HTTP {resp.status_code} {err}", backend="agnes")

            data = resp.json()
            image_data = (data.get("data") or [{}])[0]
            image_url = image_data.get("url", "")
            image_b64 = image_data.get("b64_json", "")

            if image_url:
                # Download image
                img_resp = await client.get(image_url, timeout=60)
                if img_resp.status_code != 200:
                    return ImageGenResult(success=False, error=f"Failed to download image: HTTP {img_resp.status_code}", backend="agnes")
                img_bytes = img_resp.content
            elif image_b64:
                img_bytes = base64.b64decode(image_b64)
            else:
                return ImageGenResult(success=False, error="Agnes: no image data in response", backend="agnes")

            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            logger.info("Agnes generated: %s (%d bytes)", output_path, len(img_bytes))
            return ImageGenResult(success=True, path=output_path, backend="agnes")

        except Exception as exc:
            logger.warning("Agnes image gen failed: %s", exc)
            return ImageGenResult(success=False, error=_exception_detail(exc), backend="agnes")
