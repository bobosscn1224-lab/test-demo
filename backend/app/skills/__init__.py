from app.skills.base import BaseSkill, SkillContext, SkillResult

_registry: list[BaseSkill] = []


def register(skill: BaseSkill):
    _registry.append(skill)


def get_all() -> list[BaseSkill]:
    return list(_registry)


def find_skill(message: str) -> BaseSkill | None:
    for skill in _registry:
        if skill.can_handle(message):
            return skill
    return None


def find_skill_by_name(name: str) -> BaseSkill | None:
    for skill in _registry:
        if skill.name == name:
            return skill
    return None


# Import skills to trigger registration
from app.skills.weekly_report import WeeklyReportSkill
from app.skills.ppt_maker import PPTMakerSkill
from app.skills.feishu_doc_reader import FeishuDocReaderSkill
from app.skills.chat_analyzer import ChatAnalyzerSkill

register(WeeklyReportSkill())
register(PPTMakerSkill())
register(FeishuDocReaderSkill())
register(ChatAnalyzerSkill())
