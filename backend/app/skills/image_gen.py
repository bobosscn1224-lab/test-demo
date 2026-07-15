"""Image Generation Skill — interactive multi-turn text-to-image via Agnes.

Conversation flow:
  1. User: "生成图片" → Skill: "你想生成什么图片？请描述一下"
  2. User: "一只穿西装的猫" → Skill: generates image, shows it, offers actions
  3. User: "换一张" → regenerates | "修改xxx" → changes prompt | "退出" → exits
"""
from __future__ import annotations

import os
import uuid
import logging

from app.config import settings
from app.skills.base import BaseSkill, SkillContext, SkillResult
from app.core.skill_session import SkillSessionHelper
from app.services._paths import PUBLIC_DIR

logger = logging.getLogger(__name__)

SKILL_NAME = "image_gen"
_sessions: dict[str, dict] = {}
_helper = SkillSessionHelper(SKILL_NAME, _sessions)

# Output dir: unified public output directory (served by /api/skills/download/)
_OUTPUT_DIR = str(PUBLIC_DIR)

EXIT_WORDS = {"退出", "结束", "不生了", "停止", "取消", "算了", "返回", "不画了"}
REGENERATE_WORDS = {"换一张", "再来一张", "重新生成", "再画一张", "重画"}
EDIT_PREFIXES = ("修改", "改成", "改为", "换成", "换一个", "换成")


