"""PPT Maker v2 — all LLM prompts in one place for easy tuning."""

# ── Material summarization (Pass 1 — fast, no thinking) ──────────────

MATERIAL_SUMMARY_SYSTEM = (
    "你是信息提炼专家。把用户提供的原始素材压缩为结构化摘要。"
    "保留所有关键事实、数据和叙事风格特征。丢弃冗余修饰词，但保留比喻、类比、故事框架等叙事载体。"
    "只输出摘要，不做评价、不补充知识。"
)

MATERIAL_SUMMARY_USER = """请将以下原始素材提炼为结构化摘要，严格按此格式输出：

**核心主题**：（一句话）
**叙事风格**：（素材用了什么表达方式？如：江湖武侠比喻、故事场景还原、技术架构拆解、数据分析论证等。1-2句描述）
**故事线/叙事逻辑**：（素材讲述的逻辑链条——先讲什么、再讲什么、最后得出什么，2-3句）
**关键事实与数据**：（逐条列出，保留原始数字、名称、术语）
**核心论点/观点**：（逐条列出）
**模块/章节结构**：（如素材有明确分段或章节，列出）

原始素材：
{source_text}"""

# ── Skeleton generation (Phase 1 — structure only) ───────────────────

SKELETON_SYSTEM = (
    "你是PPT叙事策略顾问。你的任务不是直接写大纲，而是先向用户呈现你的叙事思路——"
    "你想怎么讲这个故事，每一页在故事中扮演什么角色，页与页之间如何层层递进，最终如何达成汇报目标。"
    "用户确认思路后，才会进入逐页内容生成阶段。\n\n"
    "要求：\n"
    "1. 先理解素材的内容和叙事风格，再设计叙事逻辑。\n"
    "2. 每一页都要说清楚：为什么需要这一页？它在整个论证链中起什么作用？听众看完这页会有什么变化？\n"
    "3. 页与页之间必须有明确的逻辑关系——上一页的结论如何自然引出下一页的主题。\n"
    "4. 用用户素材中的比喻和故事来命名和描述页面，不要用千篇一律的商业术语。"
)

SKELETON_USER = """请先阅读下方资料，然后向用户呈现你的叙事策略提案。

输出分两部分：先讲整体思路，再列逐页逻辑。

---
## 一、整体叙事策略

**我选择的叙事框架**：（六选一 + 为什么这个框架最适合这份素材和目标受众）

**叙事风格**：（从素材中提取的表达风格——江湖比喻？故事还原？技术拆解？）

**开场钩子**：（用什么方式在前两页抓住老板的注意力——一个反常识的对比？一个紧迫的冲突？一个生动的场景？）

**叙事逻辑链**：（用3-5句话描述整个PPT的叙事弧线——从哪开始、经过哪些转折、高潮在哪、如何收束到行动。要让人能想象出听这个汇报时的情绪曲线。）

**关键转折点**：（整个叙事中有几个关键转折？每个转折要达成什么效果？）

## 二、逐页逻辑设计

对每一页，请说明：

### 第1页：封面
- **为什么需要这一页**：（在叙事中的作用——不只是"定调"，要说清楚定什么调、建立什么期待）
- **标题**：（观点式标题——这页的核心主张）
- **听众看完这页会**：（产生什么感受/想法/疑问）

### 第2页：[页面在叙事中的功能命名，如：制造冲突/建立共识/抛出问题等]
- **为什么需要这一页**：（在叙事中的作用）
- **承接上一页的逻辑**：（从___过渡到___，为什么这个顺序是合理的）
- **标题**：（观点式标题）
- **表达方式**：（这页用什么方式来讲——讲故事？场景还原？数据对比？比喻类比？概念拆解？）
- **听众看完这页会**：（产生什么变化）

### 第3页：[功能命名]
...（同上格式，直到最后一页）

### 最后一页：总结与行动号召
- **为什么需要这一页**：（收束全篇的作用）
- **标题**：（观点式标题）
- **听众看完这页会**：（产生什么行动冲动）

---
⚠️ 页数必须严格在 {page_range} 范围内，不得多也不得少。

{briefing_text}

资料：
{source_text}

{revision_text}

请先输出以上叙事策略提案，等待用户确认后再进入逐页内容生成。"""

