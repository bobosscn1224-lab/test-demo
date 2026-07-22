# PPT 制作平台 — 工作总结

> 日期：2026-07-01 ~ 2026-07-02

---

## 一、做了什么

### 1. 项目系统
- 创建/列表/继续/删除项目，每个项目唯一 8 位 ID
- JSON 文件持久化到 `data/ppt_projects/{id}.json`
- 状态机：`created → content_added → outline_generated → outline_confirmed → collages_generated → pages_generated → completed`

### 2. 步骤① 需求（briefing）
- 项目名、应用场景（7类）、目标受众（5类）、规模（3档，硬性强制页数）、视觉风格（≥3选）、关键信息
- 中文标签前后端自动映射：前端显示中文 → 后端标准化为英文 key 存储

### 3. 步骤② 素材
- 4 个 Tab：📁 文件上传（保留原始文件名+路径）、📝 粘贴文本、🪶 飞书文档（URL查询预览+导入知识库）、📚 本地知识库（开关+目录列表）
- 内容合并：追加提交不覆盖，支持文件+文本混合
- 删除已保存内容：文件逐条删除 + 文本删除

### 4. 步骤③ 大纲
- 左右双帧布局：左侧 224px 页列表 + 右侧详情面板
- 两种生成模式：普通模式（用户素材+知识库） / 增强模式（+AI补充行业知识，标注`[AI增强]`）
- 预览模式：只读 + 黄色横幅 + 单页重新生成
- 暂存 → 编辑模式：白底 + 可编辑字段 + 单页重新生成
- 确认大纲：锁定并进入下一步
- 顶栏「💾 暂存」统一保存全部页面
- 硬性页数约束：根据用户选择的规模强制 LLM 生成指定范围页数

### 5. 后端 API
- `/api/v1/ppt-maker/` 下 7 个模块：models、projects、outline、collage、pages
- 大纲生成自动读取上传文件内容 + RAG 知识库搜索
- AI 增强标记在生图前自动过滤：`_clean_for_image()` 去除 `[AI增强]` `[参考补充]`
- PUT `/projects/{id}/content` 支持完整替换（用于删除文件）

### 6. 基础设施优化
- **生图升级**：新增 Lovart/CatRouter 后端 `gpt-image-2:stable`，自动优先级：Lovart > Agnes > OpenAI > Ruizhi
- **路径统一**：输出目录统一到 `_paths.py` 的 `PUBLIC_DIR`（`d:\数字分身\outputs\`），消除 `backend/outputs/`、`data/outputs/`、`工作周报/输出/` 碎片化
- **会话持久化修复**：路由层先 `restore()` 从 SQLite 恢复再判断 `_sessions`，服务器重启不丢会话
- **中断恢复**：PPT maker 的 collage/pages 生成阶段支持断点续传（"继续"从断点续，"重新生成"清除重做）
- **PPT maker v2**：1200 行单文件 → 11 个模块化文件，14 个 stage → 6 个核心 stage
- **前端文件拆分**：`PptMakerPage.ts` 1418 行 → `ppt-maker/` 目录 14 个模块文件

### 7. 死代码清理
- 删除：`chat_analyzer.py`、`Sidebar.ts`、`MessageBubble.ts`、`chatStore.ts`
- ChatWindow.ts 移除未使用的 `formatMd()` 和 `marked` 导入
- `package.json` 移除 `marked` 依赖

---

## 二、反复出的问题（踩坑记录）

| # | 问题 | 根因 | 教训 |
|---|------|------|------|
| 1 | 创建项目 422 错误 | 前端发 `scenario`/`messages`，后端要 `purpose`/`key_message` | **前后端字段名必须一开始就对齐** |
| 2 | 大纲完全不参考用户素材 | 上传文件只存了路径，后端 `generate_outline` 没读文件内容 | **文件上传 ≠ 内容可读，生成时必须主动 parse 文件** |
| 3 | 退出再进来大纲丢失 | `_parse_outline` 返回的 `pages` 数组没持久化到 JSON | **API 返回的结构化数据也要存盘** |
| 4 | 生成 7 页而非指定的 8-12 页 | LLM prompt 里写了"期望规模"但没有硬性约束 | **用户意图要转化为 LLM 的硬约束（"必须X-Y页"），不是软建议** |
| 5 | 步骤2 提交后回退再进，内容消失 | 前端 `pastedText`/`contentFiles` 变量没从 API 恢复 | **状态同步不能只靠表单输入，`resumeProject` 要加载所有字段** |
| 6 | 预览/编辑模式看不到切换 | `outlineSaved` 初始值逻辑和视觉差异不够强 | **模式切换必须有醒目的视觉反馈（颜色横幅+背景变化）** |
| 7 | 已保存文件显示为 UUID 编码 | `/api/upload` 只存了服务器路径没存原始名 | **上传时同时保留 `path` + `name`** |
| 8 | Tab 切换丢状态（飞书 tab 跳回文件 tab） | `reRender()` 重置了局部 `activeTab` 变量 | **跨渲染周期的状态必须放全局 `state` 对象** |
| 9 | AI 增强标记 `[AI增强]` 会污染生图 | 标记文字直接传给了 collage/pages 生图 prompt | **内容生成要考虑下游消费者，生图前过滤元标记** |
| 10 | 点「添加飞书文档 URL」跳回文件页 | 同上，`reRender()` 导致 tab 状态丢失 | **改用 `state.activeContentTab` 持久化 tab** |
| 11 | 内容上传 500 错误 | `Project` Pydantic 模型 `content_files: list[dict]` 但实际存的是字符串 | **Pydantic 类型不要用 `dict` 限死，文件路径可能是字符串** |
| 12 | 已提交素材后点继续报"至少需要一个素材" | 验证逻辑只看表单输入不看已持久化的内容 | **状态判断要查 JSON，不要只信当前表单动作** |
| 13 | PPT skill v2 确认大纲后跳回普通聊天 | `_sessions` 在服务器重启后清空，路由检查在 DB 恢复之前 | **路由层先 `restore()` 从 DB 恢复再判断** |
| 14 | Lovart 文档说 `api.lovart.info` 但域名不存在 | 文档与实际部署不一致 | **先用 curl 验证 API 可达性再写代码** |
| 15 | 大纲卡片不可滚动、双 cover 页、单列太挤 | 一次性做太多 UI 细节容易漏 | **UI 布局先定骨架（滚动/网格/固定高度），再填内容** |

---

## 三、核心原则（血的教训）

1. **前后端字段名必须一致**——一处不同，整个功能挂掉
2. **LLM 输入要硬约束，不只是软建议**——"期望 8-12 页"不如"必须 8-12 页，不得少不得多"
3. **持久化 = 存盘 + 能恢复**——光存 JSON 不够，`resumeProject` 要加载所有字段恢复完整状态
4. **状态管理要查 JSON，不要信动作**——用户说"之前提交过"，就查 `projectDetail.content_files` 而不是看当前表单有没有输入
5. **暂存不是自动保存**——必须用户显式点「暂存」才持久化，不点就丢弃
6. **内容生成要考虑下游消费**——`[AI增强]` 标记在传给生图模型前必须过滤
7. **文件上传 ≠ 内容可读**——上传只存路径，生成时必须主动 `parse_file_sync` 读内容
8. **Pydantic 模型不要过早限死类型**——`list[dict]` 改 `list`，兼容字符串和对象
9. **跨渲染的状态放全局 state**——局部变量在 `reRender()` 后会重置
10. **API 可用性先验证再写代码**——DNS 解析、HTTP 连通性、认证方式先确认

---

## 四、当前架构

```
frontend/src/components/ppt-maker/     backend/app/api/ppt_maker/
├── index.ts          主入口            ├── __init__.py      路由聚合
├── types.ts          类型定义          ├── models.py        Pydantic 模型
├── state.ts          全局状态          ├── projects.py      项目 CRUD
├── utils.ts          工具函数          ├── outline.py       大纲生成+解析
├── navigation.ts     导航控制          ├── collage.py       3套缩略图
├── project-list.ts   项目列表          └── pages.py         逐页高清图
├── step-bar.ts       步骤指示器
└── steps/
    ├── step1-create.ts    需求表单
    ├── step2-content.ts   素材上传（4 Tab）
    ├── step3-outline.ts   大纲（左右双帧）
    ├── step4-collage.ts   缩略图（待开发）
    ├── step5-pages.ts     逐页图（待开发）
    └── step6-done.ts      完成下载（待开发）
