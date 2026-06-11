import asyncio
import logging
from collections.abc import AsyncGenerator
import anthropic
from app.config import settings

logger = logging.getLogger(__name__)

STREAM_TIMEOUT_SECONDS = 120  # max seconds between tokens before aborting


class LLMService:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=180.0,  # connection timeout
        )
        self.default_model = model or settings.claude_model

    async def stream_chat(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        thinking: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        kwargs = dict(
            model=model or self.default_model,
            max_tokens=max_tokens or settings.claude_max_tokens,
            temperature=temperature or settings.claude_temperature,
            system=system_prompt,
            messages=messages,
        )
        if thinking is not None:
            kwargs["thinking"] = thinking

        async with self.client.messages.stream(**kwargs) as stream:
            stream_iter = stream.text_stream.__aiter__()
            while True:
                try:
                    text = await asyncio.wait_for(
                        stream_iter.__anext__(),
                        timeout=STREAM_TIMEOUT_SECONDS,
                    )
                    yield text
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    logger.warning("Stream timed out after %ds with no token", STREAM_TIMEOUT_SECONDS)
                    raise

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout: float = 180.0,
        thinking: dict | None = None,
    ) -> anthropic.types.Message:
        kwargs = dict(
            model=model or self.default_model,
            max_tokens=max_tokens or settings.claude_max_tokens,
            temperature=temperature or settings.claude_temperature,
            system=system_prompt,
            messages=messages,
        )
        if thinking is not None:
            kwargs["thinking"] = thinking
        return await asyncio.wait_for(
            self.client.messages.create(**kwargs),
            timeout=timeout,
        )


llm_service = LLMService()