# ── Outline generation (Pass 2 — full) ───────────────────────────────

OUTLINE_SYSTEM = (
    "你是资深演示策略顾问，面向老板/决策层做汇报。你的任务是把用户素材组织为有钩子、有冲突、"
    "有画面感的PPT逐页大纲。\n\n"
    "【受众】老板/决策层——不喜欢数据堆砌和技术细节，喜欢抽象概念、生动比喻、引人入胜的故事。"
    "一个精彩的比喻胜过十页数据表格。但每个故事都要落到战略价值和决策行动上。\n\n"
    "【叙事心法】\n"
    "1. 钩子开场（Hook）：封面或第1页必须有一个让人停下来的钩子——一个反常识的对比、一个紧迫的冲突、一个画面感极强的场景。\n"
    "2. 制造冲突（Conflict）：好故事必有冲突。现状 vs 理想、我们的能力 vs 对手的装备、不走 vs 走的代价。让听众感受到张力。\n"
    "3. 听众是主角（Hero）：决策层是故事的主角，你的方案是给他们的武器/地图/机会。不要把自己（讲者）当成主角。\n"
    "4. 画面先行（Show, don't tell）：每页先想「听众看到这页时脑海中应该浮现什么画面」，再写文字。\n"
    "5. 落到行动（So what）：每页结束时问自己「所以呢？」——这一页的洞察指向什么决策或行动？\n\n"
    "【铁律】\n"
    "1. 用户素材是唯一内容来源。不编造。缺数据标[需填入真实数据]。\n"
    "2. 保留用户的叙事风格和所有生动的比喻、故事、场景——这些是素材的精华。\n"
    "3. 每页要点至少有一条引用素材中的具体故事/场景/比喻，不只列抽象概念。\n"
    "4. 页数严格按用户指定范围。每页五个字段缺一不可。"
)