class ImageGenSkill(BaseSkill):
    name = "image_gen"
    description = "通过文本描述生成图片，支持迭代修改。输入生成图片开始"
    triggers = ["生成图片", "画一张", "画一张图", "生成一张图", "ai画图", "ai绘图", "ai生成图片", "文生图"]
    keywords = ["生成图片", "画图", "绘图", "作图", "画一张"]

    async def execute(self, context: SkillContext) -> SkillResult:
        msg = context.user_message.strip()
        sid = context.session_id or "default"

        # Restore persisted sessions on first access
        await _helper.restore()

        if self._is_exit(msg):
            await _helper.delete(sid)
            return SkillResult(success=True, message="已退出图片生成。可以继续其他对话。")

        session = _sessions.get(sid)

        # ── First call / restart: ask for prompt ──
        if not session:
            # Check if user included a description with the trigger
            prompt = _extract_prompt(msg)
            if prompt:
                return await self._do_generate(sid, prompt)
            # No description — ask
            await _helper.save(sid, {"stage": "awaiting_prompt"})
            return SkillResult(
                success=True,
                message="你想生成什么图片？请描述一下画面内容、风格等。\n\n例如：`一只穿西装的猫在会议室，扁平商务插画风格`",
            )

        stage = session.get("stage")

        # ── Stage 1: awaiting prompt ──
        if stage == "awaiting_prompt":
            return await self._do_generate(sid, msg)

        # ── Stage 2: awaiting action after generation ──
        if stage == "awaiting_action":
            if msg in REGENERATE_WORDS:
                return await self._do_generate(sid, session["last_prompt"])
            if msg.startswith(EDIT_PREFIXES):
                new_prompt = _clean_prompt(msg)
                return await self._do_generate(sid, new_prompt if new_prompt else session["last_prompt"])
            # New prompt — treat as fresh description
            return await self._do_generate(sid, msg)

        # Unknown — reset
        await _helper.delete(sid)
        return await self.execute(context)

    @staticmethod
    def _is_exit(msg: str) -> bool:
        """Check if the message is an exit command (short messages only)."""
        normalized = msg.strip().replace(" ", "")
        if len(normalized) > 8:
            return False
        for word in EXIT_WORDS:
            if word in normalized:
                return True
        return False

    async def execute_stream(self, context: SkillContext):
        """Streaming variant — yields progress during image generation."""
        msg = context.user_message.strip()
        sid = context.session_id or "default"

        await _helper.restore()

        if self._is_exit(msg):
            await _helper.delete(sid)
            yield SkillResult(success=True, message="已退出图片生成。")
            return

        session = _sessions.get(sid)

        if not session:
            prompt = _extract_prompt(msg)
            if prompt:
                yield f"正在生成图片：{prompt[:100]}...\n"
                async for item in self._generate_stream(sid, prompt):
                    yield item
                return
            await _helper.save(sid, {"stage": "awaiting_prompt"})
            yield SkillResult(
                success=True,
                message="你想生成什么图片？请描述一下画面内容、风格等。\n\n例如：`一只穿西装的猫在会议室，扁平商务插画风格`",
            )
            return

        stage = session.get("stage")
        if stage == "awaiting_prompt":
            yield f"正在生成图片...\n"
            async for item in self._generate_stream(sid, msg):
                yield item
            return

        if stage == "awaiting_action":
            if msg in REGENERATE_WORDS:
                yield "正在重新生成...\n"
                async for item in self._generate_stream(sid, session["last_prompt"]):
                    yield item
            elif msg.startswith(EDIT_PREFIXES):
                new_prompt = _clean_prompt(msg)
                yield f"正在按修改重新生成...\n"
                async for item in self._generate_stream(sid, new_prompt if new_prompt else session["last_prompt"]):
                    yield item
            else:
                async for item in self._generate_stream(sid, msg):
                    yield item
            return

        await _helper.delete(sid)
        yield await self.execute(context)

    async def _generate_stream(self, sid: str, prompt: str):
        """Yields progress tokens during generation, then final SkillResult."""
        from app.services.image_gen_service import generate_image

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        filename = f"gen_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(_OUTPUT_DIR, filename)

        yield "⏳ 正在调用图片生成服务...\n"
        result = await generate_image(prompt, output_path, size="1024x1024")

        if not result.success:
            yield SkillResult(success=False, message=f"生成失败：{result.error}")
            return

        img_url = f"http://localhost:8011/api/skills/download/{filename}"
        _sessions[sid] = {"stage": "awaiting_action", "last_prompt": prompt, "last_image": output_path}
        await _helper.save(sid, _sessions[sid])

        yield SkillResult(
            success=True,
            message=(
                f"![{prompt}]({img_url})\n\n"
                f"💬 **换一张** 重新生成 | **修改 xxx** 调整描述 | **退出** 结束"
            ),
            data={"skill": self.name, "image_path": output_path, "download_url": img_url},
        )

    async def _do_generate(self, sid: str, prompt: str) -> SkillResult:
        from app.services.image_gen_service import generate_image

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        filename = f"gen_{uuid.uuid4().hex[:8]}.png"
        output_path = os.path.join(_OUTPUT_DIR, filename)

        result = await generate_image(prompt, output_path, size="1024x1024")
        if not result.success:
            return SkillResult(success=False, message=f"生成失败：{result.error}")

        img_url = f"http://localhost:8011/api/skills/download/{filename}"

        _sessions[sid] = {"stage": "awaiting_action", "last_prompt": prompt, "last_image": output_path}
        await _helper.save(sid, _sessions[sid])

        return SkillResult(
            success=True,
            message=(
                f"![{prompt}]({img_url})\n\n"
                f"💬 **换一张** 重新生成 | **修改 xxx** 调整描述 | **退出** 结束"
            ),
            data={"skill": self.name, "image_path": output_path, "download_url": img_url},
        )


def _extract_prompt(msg: str) -> str | None:
    """Extract description after trigger word. Returns None if only trigger.

    Only extracts when the message CLEARLY starts with a trigger word.
    If the message doesn't start with a trigger, it's likely not an image generation request.
    """
    triggers_sorted = sorted(
        ["生成一张图", "生成图片", "ai生成图片", "ai画图", "ai绘图", "文生图", "画一张图", "画一张", "帮我生成图片", "帮我画"],
        key=len, reverse=True,
    )
    for t in triggers_sorted:
        if msg.startswith(t):
            remaining = msg[len(t):].strip().lstrip("，,：:；;！!\n ")
            return remaining if remaining else None
    # Message doesn't start with any trigger — don't treat as image prompt
    return None


def _clean_prompt(msg: str) -> str:
    """Remove edit prefixes like 修改/改成/改为."""
    for prefix in EDIT_PREFIXES:
        if msg.startswith(prefix):
            return msg[len(prefix):].strip()
    # Try "修改成" and "修改为" (two-character combinations)
    for prefix in ("修改成", "修改为"):
        if msg.startswith(prefix):
            return msg[len(prefix):].strip()
    return msg
