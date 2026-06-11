"""Skill: extract user profile info from conversations. Runs automatically in background."""
from app.skills.base import BaseSkill, SkillContext, SkillResult


class ChatAnalyzerSkill(BaseSkill):
    name = "chat_analyzer"
    description = "从对话中自动提取用户信息，完善用户画像"
    triggers = []  # Runs automatically, not user-triggered
    keywords = []

    def can_handle(self, message: str) -> bool:
        return False  # Never triggered manually

    async def execute(self, context: SkillContext) -> SkillResult:
        # This skill runs via extract_user_info_from_message in chat_service
        return SkillResult(success=True, message="")
