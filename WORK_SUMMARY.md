# 数字分身系统 — 工作总结

> 日期：2026-06-30 ~ 2026-07-01

---

## 一、已完成的工作

### 1. 技能系统全面审计与修复（9项）

| # | 修复项 | 说明 |
|---|--------|------|
| 1 | `image_gen` | 退出词检测改 `_is_exit()` 方法；prompt 提取改为仅从触发词开头提取不误触 |
| 2 | `base.py` | 新增 `execute_stream`、`match_score`、`on_startup/on_shutdown`、`extract_text_from_llm_response`、`cleanup_sessions` |
| 3 | 飞书触发冲突 | `doc_reader` 移除 8 个妙记触发词，URL 检测委托给 `minutes_reader` |
| 4 | 飞书 Token 共享 | 新建 `feishu_token_manager.py`，两个 feishu 技能统一使用 |
| 5 | LLM 文本解析 | 提取到 `BaseSkill.extract_text_from_llm_response()`，消除重复代码 |
| 6 | `chat_analyzer` | 从技能注册表移除空壳，`chat_service` 已直接处理用户画像 |
| 7 | 会话持久化 | `ppt_maker`、`image_gen` 加入 `SkillSessionHelper`，重启不丢进度 |
| 8 | `weekly_report` 拆分 | 1260行 → `handler.py`(350行) + `constants.py` + `date_utils.py` + `excel_ops.py` + `llm_ops.py` |
| 9 | `ppt_maker` 拆分 | 提取 `visual_systems.py`，去除 ~300 行硬编码 Prompt |
| 10 | 会话清理 | 新建 `session_cleanup.py`，24h TTL，支持定时后台任务 |
| 11 | 技能路由优化 | `find_skill()` 改用 `match_score` 评分制，注册顺序不再决定一切 |

### 2. 前端架构重构

- 左右结构 → **上下结构**（TopNav 顶部导航 + 全宽内容区）
- 导航从 4 项扩展为 **6 项**：对话 / 知识库 / 周报 / 图片 / PPT / 技能
- Chat 页面内嵌 **可折叠 SessionPanel**（替代旧 Sidebar）
- 技能中心重写，显示全部 5 个已注册技能
- 新建 `ReportPage.ts`、`ImageGenPage.ts` Feature 页面
- 重启服务器按钮移至 TopNav 右侧

### 3. 后端 Feature API 解耦

```
backend/app/api/
├── reports.py    # 周报 CRUD + 自动填报 + 完善 + 预览 + 草稿存取
├── images.py     # 图片生成（ratio 预设、多后端）
└── pptx.py       # PPT 转换（批量/异步）
```

全部挂载在 `/api/v1/` 下，与旧 `/api/` 路由并行运行。

### 4. 周报功能深度优化

**数据持久化**：
- `report_store.py`：JSON 持久化周报记录（替代文件系统扫描）
- `activity_store.py`：JSON 持久化草稿活动数据
- `llm_logger.py`：每次 LLM 交互记录输入输出到 `data/llm_logs/`

**前端交互**：
- 三视图：列表（历史记录+删除） → 详情（预览） → 创建（输入+生成）
- 结构化活动卡片：时段 + 开始-结束时间 + 活动 + 完成情况，可增删改
- 自动填报：LLM 提取用户输入 → 程序裁切时间 → 填入卡片
- 完善 ✨：空白行智能填充（参考模板历史数据）
- 校验 🔍：自动修复时间冲突/倒置/重叠/超界
- 模板自动选择：上一周报告或手动指定

**Excel 生成**：
- `report_builder.py`：从结构化活动数据**动态建表**（非填空模式）
- LLM 只写总结，不填 D/E 列
- 时间强制裁剪 9:00-18:00，超出部分清空

### 5. 图片生成 Feature

- 独立页面：Prompt 输入 + 比例选择 + 生成按钮 + 预览 + 历史
- API：`POST /api/v1/images/generate`，支持 ratio 预设（1:1/16:9/9:16）
- 后端：Agnes/OpenAI/RuiZhi 三后端自动切换

### 6. PPT 转换 Feature

- `POST /api/v1/pptx/convert`：上传图片 → layout/batch 模式 → 下载 PPTX
- `POST /api/v1/pptx/convert-async`：异步批量 + 轮询进度

---

## 二、反复出问题的地方