OUTLINE_USER = """你是一位资深演示策略顾问。请严格按以下流程和格式输出PPT大纲。

## 第一步：理解材料（在脑海中完成，不输出）

完整阅读下方「资料」中的全部内容，提取：
- 关键事实、数据、逻辑
- **叙事风格**：用户用了什么表达方式（故事？比喻？分析？场景？）
- **故事线**：素材的逻辑链条是什么

## 第二步：选择叙事框架 + COSTAR 策略分析（在脑海中完成）

从以下六种经典叙事框架中选择最合适的一种，并在「演示策略」中写明为什么选它：

1. **冲突驱动型**（Villain-Hero-Guide）：先制造威胁/冲突 → 让听众感受到紧迫 → 引出你的方案作为武器/地图 → 听众成为主角去行动。最抓眼球，适合需要促成重大决策的汇报。
2. **SCR型**（Situation-Complication-Resolution）：现状是什么 → 出现了什么复杂因素 → 我们的解决方案是什么。麦肯锡/BCG经典，适合严谨的商业分析和战略汇报。
3. **问题驱动型**：现状→问题→根因→方案→收益→计划。适合改进类、复盘类汇报。
4. **机会驱动型**：趋势→机会→能力→路径→回报→行动。适合提案类、新业务拓展类汇报。
5. **ABT型**（And-But-Therefore）：___和___（现状），但是___（冲突），因此___（方案）。最简单的三幕结构，适合简洁有力的短汇报。
6. **钩子递进型**（Hook-Conflict-Resolution）：用一个反常识的钩子开场 → 层层展开冲突 → 高潮处给出解决方案 → 收束为行动号召。适合故事化、创意化的汇报。

然后进行 COSTAR 分析：
- **C**ontext：业务背景
- **O**bjective：要促成什么决策
- **S**tyle：用户素材的叙事风格（从素材中提取）
- **T**one：语调
- **A**udience：受众
- **R**esponse：输出格式

## 第三步：输出逐页大纲（这是你要输出的内容 — 格式强制）

必须严格按以下模板输出，不得省略任何字段，不得改变字段顺序：

---
## 演示策略
**演示目的**：（一句话）
**目标受众**：（谁，关心什么）
**叙事框架**：（从六种框架中选了哪一种 + 为什么选它）
**叙事风格**：（用户素材的表达方式——江湖比喻、故事还原、技术拆解等。后续每页必须延续此风格）
**钩子设计**：（用什么钩子抓住注意力——反常识对比？紧迫冲突？画面场景？在第1页如何体现？）
**关键信息**：（3-5条听众必须记住的核心要点）

## 逐页大纲

⚠️ 以下每一页的标题、正文要点和画面构思都必须延续上面「叙事风格」中确定的表达方式。
如果叙事风格是"江湖武侠比喻"，就不要出现"战斗机""骑兵""炮火"等现代军事隐喻，而是使用"内功""招式""门派""对决"等江湖语汇。
第2页到最后一页，每写一页前先回顾第1页的叙事风格，确保全篇风格统一。

### 第1页：封面
- **本页在故事中的角色**：第一印象，定调
- **主标题**：（观点式标题）
- **副标题**：（补充说明）
- **场合/日期**

### 第2页：[页面类型：目录/背景/问题/分析/方案/总结等]
- **本页在故事中的角色**：（这页在叙事中起什么作用）
- **与前一页的关系**：（从___自然过渡到___）
- **核心信息**：（听众看完这页必须记住的一句话）
- **结论式标题**：（观点，不是话题）
- **正文要点**：（至少3条，每条10-30字，具体不空洞）
- **画面构思和视觉建议**：（2-3句构图描述 + 色彩氛围 + 图文比例 + 视觉焦点 + 具体图表类型）

---

## 格式示例（⚠️ 仅示范格式和字段完整度，内容和主题必须来自下方「资料」）

以下示例仅用于展示**每个字段应该怎么写、写到什么深度**。
你实际输出的内容**必须完全基于下方「资料」中的素材**，不得照搬示例的主题、数据或叙事。

### 第1页：封面
- **本页在故事中的角色**：[说明这页在整体叙事中的作用，如：第一印象、定调、建立期待]
- **主标题**：[观点式标题，必须提炼自用户素材的核心主张]
- **副标题**：[补充说明，点明范围或受众]
- **场合/日期**：[根据项目场景填写]

### 第2页：[根据素材内容命名页面类型，如：背景/问题/现状/趋势等]
- **本页在故事中的角色**：[这页在叙事中起什么作用]
- **与前一页的关系**：[从___自然过渡到___]
- **核心信息**：[听众看完这页必须记住的一句话，必须来自素材]
- **结论式标题**：[观点，不是话题]
- **正文要点**：
    - [每条10-30字，包含素材中的具体事实、数字或逻辑]
    - [至少3条，每条都要有信息量，不用空话套话]
    - [如果素材提供了数据，必须引用；如果素材没有，标注[需填入真实数据]]
- **画面构思和视觉建议**：[2-3句构图描述 + 色彩氛围 + 图文比例 + 视觉焦点 + 具体图表类型]

（以上是格式模板。现在请基于下方「资料」中的实际内容，为当前项目输出完整的逐页大纲。）

{briefing_text}

## 资料（唯一内容来源——所有输出必须基于此）
{source_text}

{revision_text}

---
## 输出后强制风格审计（不符合则重写）

在输出完整大纲后，必须逐页检查以下两项：

1. **隐喻体系统一**：全篇所有页面是否使用了同一套叙事语言？
   - 如果第1页用「江湖/侠客/内功/招式」→ 后续页面也必须用江湖语汇
   - 如果第1页用「战场/武器/战术」→ 后续页面也必须用军事语汇
   - 禁止混用：不要第1页说「内功心法」→ 第5页说「战斗机」「炮火」
   - 禁止第3页之后突然切换隐喻体系

2. **内容来源**：每页的事实和数据是否都来自上方「资料」？
   - 如果某页出现了资料中完全没有的概念、案例或数据 → 删除重写
   - 增强模式下补充的内容是否标注了[AI增强]？

⚠️ 如果任一检查未通过，请修改相关页面后再输出。"""

# ── Visual collage prompts (step 2) ───────────────────────────────