```

### 状态机

```
created → content_added → outline_generated → outline_confirmed
       → collages_generated → pages_generated → completed
```

### 生图链路优先级

```
PPT maker → image_gen.generate()
  ├─ ruizhi-imagegen.exe CLI → RUIZHI_API_KEY 过期
  └─ image_gen_service回退:
       ├─ Lovart/CatRouter: gpt-image-2:stable  ✅ 当前
       ├─ Agnes: agnes-image-2.1-flash
       ├─ OpenAI: DALL-E 3 / gpt-image-2
       └─ Ruizhi: CLI
```

### 路径统一

所有路径从 `app/services/_paths.py` 单一来源导出：
- `PUBLIC_DIR` = `d:\数字分身\outputs\` （下载端点 + 生成文件输出）
- `DATA_DIR` = `d:\数字分身\data\`
- `OUTPUTS_DIR` = `d:\数字分身\data\outputs\`
- `WEEKLY_REPORT_DIR` = `d:\数字分身\工作周报\输出\`

---

## 五、下一步计划

### 步骤 4-6（待开发）
- **步骤④ 缩略图**：三套方案（A/B/C）生成 + 预览 + 选择。后端已有骨架代码
- **步骤⑤ 逐页图**：逐页高清 16:9 生成 + 预览 + 单页重生成。后端已有骨架代码
- **步骤⑥ 完成**：PPTX 下载（复用现有 `/api/v1/pptx/convert-async`）

### 开发前准备（吸取教训）
1. **先定接口契约**：前后端字段名、请求/响应格式、状态流转，白纸黑字写清楚
2. **先验证后写码**：每个后端 API 用 curl/Python 验证通过再写前端对接
3. **一次只做一个功能**：步骤4→步骤5→步骤6，不跳步不并行
4. **做完一步验收一步**：前端 UI + 后端 API + 持久化 + 断点续传，四项全通了再下一步

### 现有功能优化
- 飞书文档 tab：目前只有预览+导入到知识库，后续可加入从知识库直接选取已导入文档
- 知识库 tab：支持用户从已索引目录中选择特定目录限定搜索范围
- 步骤① 需求表单：可保存为模板，下次创建项目时快速加载
