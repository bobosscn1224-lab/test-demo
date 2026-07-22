"""Gated vision-model boundary for generated-image semantic review."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import yaml

from app.config import settings
from app.services.llm_interaction import execute_with_quality_gate, _extract_json

_IMAGE_SPEC_PATH = Path(__file__).parent / "collage_prompt_spec.yaml"
with _IMAGE_SPEC_PATH.open(encoding="utf-8") as f:
    _raw = (yaml.safe_load(f) or {}).get("image_interactions") or {}
    # Top-level keys are interaction names (ppt_collage, ppt_slide, general_image);
    # _defaults and version are metadata, not interactions.
    IMAGE_GENERATION_SPECS = {
        k: v for k, v in _raw.items() if not k.startswith("_")
    }


def render_vision_review_prompt(
    interaction_name: str,
    prompt: str,
    context: dict[str, Any] | None = None,
) -> str:
    """Render one persisted review template while preserving literal JSON."""
    context = context or {}
    spec = IMAGE_GENERATION_SPECS.get(interaction_name) or {}
    template = spec.get("vision_review_prompt")
    if not template:
        raise ValueError(f"No vision review prompt for image interaction '{interaction_name}'")
    return str(template).format(
        prompt=prompt[:8000],
        expected_pages=context.get("expected_pages", "未指定"),
        columns=context.get("columns", 3),
        outline=str(context.get("outline", ""))[:5000],
    )


class VisionModelService:
    async def _raw_call_for_image(
        self, image_path: str, api_key: str, *, system_prompt: str, messages: list[dict],
        model: str | None = None, max_tokens: int = 4096,
        temperature: float = 0.1, timeout: float = 180,
        thinking: dict | None = None,
    ) -> Any:
        image_bytes = Path(image_path).read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        suffix = Path(image_path).suffix.lower()
        mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else "image/png"
        multimodal = [dict(message) for message in messages]
        for index in range(len(multimodal) - 1, -1, -1):
            if multimodal[index].get("role") == "user":
                text = str(multimodal[index].get("content", ""))
                multimodal[index]["content"] = [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{encoded}", "detail": "high",
                    }},
                ]
                break

        primary_model = model or "gemini-3-pro-thinking"
        from app.services.collage_prompt_spec import get_generation_runtime
        runtime = get_generation_runtime()
        model_candidates = [primary_model]
        for fallback in runtime.get("vision_fallback_models") or []:
            fallback = str(fallback).strip()
            if fallback and fallback not in model_candidates:
                model_candidates.append(fallback)

        payload = {
            "model": primary_model,
            "messages": [{"role": "system", "content": system_prompt}] + multimodal,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0)) as client:
            response = None
            for index, candidate in enumerate(model_candidates):
                payload["model"] = candidate
                response = await client.post(
                    f"{settings.tutujin_base_url.rstrip('/')}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}",
                             "Content-Type": "application/json"},
                    json=payload,
                )
                status_code = int(getattr(response, "status_code", 200))
                retryable_model_status = status_code in {400, 404, 429} or status_code >= 500
                if status_code < 400 or not retryable_model_status or index == len(model_candidates) - 1:
                    break
        assert response is not None
        response.raise_for_status()
        data = response.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            ),
        )

    async def analyze(
        self, *, interaction_name: str, system_prompt: str,
        user_prompt: str, image_path: str, api_key: str = "",
    ) -> dict[str, Any]:
        if api_key:
            key = api_key
        else:
            from app.services.tutujin_credentials import get_vision_credential
            key = get_vision_credential()
        from app.services.collage_prompt_spec import get_generation_runtime
        runtime = get_generation_runtime()
        model = str(runtime.get("vision_model") or "gemini-3-pro-thinking")

        async def raw_call(**kwargs):
            return await self._raw_call_for_image(image_path, key, **kwargs)

        guarded = await execute_with_quality_gate(
            interaction_name=interaction_name,
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            raw_call=raw_call,
            model=model,
            return_guarded_response=True,
        )
        data = _extract_json(guarded.content)
        if not isinstance(data, dict):
            raise RuntimeError("Vision quality gate did not return a JSON object")
        return data

    async def review_generated_image(
        self, *, interaction_name: str, prompt: str, image_path: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        review_prompt = render_vision_review_prompt(interaction_name, prompt, context)
        return await self.analyze(
            interaction_name="image_quality_review",
            system_prompt="你是独立、严格的图像质量门禁。只按验收规则返回 JSON，不美化结论。",
            user_prompt=review_prompt,
            image_path=image_path,
        )


vision_model_service = VisionModelService()
