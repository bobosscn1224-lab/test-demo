# 数字分身 — 项目宪法

> 所有开发、AI 调用、代码变更必须遵循本文档。改动先更新文档。

---

## 一、核心设计原则

### 0. 需求驱动开发流程（铁律）

**拿到需求后，禁止直接动手改代码。必须先完成以下步骤：**

```
需求 → 分析 → 设计 → 评审 → 实现 → 验证
```

| 步骤 | 必须做的事 | 禁止跳过 |
|------|-----------|---------|
| **分析** | 读当前架构、数据流、已有的规范文件，理解现状 | ❌ 不看代码就提方案 |
| **设计** | 基于现有设计模式（持久化规范、共享模块、v1/v2 共存）提出方案，说明改动范围和影响 | ❌ 不考虑架构一致性 |
| **评审** | 确认方案与项目宪法一致，复用已有规范而非新建 | ❌ 方案未确认就开始写 |
| **实现** | 按方案写代码，先改规范文件再改代码 | ❌ 边写边改方向 |
| **验证** | 跑编译、启动服务、端到端测试 | ❌ 不测试就说完成 |

**判断标准**：如果改动后需要把同样的规则在多个地方各改一遍 → 设计有问题，应该抽取共享模块。

### 1. 大模型交互标准范式（铁律）

**每一次与大模型（LLM / Image Model）的交互，必须严格遵循以下范式：**

```
┌──────────────────────────────────────────────────────────────┐
│                    STANDARD LLM INTERACTION                    │
│                                                               │
│  1. SPEC   → 从持久化规范文件加载：要求、规则、输入            │
│  2. CALL   → 调用大模型，传入规范化的 prompt                   │
│  3. CHECK  → 校验输出是否满足质量要求                          │
│  4. RETRY  → 不满足？用具体反馈让大模型完善（最多 N 次）        │
│  5. GATE   → 只返回通过所有质量检查的结果                      │
└──────────────────────────────────────────────────────────────┘
```

**禁止行为**：
- ❌ 直接调用 LLM 而不经过质量校验
- ❌ 在业务代码中硬编码 prompt 规则
- ❌ 接受不满足要求的输出
- ❌ 跳过重试机制

**实现方式**：
- 所有 LLM 交互使用 `app/services/llm_interaction.py` 的 `execute_with_quality_gate()`
- 所有图像生成使用 `app/services/collage_prompt_spec.py` 的 `build_collage_prompt()` + `validate_output()`
- 交互规范持久化在 `app/services/llm_interaction_spec.yaml`
- 图像生成规范持久化在 `app/services/collage_prompt_spec.yaml`

### 2. 持续改进与问题回溯原则（铁律）

**每次出现问题或 Bug，必须完成以下闭环，不得只修不究：**

```
发现问题 → 定位根因 → 记录教训 → 完善规范 → 交付
```

| 步骤 | 必须做的事 |
|------|-----------|
| **定位根因** | 不是修表面现象，是找到造成问题的**关键缺失点**。例如：是 prompt 没约束？是校验没做？是规范文件没更新？ |
| **记录教训** | 将根因和教训写入 `CLAUDE.md` 的「问题回溯记录」章节，记录：什么现象、根因是什么、哪个环节没做好、如何防止复发 |
| **完善规范** | 根据教训更新对应的规范 YAML 文件或设计原则，确保同类问题不会复现 |
| **验证闭环** | 修复后验证，确认问题解决 + 规范已更新 |

**禁止行为**：
- ❌ 只修 bug 不分析根因
- ❌ 同样的错误出现两次
- ❌ 发现问题是因为规范缺失，却不补规范

### 3. 持久化优先原则

**任何规则、约束、prompt 模板必须持久化到规范文件中，不得硬编码。**

| 持久化文件 | 管理内容 |
|-----------|---------|
| `app/services/llm_interaction_spec.yaml` | LLM 交互的质量检查规则、重试模板、模型参数 |
| `app/services/collage_prompt_spec.yaml` | 拼图生图的所有规则：网格约束、视觉方向、内容处理 |
| `DEVELOPMENT_CONTRACT.md` | 前后端接口契约、字段映射、状态机 |
| `CLAUDE.md` | 本文档 — 项目级设计原则和开发规范 |

### 4. 单一真相来源原则

**每条规则只有一个权威定义位置。** 如果一条规则出现在两个地方，这是 bug。

---

## 二、问题回溯记录

> 每次出现问题，记录：现象、根因、哪个环节没做好、如何防止复发。

### 2026-07-16：拼图缩略图尺寸不一致

