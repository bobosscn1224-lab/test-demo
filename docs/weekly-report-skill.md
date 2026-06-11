# 周报生成技能 (Weekly Report Skill)

## 概述

`WeeklyReportSkill` 是数字分身系统的核心技能之一，负责自动生成 MO/SCE 流程管理周报。通过对话式交互收集用户本周工作内容，基于历史周报模板格式，利用 LLM 生成专业的 D 列（本周计划）和 E 列（本周总结）内容，并输出为格式化的 Excel 文件。

## 架构

```
用户输入 → find_skill() → WeeklyReportSkill.execute()
                              │
                              ├── A模式: 逐天引导收集 (_start_guided → _handle_collection × 5)
                              │         └── → _generate_from_collected()
                              │
                              ├── B模式: 一次性收集 (_handle_fast_collect)
                              │         └── → _generate_full()
                              │
                              └── _generate_full()
                                    ├── 1. 复制模板 Sheet
                                    ├── 2. LLM 分批生成 D/E 内容 (Mon-Tue / Wed-Thu / Fri)
                                    ├── 3. 填充空单元格 (_fill_empty_cells)
                                    ├── 4. LLM 生成总结区 (_generate_summary)
                                    └── 5. 保存 Excel
```

## 文件位置

| 文件 | 用途 |
|------|------|
| `backend/app/skills/weekly_report/handler.py` | 核心技能实现 (~1119 行) |
| `backend/app/skills/base.py` | 技能基类 (BaseSkill, SkillContext, SkillResult) |
| `backend/app/skills/__init__.py` | 技能注册与路由 |
| `工作周报/template & history.xlsx` | 周报模板文件（含历史 Sheet） |
| `工作周报/输出/` | 生成的周报输出目录 |

## 触发方式

### 触发词 (`triggers`)
```python
triggers = ["写周报", "周报", "生成周报", "帮我写周报"]
```

### 关键词 (`keywords`)
```python
keywords = ["周报", "weekly", "工作周报", "周工作总结"]
```

### 触发逻辑
用户在聊天中输入含触发词/关键词的消息 → `can_handle()` 返回 `True` → 路由到 `WeeklyReportSkill.execute()`

## 交互流程

### 入口：模式选择

```
用户: "写周报"
↓
分身: "你想怎么聊？A. 一天一天聊  B. 一次性聊完"
```

- 用户回复 **A** → 进入逐天引导模式
- 用户回复 **B** → 进入一次性收集模式
- 消息中带有 `"一天一天"` 等关键词 → 直接进入 A 模式
- 消息中带有 `"一次性"` 等关键词 + 工作详情 → 直接生成

### A 模式：逐天引导

```
周一工作? → 用户输入 → 周二工作? → ... → 周五工作? → 生成周报
```

状态管理通过内存 `_sessions` 字典 (`handler.py:12`)：
```python
_sessions: dict[str, dict] = {
    session_id: {
        "file_path": "...",
        "start_date": "2026-05-25",
        "end_date": "2026-05-29",
        "day_index": 2,           # 当前在周几 (0=周一)
        "collected": {0: "...", 1: "..."},  # 已收集的工作内容
        "last_sheet_content": "..."  # 上周内容参考
    }
}
```

### B 模式：一次性收集

```
用户一次性描述一周工作 → 直接生成周报
```

### 控制命令

| 命令 | 效果 |
|------|------|
| `重新开始` / `重来` / `取消` | 清除当前会话状态 |

## Excel 处理

### Sheet 命名规则
格式：`M.D-M.D`，如 `5.25-5.29`

### Sheet 选择 (`_get_latest_sheet_name`)
- 优先选择匹配 `\d+\.\d+-\d+\.\d+` 正则的 Sheet
- 按开始日期排序，取最新的
- 排除 Sheet1、非日期命名的 Sheet

### Sheet 复制 (`_copy_sheet`)
完整复制模板 Sheet 到新 Sheet，包括：
- 所有单元格值
- 字体、边框、填充、数字格式、对齐方式
- 合并单元格
- 列宽、行高

### 日期处理
- A 列日期由代码直接写入（不经过 LLM），格式 `YYYY-MM-DD`
- 清除旧日期的规则：只清空匹配 `^\d{4}-\d{2}-\d{2}` 的值
- 日期单元格合并按天（`_merge_date_cells`）

### 节假日处理
```python
_HOLIDAYS_2026 = {
    "01-01", "01-02", "01-03",   # 元旦
    "02-16" ~ "02-22",           # 春节
    "04-06", "04-07",            # 清明
    "05-01" ~ "05-05",           # 劳动节
    "06-19" ~ "06-21",           # 端午
    "09-25" ~ "09-27",           # 中秋+国庆
    "10-01" ~ "10-07",           # 国庆
}
```

## LLM 生成策略

### 分批调用

3 次 LLM 调用 + 1 次总结调用：

