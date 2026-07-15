"""PPT Maker v2 — constants: triggers, exit/confirm words, visual systems."""

SKILL_NAME = "ppt_maker"

# ── Trigger & routing ─────────────────────────────────────────────
TRIGGERS = ["做PPT", "制作PPT", "生成PPT", "帮我做PPT", "PPT", "ppt", "幻灯片", "演示文稿"]
KEYWORDS = ["ppt", "powerpoint", "slides", "deck", "提案", "路演", "汇报材料", "课件"]

EXIT_WORDS = {"退出", "返回", "不做了", "停止", "结束", "取消", "先不做", "退出skill", "退出 skill", "quit", "exit"}
CONFIRM_WORDS = {"确认", "可以", "没问题", "通过", "就这样", "ok", "okay", "yes", "确定", "开始", "继续", "好", "行", "嗯", "对", "是的", "没错", "对的", "好的", "可以的"}

# ── Entry descriptions ────────────────────────────────────────────
ENTRY_MENU = """请选择制作方式：

**1** — 上传资料或输入内容，生成 PPT 大纲（走完整 1→2→3→4 步）
**2** — 直接提供 PPT 大纲，从第 2 步开始制作缩略图
**3** — 上传 PPT 整体缩略图，从第 3 步开始输出分页高清图
**4** — 上传单页高清风格图，直接制作可编辑 PPTX"""

# ── Image generation ──────────────────────────────────────────────
IMAGE_TIMEOUT = 420  # 7 minutes max per image
IMAGE_SIZE = "1792x1024"

# ── PPTX output ───────────────────────────────────────────────────
SLIDE_WIDTH_INCHES = 13.333
SLIDE_HEIGHT_INCHES = 7.5