| 项 | 内容 |
|----|------|
| **现象** | 生成的拼图中，各页面缩略图尺寸不统一（前 6 页正常，第 7-10 页变窄） |
| **根因** | prompt 中缺少严格的 same-size 约束。旧 prompt 只说了"16:9"，没强调"Slide 1 = Slide 7 = Slide N" |
| **缺失环节** | prompt 设计时未充分考虑 AI 模型的排版自由度，把布局约束写得太宽松 |
| **修复** | 在 `collage_prompt_spec.yaml` 中加入 `MANDATORY GRID RULES` 块，明确 "EVERY slide IDENTICAL size" |
| **防止复发** | 所有生图 prompt 必须从 `collage_prompt_spec.yaml` 构建，prompt 第一条必须是网格强制规则 |

### 2026-07-16：拼图内容与大纲不一致（合规审查 → 经营报告）

| 项 | 内容 |
|----|------|
| **现象** | 大纲是关于"合规审查"的，但生成的拼图风格像"经营报告"，内容完全不匹配 |
| **根因** | `_extract_slide_summary()` 的 split 正则要求 `第X页：`（冒号紧跟），但实际大纲是 `第X页\n**标题**`（换行），导致提取返回空字符串。gpt-image-2 没有收到任何内容上下文 |
| **缺失环节** | (1) 提取函数设计时未考虑大纲格式多样性 (2) 没有预生成校验来检测内容丢失 (3) 测试时未用真实大纲数据验证 |
| **修复** | (1) 改为 `strip_visual_suggestions()`：保留所有内容，只删视觉建议 (2) 加入 `validate_prompt()` 预生成校验 (3) 用真实项目数据测试 |
| **防止复发** | (1) prompt 构建后必须跑 `validate_prompt()` 检查 (2) 任何内容提取函数必须用真实数据做回归测试 |

### 2026-07-16：tutujin API 间歇性返回空响应

| 项 | 内容 |
|----|------|
| **现象** | 方案 B 生成成功，方案 A 同一大纲生成失败：`no image in response. Content preview: (空)` |
| **根因** | tutujin gpt-image-2 API 间歇性空返回，没有重试机制 |
| **缺失环节** | 调用外部 API 未考虑失败重试 |
| **修复** | 在 `image_gen_service.py` 的 `_generate_tutujin()` 中加入一次自动重试 |
| **防止复发** | 所有外部 API 调用应有合理的重试策略 |

### 2026-07-16：prompt 格式从中文改成英文导致生图布局漂移（反复出现 3 次）

| 项 | 内容 |
|----|------|
| **现象** | 拼图缩略图尺寸不一致问题反复出现 3 次，每次修完 prompt 后又复发 |
| **根因** | 我们将 prompt 从**中文 + `━━━` 结构**改成了**英文 designer-brief 风格**。gpt-image-2 对中文结构化指令（`━━━ 排版约束 ━━━` + 逐条编号 + 具体 px 值）的响应远比英文 "designer brief" 可靠。旧 prompt 工作正常，我们的"优化"反而破坏了它 |
| **缺失环节** | (1) 改动前没有对比旧 prompt 格式的有效性 (2) 假设英文和中文 prompt 效果一样 (3) 没有意识到 gpt-image-2 对特定 prompt 格式有偏好 |
| **修复** | 将 prompt 模板还原为中文 + `━━━` 结构，保留我们添加的内容改进（strip_visual_suggestions、project_context、validation） |
| **防止复发** | **铁律：gpt-image-2 prompt 必须使用中文 + `━━━` 结构化格式，不得改为英文**。此规则已写入 `collage_prompt_spec.yaml` 注释 |

### 2026-07-16：Python 3.9 类型语法不兼容

| 项 | 内容 |
|----|------|
| **现象** | 服务启动报错 `TypeError: unsupported operand type(s) for |` |
| **根因** | 项目代码使用了 Python 3.10+ 的 `str | None` 语法，但 macOS 环境是 Python 3.9 |
| **缺失环节** | 项目未声明 Python 版本要求，也未在启动时检查 |
| **修复** | 55 个文件添加 `from __future__ import annotations` |
| **防止复发** | 如升级 Python 版本，需同步更新 requirements.txt 中的版本约束 |

| 持久化文件 | 管理内容 |
|-----------|---------|
| `app/services/llm_interaction_spec.yaml` | LLM 交互的质量检查规则、重试模板、模型参数 |
| `app/services/collage_prompt_spec.yaml` | 拼图生图的所有规则：网格约束、视觉方向、内容处理 |
| `DEVELOPMENT_CONTRACT.md` | 前后端接口契约、字段映射、状态机 |
| `CLAUDE.md` | 本文档 — 项目级设计原则和开发规范 |