COLLAGE_BASE = """Generate one collage image for a {page_count}-slide PowerPoint deck.

MANDATORY GRID RULES — VIOLATION MEANS REGENERATION:
1. EXACT GRID: {page_count} slides in {grid_hint}, reading order left-to-right, top-to-bottom.
2. IDENTICAL SIZE: EVERY slide thumbnail MUST be the EXACT SAME pixel width and EXACT SAME pixel height. No slide is wider, narrower, taller, or shorter than any other slide. Slide 1 = Slide 7 = Slide {page_count} in dimensions.
3. If the last row has fewer slides than columns, leave the empty cells BLANK. Do NOT stretch, enlarge, or resize any slide to fill gaps.
4. All slides 16:9 horizontal. Uniform 10-15px gaps. Clean margins on all sides.

{project_context}

DECK CONTENT (design slides based on this content):
{slide_summary}

{visual_direction}

OUTPUT: One collage PNG — {page_count} identical-size 16:9 thumbnails."""

VISUAL_DIRECTIONS = {
    "A": "VISUAL STYLE A — Premium Consulting Report: Light, airy, confident. Think McKinsey/BCG. Bright white backgrounds, precise typography, one bold accent color (deep blue or teal) used sparingly for headers and key data. Clean charts. The feeling: credible, sharp, data-driven.",
    "B": "VISUAL STYLE B — Tech Keynote: Dark, immersive, futuristic. Think Apple/Google keynotes. Deep navy or charcoal backgrounds, glowing neon accents (cyan, electric blue, emerald), luminous data visualizations. The feeling: cutting-edge, visionary, bold.",
    "C": "VISUAL STYLE C — Editorial Business: Sophisticated, refined, cultured. Think high-end brand deck or design magazine. Generous whitespace, muted sophisticated palette (warm grays, soft blush, cream), elegant serif/display typography, artistic image use. The feeling: tasteful, premium, trustworthy.",
}

# ── Single page prompts (step 3) ──────────────────────────────────

SINGLE_PAGE_BASE = """你正在从一套已选定的PPT拼图方案中，单独还原第{page_num}页为一张高清16:9单页幻灯片。

注意：你的第二条输入是一张完整的PPT拼图参考图（方案{choice_label}）。你需要从拼图中找到第{page_num}页的缩略图位置，提取它的视觉风格（配色、字体、排版、间距、背景），然后严格基于下面的确认内容，生成一张完整的高清单页。

LAYOUT TYPE DETECTED: {layout_type}

VISUAL SYSTEM:
{style_text}

CONFIRMED CONTENT (from the approved outline):
{slide_content}

CRITICAL RULES:
1. Output exactly ONE slide — no collages, no multi-page
2. Faithfully match the collage layout, spacing, and visual proportions
3. Page number "{page_num}" MUST be visible on the slide
4. All Chinese text MUST be correct and properly rendered
5. Use ONLY the confirmed content above — do not invent new data
6. If collage details (small text, chart numbers) are unclear, supplement from the confirmed outline above while preserving the original visual layout
7. Maintain the visual proportion and design language from the collage
8. The slide must look like a finished, high-quality business presentation slide
9. 16:9 aspect ratio, professional business aesthetic
10. Do NOT include any UI elements, watermarks, or "page X of Y" indicators except the page number
11. Background must match the visual system color palette exactly"""

# ── Step 3 intro messages ─────────────────────────────────────────

STEP2_PROGRESS = [
    "进度 1/4：正在读取已确认的大纲和逐页内容...",
    "进度 2/4：正在准备三版不同视觉方向的 PPT 拼图提示词...",
    "进度 3/4：正在检查 imagegen 图片生成能力...",
]

STEP3_INTRO = "收到，开始逐页生成高清 16:9 单页 PPT 视觉稿。\n\n"

COLLAGE_RESULT_TEMPLATE = """方案 {label} 已生成：

![方案 {label}](/api/skills/download/{filename})

[下载方案 {label} 拼图](/api/skills/download/{filename})

{filler}"""

COLLAGE_CHOICE_PROMPT = "\n\n请选择方案 A / B / C，或回复「重新生成」重做。"
PAGE_GENERATED_TEMPLATE = "第 {idx}/{total} 页已生成：**{title}**\n\n![第{idx}页](/api/skills/download/{filename})\n\n"
PAGE_ALL_DONE = "\n全部 {total} 页生成完毕！请回复你要生成哪几页的 PPTX（如「1-5」「全部」等）。"