| 批次 | 行范围 | 说明 |
|------|--------|------|
| Batch 1 | 周一 ~ 周二 | Day 0-1 |
| Batch 2 | 周三 ~ 周四 | Day 2-3 |
| Batch 3 | 周五 | Day 4 |
| Summary | — | B/C 列总结区 |

### LLM 参数
```python
model: "deepseek-v4-pro" (via Anthropic-compatible API)
max_tokens: 4096
temperature: 0.2
timeout: 180s
thinking: {"type": "disabled"}
```

### System Prompt 核心规则
1. **用户输入是唯一依据** — 不编造用户没提到的工作
2. 将口语化描述转为专业流程管理术语
3. B/C 列保持不动，只更新 D 列和 E 列
4. 固定例会自动填入（周一上午部门周例会、周四下午 MO 周例会）
5. 严禁写入：DG 流程、LTC 全链路、CRM 系统建设

### 时间匹配 (`_build_time_hints`)
预处理用户输入，识别时间关键词（如"周四下午"），生成显式的行号映射提示：
```
周四下午工作 → 只能填第21、22行（下午时段）
```

### 知识点检索 (`_search_knowledge_base`)
从 ChromaDB 检索历史周报的日常工作模式，作为生成参考：
```python
await rag_service.search("周工作总结 日常工作 流程优化")
```

## 空单元格填充 (`_fill_empty_cells`)

LLM 生成后，对仍然空的 D/E 单元格用 4 种变体默认值填充，按半天位置循环避免重复：

**上午变体：**
| 位置 | D 列 | E 列 |
|------|------|------|
| 0 | 流程材料更新与日常支持 | 完成流程材料更新及PO日常支持 |
| 1 | 业务流程数据整理与分析 | 完成业务流程数据整理与分析 |
| 2 | 专项工作材料准备 | 完成专项工作材料准备工作 |
| 3 | 跨部门沟通与协作对接 | 完成跨部门沟通与事务对接 |

**下午变体：**
| 位置 | D 列 | E 列 |
|------|------|------|
| 0 | 专项工作跟进与IT需求沟通 | 完成专项工作跟进及IT需求对接 |
| 1 | 流程优化方案讨论与推进 | 完成流程优化方案讨论及推进 |
| 2 | 业务分析与总结报告撰写 | 完成业务分析与总结报告撰写 |
| 3 | L2/L3流程PO支持与答疑 | 完成L2/L3流程PO支持与答疑 |

## 总结区生成 (`_generate_summary`)

### 定位逻辑
`_find_summary_row()` — 从底部向上扫描，找到 A 列含"本周计划"/"本周目标"的行，内容行在标题行 +1。

### 生成内容
| 单元格 | 内容 | 字数 |
|--------|------|------|
| B{row} | 本周主要进展和成果，按模块分点（1.1, 1.2...），7-10 个模块 | 100-200 字 |
| C{row} | 下周计划与目标，按模块分点，5-8 个模块 | 80-150 字 |

### 格式规范
```
1、MO漏斗相关计划：
1.1 跟进试点单执行情况...
1.2 N和T专项推进行动项...
2、SCE流程跟进：
2.1 梳理PO流程计划...
```

## 输出

### 文件命名
```
26年周工作总结和下周计划-ZB-M.D-M.D.xlsx
```

### 输出位置
- `工作周报/输出/` — 主输出目录
- `data/outputs/` — 下载目录（提供 `/api/skills/download/{filename}` 接口）

### 返回格式
```python
SkillResult(
    success=True,
    message="✅ 周报已生成！\n📅 时间范围: ...\n...",
    data={
        "download_url": "/api/skills/download/...",
        "filename": "...",
        "path": "...",
    },
    follow_up_action="download",
)
```

## 关键常量

| 常量 | 值 | 用途 |
|------|-----|------|
| `DAY_NAMES` | `["周一", "周二", "周三", "周四", "周五"]` | 星期名 |
| `MIN_DETAIL_LENGTH` | `10` | 最小工作描述长度 |
| `TEMPLATE_FILE` | `../工作周报/template & history.xlsx` | 模板路径 |
| `OUTPUT_DIR` | `../工作周报/输出` | 输出目录 |
| `EXCLUDED_DIRS` | `{Backup0928, BACKUP1225, ...}` | 扫描排除目录 |

## 依赖

- **openpyxl** — Excel 读写、Sheet 复制、合并单元格
- **LLM (DeepSeek V4 Pro)** — 内容生成
- **ChromaDB + SiliconFlow embeddings** — 知识库检索（RAG）
- **asyncio** — 异步 LLM 调用
- **copy** — 单元格样式深拷贝

## 会话状态

技能使用内存字典 `_sessions` 管理多轮对话状态，key 为 `session_id`。会话在以下情况下清除：
- 用户发送 `重新开始` / `重来` / `取消`
- 周报生成完成
- 服务重启（内存态，不持久化）
