"""Weekly report constants — hardcoded data, prompts, templates."""

from app.services._paths import WEEKLY_REPORT_DIR, WEEKLY_REPORT_TEMPLATE

SKILL_NAME = "weekly_report"
MIN_DETAIL_LENGTH = 10

DAY_NAMES = ["周一", "周二", "周三", "周四", "周五"]

OUTPUT_DIR = str(WEEKLY_REPORT_DIR)
TEMPLATE_FILE = str(WEEKLY_REPORT_TEMPLATE)
_PROJECT_ROOT = str(WEEKLY_REPORT_DIR.parent.parent)  # project root for backward compat

# 中国法定节假日（2026年，格式 MM-DD）
HOLIDAYS_2026: set[str] = {
    "01-01", "01-02", "01-03",  # 元旦
    "02-16", "02-17", "02-18", "02-19", "02-20", "02-21", "02-22",  # 春节
    "04-06", "04-07",  # 清明节
    "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
    "06-19", "06-20", "06-21",  # 端午节
    "09-25", "09-26", "09-27",  # 中秋节+国庆
    "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  # 国庆节
}

SYSTEM_PROMPT = """你是流程管理周报撰写助手。根据用户输入更新周报Excel的D列（本周计划）和E列（本周总结）。

职责范围：MO（管理商机）和SCE（售前-售后协同）流程体系，6个专项（做准N和T、价格管理、高质量执行MO、售前-售后协同、POC流程发布、SCE大项目大客户支持），IT数字化对接。
日常固定工作：流程L2/L3 PO日常支持、部门AI项目统筹管理与支持。

严禁写入以下内容：DG流程、LTC全链路、CRM系统建设、渠道流程及任何与MO/SCE无关的内容。

固定例会（除非用户明确说改时间，否则保持不变）：
- 周一上午：部门周例会
- 周四下午：MO周例会

核心规则（严格遵守）：
1. **用户输入是唯一依据**：只能根据用户提供的工作内容填写D/E列，不要编造用户没有提到的工作
2. 将用户的口语化描述转为专业流程管理术语，但内容必须是用户说的
3. B列、C列保持不动，只更新D列和E列
4. 用户可能只描述了部分时段的工作，其余时段可以留空（后续会自动补全）
5. 遇到法定节假日，对应日期的工作内容清空
6. 遇到调休工作日（周六/周日上班），按正常工作日处理
7. 返回严格JSON数组"""

# Default fill text variants for empty cells
MORNING_VARIANTS_D = [
    "流程材料更新与日常支持",
    "业务流程数据整理与分析",
    "专项工作材料准备",
    "跨部门沟通与协作对接",
]
MORNING_VARIANTS_E = [
    "完成流程材料更新及PO日常支持",
    "完成业务流程数据整理与分析",
    "完成专项工作材料准备工作",
    "完成跨部门沟通与事务对接",
]
AFTERNOON_VARIANTS_D = [
    "专项工作跟进与IT需求沟通",
    "流程优化方案讨论与推进",
    "业务分析与总结报告撰写",
    "L2/L3流程PO支持与答疑",
]
AFTERNOON_VARIANTS_E = [
    "完成专项工作跟进及IT需求对接",
    "完成流程优化方案讨论及推进",
    "完成业务分析与总结报告撰写",
    "完成L2/L3流程PO支持与答疑",
]
DEFAULT_D_LAST = "工作总结与复盘"
DEFAULT_E_LAST = "完成当日工作总结与复盘"