| 问题 | 根因 | 教训 |
|------|------|------|
| **服务器跑旧代码** | 多个 uvicorn 进程堆积在 8011 端口，`--reload` 不生效 | 每次改代码必须手动杀进程 + 清 `__pycache__` |
| **前端缓存旧 JS** | 浏览器缓存 + Vite 未热更新 | 改完前端要 `Ctrl+Shift+R` 硬刷新 |
| **LLM 返回泛词/编造** | 提示词约束不够，模型发散 | LLM 只做提取，不做判断，程序兜底 |
| **空白行被删除** | 前端 `filter(a => a.activity)` 把空行滤掉了 | 始终传完整结构，不筛选 |
| **日期字段名不匹配** | 改为 `time_start/time_end` 后生成按钮未同步 | 改 model 必须同步所有引用 |
| **文件路径不一致** | 多个输出目录（`outputs/`、`data/outputs/`、`工作周报/输出/`） | 统一路径管理 |
| **周报记录丢失** | 文件系统扫描不靠谱 | JSON store 做唯一真相来源 |
| **f-string 花括号冲突** | JSON 示例中的 `{}` 被 f-string 当成占位符 | 大段 JSON 用 `.format()` 或 `{{}}` 转义 |
| **竞态条件** | `loadCreateForm` 异步完成后覆盖用户手动选择的日期 | 先检查 `!s.value` 再自动设值 |
| **事件重复绑定** | `buildDayInputs` 每次切换日期叠加新的事件监听器 | 先 `removeEventListener` 再 `addEventListener` |

---

## 三、核心原则（血的教训）

1. **LLM 只提取，程序做判断** — 不靠提示词约束模型，靠代码裁剪校验
2. **JSON 持久化一切** — 每次 LLM 交互前后都存盘（draft → LLM → draft），不依赖内存
3. **结构化数据流** — 前端活动数组 → JSON → 后端 → Pydantic 校验 → JSON → Excel
4. **不改用户内容** — 用户输入的第一优先级，LLM 补充的只能填空白行
5. **先存再调** — 调 LLM 前先 `draft_save()`，即使 LLM 挂了数据也不丢
6. **程序兜底** — LLM 返回不符合预期时，程序自动裁剪/补全/替换，不抛给用户

---

## 四、当前架构

```
┌──────────────────────────────────────────────────────────┐
│  🏠  💬对话 │ 📚知识库 │ 📊周报 │ 🎨图片 │ 📽PPT │ ⚡技能 │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Frontend (6 panels)                                     │
│  ┌──────────┬──────────┬──────────┬──────────────────┐  │
│  │ Chat     │ Knowledge│ Report   │ ImageGen/PPTX    │  │
│  │(Session  │(RAG/     │(list→    │(Feature pages)   │  │
│  │ Panel)   │ Feishu)  │ detail→  │                  │  │
│  │          │          │ create)  │                  │  │
│  └──────────┴──────────┴──────────┴──────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  Backend API                                             │
│  🆕 /api/v1/reports/*   ← 周报 Feature                  │
│  🆕 /api/v1/images/*    ← 图片 Feature                  │
│  🆕 /api/v1/pptx/*      ← PPT 转换 Feature              │
│  📦 /api/chat/*         ← 对话（SSE stream）            │
│  📦 /api/knowledge/*    ← 知识库                        │
│  📦 /api/skills/*       ← 技能中心                      │
├──────────────────────────────────────────────────────────┤
│  Services                                                │
│  report_store / activity_store / llm_logger (JSON 持久化) │
│  report_builder (动态建 Excel)                            │
│  feishu_token_manager (共享 Token)                        │
│  chat_service / rag_service / image_gen_service           │
├──────────────────────────────────────────────────────────┤
│  Legacy Skills (保持不变)                                 │
│  ppt_maker / feishu_doc_reader / feishu_minutes_reader   │
└──────────────────────────────────────────────────────────┘
```

---

## 五、下一步计划

1. **周报**：完善功能用模板历史数据填空白行；Excel 预览直接显示活动数据
2. **图片生成**：前端页面美化 + 历史记录
3. **PPT 转换**：Feature API 完善 + 前端页面独立
4. **技能中心**：chat_analyzer 重新实现或彻底移除
5. **系统稳定性**：统一输出目录、加全局错误处理、自动化测试