---

## 三、LLM 调用规范

### 标准调用代码

```python
from app.services.llm_interaction import execute_with_quality_gate

result = await execute_with_quality_gate(
    interaction_name="outline_generation",  # 对应 llm_interaction_spec.yaml 中的 key
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    llm_service=llm_service,
    extra_context={                         # 用于重试 prompt 构建
        "source_text": source_text,
        "briefing_text": briefing_text,
    },
)

if not result.success:
    # 质量检查未通过，result.error 包含失败原因
    # result.quality_failures 包含每项失败的具体反馈
    raise Exception(f"Quality gate failed: {result.error}")
```

### 图像生成调用规范

```python
from app.services.collage_prompt_spec import (
    build_collage_prompt, strip_visual_suggestions,
    validate_prompt, validate_output,
)

# 1. 清理大纲（去掉视觉建议，保留所有内容）
cleaned_outline = strip_visual_suggestions(outline)

# 2. 构建标准化 prompt
prompt = build_collage_prompt(
    total_pages=page_count,
    cleaned_outline=cleaned_outline,
    variant_label="A",
    project_context="应用场景：业务汇报\n目标受众：管理层",
)

# 3. 发送前校验
warnings = validate_prompt(prompt, page_count, cleaned_outline)

# 4. 调用生图 API
error = await image_gen.generate(prompt, output_path, timeout=420)

# 5. 生成后校验
output_warnings = validate_output(output_path)
```

### 新增 LLM 交互的流程

1. 在 `llm_interaction_spec.yaml` 添加新的 interaction section，定义 `quality_checks`、`retry_prompt_template`
2. 实现时调用 `execute_with_quality_gate(interaction_name="新交互名称", ...)`
3. 框架自动处理校验、重试、把关

---

## 四、项目架构

```
backend/app/
├── services/
│   ├── llm_interaction.py          ← LLM 交互框架（所有人必须用）
│   ├── llm_interaction_spec.yaml   ← LLM 交互规范（唯一真相来源）
│   ├── collage_prompt_spec.py      ← 拼图规范加载器
│   ├── collage_prompt_spec.yaml    ← 拼图规范（唯一真相来源）
│   ├── llm_service.py              ← LLM API 封装
│   ├── image_gen_service.py        ← 图像生成 API 封装
│   ├── chat_service.py             ← 对话服务
│   └── rag_service.py              ← 知识库检索
├── api/
│   └── ppt_maker/                  ← PPT 制作 Feature API (v1)
├── skills/
│   └── ppt_maker_v2/               ← PPT 制作 Skill (v2, 对话驱动)
└── routes/                         ← 旧版路由
```

### v1 与 v2 的关系

- **v1** (`api/ppt_maker/`)：前端页面驱动，REST API，`DEVELOPMENT_CONTRACT.md` 定义契约
- **v2** (`skills/ppt_maker_v2/`)：对话驱动，skill 框架
- **共享模块**：两个版本通过 `collage_prompt_spec.py` 和 `llm_interaction.py` 共享规则

---

## 五、开发规范

### 4.1 修改规则流程

1. 修改对应的规范 YAML 文件
2. 如果改了字段名/接口，同步更新 `DEVELOPMENT_CONTRACT.md`
3. 写代码引用规范文件中的规则，不要复制粘贴
4. 重启后端，验证

### 4.2 Prompt 编写原则

- prompt 规则放 YAML，不放代码
- 约束用醒目格式（`━━━` 框、`MANDATORY`、`VIOLATION MEANS REGENERATION`）
- 给大模型的指令要具体：`Slide 1 = Slide 7 = Slide N in dimensions` 比 `统一尺寸` 有效
- 去掉冗余信息：传给生图模型的是**内容**，不是 LLM 臆想的**布局指令**

### 4.3 代码审查检查点

- [ ] 新 LLM 调用用了 `execute_with_quality_gate()` 吗？
- [ ] 新图像生成用了 `build_collage_prompt()` + `validate_output()` 吗？
- [ ] 有没有硬编码的 prompt 规则？（有 = 不合格）
- [ ] 质量检查的 `fail_feedback` 是否具体、可执行？
- [ ] `max_retries` 设置合理吗？

---

## 六、版本记录

| 日期 | 变更 |
|------|------|
| 2026-07-16 | 初始版本：LLM 交互标准范式、单一真相来源原则、项目架构规范 |
