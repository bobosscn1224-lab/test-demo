from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SkillContext:
    db: AsyncSession
    user_message: str
    persona_slug: str | None = None
    session_id: str | None = None
    uploaded_files: list[dict] = field(default_factory=list)  # [{filename, path, content_type}]
    extra: dict = field(default_factory=dict)


@dataclass
class SkillResult:
    success: bool
    message: str                     # Text response to show user
    data: dict = field(default_factory=dict)  # Additional data (file paths, download URLs, etc.)
    follow_up_action: str | None = None  # "download", "redirect", None


class BaseSkill:
    name: str = ""
    description: str = ""
    triggers: list[str] = []         # ["写周报", "周报"]
    keywords: list[str] = []         # ["周报", "weekly", "report"]

    def can_handle(self, message: str) -> bool:
        msg_lower = message.lower()
        for trigger in self.triggers:
            if trigger.lower() in msg_lower:
                return True
        for kw in self.keywords:
            if kw.lower() in msg_lower:
                return True
        return False

    async def execute(self, context: SkillContext) -> SkillResult:
        raise NotImplementedError
