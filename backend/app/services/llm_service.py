"""Paid text-model clients with a mandatory persistent quality gate."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import anthropic

from app.config import settings
from app.services.llm_interaction import (
    execute_with_quality_gate,
)


class LLMService:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=180.0,
        )
        self.default_model = model or settings.claude_model

    async def _chat_raw(
        self,
        *,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: float = 180.0,
        thinking: dict | None = None,
    ) -> anthropic.types.Message:
        """Vendor call. Only the quality-gate module may invoke this directly."""
        kwargs = dict(
            model=model or self.default_model,
            max_tokens=settings.claude_max_tokens if max_tokens is None else max_tokens,
            temperature=settings.claude_temperature if temperature is None else temperature,
            system=system_prompt,
            messages=messages,
        )
        if thinking is not None:
            kwargs["thinking"] = thinking
        return await asyncio.wait_for(self.client.messages.create(**kwargs), timeout=timeout)

    async def chat(
        self,
        *,
        interaction_name: str,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: float = 180.0,
        thinking: dict | None = None,
        extra_context: dict | None = None,
    ) -> anthropic.types.Message:
        guarded = await execute_with_quality_gate(
            interaction_name=interaction_name,
            system_prompt=system_prompt,
            messages=messages,
            raw_call=self._chat_raw,
            return_guarded_response=True,
            extra_context=extra_context,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            thinking=thinking,
        )
        return guarded.response

    async def stream_chat(
        self,
        *,
        interaction_name: str,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """Validate the complete answer before releasing any streamed chunk."""
        response = await self.chat(
            interaction_name=interaction_name,
            system_prompt=system_prompt,
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking=thinking,
        )
        from app.services.llm_interaction import extract_response_text
        text = extract_response_text(response)
        chunk_size = 96
        for start in range(0, len(text), chunk_size):
            yield text[start:start + chunk_size]
            await asyncio.sleep(0)


class SyncLLMService:
    """Synchronous gated client used only inside ingestion worker threads."""

    def __init__(self):
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=180.0,
        )
        self.default_model = settings.claude_model

    def _chat_raw(
        self, *, system_prompt: str, messages: list[dict], model: str | None = None,
        max_tokens: int | None = None, temperature: float | None = None,
        timeout: float = 180.0, thinking: dict | None = None,
    ):
        kwargs = dict(
            model=model or self.default_model,
            max_tokens=settings.claude_max_tokens if max_tokens is None else max_tokens,
            temperature=settings.claude_temperature if temperature is None else temperature,
            system=system_prompt,
            messages=messages,
        )
        if thinking is not None:
            kwargs["thinking"] = thinking
        return self.client.messages.create(**kwargs)

    def chat(self, *, interaction_name: str, system_prompt: str,
             messages: list[dict], **kwargs):
        guarded = asyncio.run(execute_with_quality_gate(
            interaction_name=interaction_name, system_prompt=system_prompt,
            messages=messages, raw_call=self._chat_raw,
            return_guarded_response=True, **kwargs,
        ))
        return guarded.response


llm_service = LLMService()
sync_llm_service = SyncLLMService()
