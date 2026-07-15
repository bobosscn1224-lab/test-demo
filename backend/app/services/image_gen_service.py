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
import logging
import os
import subprocess
import uuid
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"
AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
SHIYUN_BASE_URL = os.getenv("SHIYUN_BASE_URL", "https://shiyunapi.com")
LOVART_BASE_URL = os.getenv("LOVART_BASE_URL", "https://api.catrouter.net/v1")


class ImageGenResult:
    def __init__(self, success: bool, path: str = "", error: str = "", backend: str = ""):
        self.success = success
        self.path = path
        self.error = error
        self.backend = backend


def _backends() -> list[str]:
    """Return ordered list of backends to try.

    If IMAGE_GEN_BACKEND is set explicitly, use only that one.
    Otherwise try in priority order: Agnes > Lovart > OpenAI > Ruizhi.
    """
    explicit = getattr(settings, "image_gen_backend", None) or os.environ.get("IMAGE_GEN_BACKEND", "auto")
    if explicit in ("tutujin", "tutujin_vip", "api0029", "shiyun", "lovart", "openai", "ruizhi", "agnes"):
        return [explicit]
    # auto: Shiyun (gpt-image-2) first > Lovart > Agnes > OpenAI > Ruizhi
    order: list[str] = []
    if settings.tutujin_api_key:
        order.append("tutujin")
        order.append("tutujin_vip")
    if settings.api0029_key:
        order.append("api0029")
    if settings.shiyun_api_key:
        order.append("shiyun")
    if settings.lovart_api_key:
        order.append("lovart")
    if settings.agnes_api_key:
        order.append("agnes")
    if settings.openai_api_key:
        order.append("openai")
    if settings.ruizhi_api_key:
        order.append("ruizhi")
    return order if order else ["none"]


async def generate_image(
    prompt: str,
    output_path: str,
    size: str = "1792x1024",
    quality: str = "standard",
    force_backend: str = "",
    reference_url: str = "",
) -> ImageGenResult:
    """Generate an image from a text prompt. Tries backends in order, falls through on failure.

    If force_backend is specified, uses ONLY that backend (ignores IMAGE_GEN_BACKEND setting).
    """
    backends_to_try = [force_backend] if force_backend else _backends()
    errors: list[str] = []
    for backend in backends_to_try:
        result: ImageGenResult
        if backend == "tutujin":
            result = await _generate_tutujin(prompt, output_path, size, "gpt-image-2", reference_url)
        elif backend == "tutujin_vip":
            result = await _generate_tutujin(prompt, output_path, size, "gpt-image-2-vip", reference_url)
        elif backend == "api0029":
            result = await _generate_api0029(prompt, output_path, size)
        elif backend == "shiyun":
            result = await _generate_shiyun(prompt, output_path, size)
        elif backend == "agnes":
            result = await _generate_agnes(prompt, output_path, size)
        elif backend == "lovart":
            result = await _generate_lovart(prompt, output_path, size)
        elif backend == "openai":
            result = await _generate_openai(prompt, output_path, size, quality)
        elif backend == "ruizhi":
            result = await _generate_ruizhi(prompt, output_path)
        else:
            errors.append("未配置任何图片生成服务")
            break

        if result.success:
            return result
        errors.append(f"[{backend}] {result.error}")

    return ImageGenResult(
        success=False,
        error="; ".join(errors) if errors else "所有图片生成后端均不可用",
        backend="none",
    )


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
        "prompt": prompt[:4000],
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
            return ImageGenResult(success=False, error=str(exc), backend="openai")


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
        "prompt": prompt[:4000],
        "n": 1,
        "size": size,
        "format": "png",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{LOVART_BASE_URL}/images/generations",
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
            return ImageGenResult(success=False, error=str(exc), backend="lovart")


# ── Tutujin backend (gpt-image-2 via api.tutujin.com) ──────────────────────

async def _generate_tutujin(prompt: str, output_path: str, size: str, model: str = "gpt-image-2",
                             reference_url: str = "") -> ImageGenResult:
    """Generate image via api.tutujin.com — uses chat/completions API with optional image reference."""
    import ssl as _ssl, certifi as _certifi, re as _re

    key = settings.tutujin_api_key
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
            return ImageGenResult(success=False, error=f"{exc.__class__.__name__}: {exc}", backend="tutujin")


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
        "prompt": prompt[:4000],
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
            return ImageGenResult(success=False, error=f"{exc.__class__.__name__}: {exc}", backend="api0029")


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
        size = "1792x1024"

    def _do_request(field_name: str) -> tuple[int, bytes]:
        payload = {
            field_name: "gpt-image-2",
            "prompt": prompt[:1000],
            "n": 1,
            "size": size,
            "quality": "auto",
            "format": "png",
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{SHIYUN_BASE_URL}/v1/images/generations",
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
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    try:
        status, raw = await asyncio.to_thread(_do_request, "model")

        # Retry with "modal" field on validation error
        if status in (400, 422):
            text = raw.decode("utf-8", errors="replace").lower()
            if any(h in text for h in ("model", "modal", "missing", "required", "invalid")):
                status, raw = await asyncio.to_thread(_do_request, "modal")

        if status != 200:
            err = raw.decode("utf-8", errors="replace")[:500]
            logger.warning("ShiyunApi error (%s): %s", status, err)
            return ImageGenResult(success=False, error=f"ShiyunApi: HTTP {status} {err}", backend="shiyun")

        data = json.loads(raw.decode("utf-8", errors="replace"))

        # Parse response — try standard OpenAI format first
        img_bytes = None
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
        return ImageGenResult(success=False, error=str(exc), backend="shiyun")


# ── Agnes backend ────────────────────────────────────────────────────────

async def _generate_agnes(prompt: str, output_path: str, size: str) -> ImageGenResult:
    """Generate image using Agnes Image API (agnes-image-2.1-flash)."""
    key = settings.agnes_api_key
    if not key:
        return ImageGenResult(success=False, error="AGNES_API_KEY not configured", backend="agnes")

    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt[:4000],
        "n": 1,
        "size": size if size in ("1024x1024", "1792x1024", "1024x1792") else "1024x1024",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{AGNES_BASE_URL}/images/generations",
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
            return ImageGenResult(success=False, error=str(exc), backend="agnes")
