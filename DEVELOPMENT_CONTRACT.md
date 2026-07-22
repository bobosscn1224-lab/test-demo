# PPT 制作平台 — 开发契约

> 前后端接口、字段名、状态机、数据格式的单一真相来源。
> 所有开发必须严格遵循本文档，改动先更新文档。

---

## 一、通用约定

### 1.1 API 基础

| 项 | 值 |
|---|-----|
| 前端 base | `/api`（api.ts 自动加前缀） |
| 后端路由 | `/api/v1/ppt-maker/` |
| 本地后端端口 | `8001`（配置、代理和启动脚本统一） |
| 认证 | 无需认证（同其他 Feature API） |

### 1.2 字段名规范

**前后端字段名必须完全一致。** 以下是所有字段的对照表：

| 前端变量 | 后端字段 | 类型 | 说明 |
|---------|---------|------|------|
| `name` | `name` | `string` | 项目名称 |
| `formScenario` | `purpose` | `string` | 应用场景（英文 key 存储，中文 label 展示） |
| `formAudience` | `audience` | `string` | 目标受众 |
| `formScale` | `scale` | `string` | 规模 |
| `formStyles` | `styles` | `string[]` | 视觉风格 |
| `formMessages` | `key_message` | `string` | 关键信息 |
| `formNarrativeStyle` | `narrative_style` | `string` | COSTAR 叙事风格 |
| `formNarrativeFramework` | `narrative_framework` | `string` | COSTAR 叙事框架 |
| `formObjective` | `objective` | `string` | 汇报目标 |
| `formTone` | `tone` | `string` | 表达语调 |
| `_imageBackend` | `image_backend` | `string` | 拼图与逐页图使用的生图后端 |
| `outlineMode` | `outline_mode` | `string` | `conservative` 或 `enhanced`，必须可恢复 |
| `pastedText` | `content_text` | `string` | 粘贴的文本内容 |
| `contentFiles` | `content_files` | `any[]` | 上传的文件（`{path, name}` 对象或字符串） |
| `outlinePages` | `outline_pages` | `OutlinePage[]` | 结构化大纲页 |
| `collages` | `collages` | `Collage[]` | 已生成的风格拼图；`status` 仅为前端运行态 |
| — | `collage_run_id` | `string` | 当前 A/B/C 完整批次标识；三张必须相同 |
| — | `collage_quality_status` | `string` | 当前完整批次质量状态；`invalid*` 批次不得展示或选择 |
| — | `collage_visual_directions` | `Record<"A"|"B"|"C", string>` | 当前批次的三个整套视觉方向 |
| `pageImages` | `page_images` | `PageItem[]` | 已生成的逐页图 |

`feishuUrls`、`useKnowledgeBase` 是前端素材收集状态，不属于 `Project` 持久化字段；提交时转换为 `feishu_ref`、`content_text` 或 `content_files`。

### 1.3 文件与标识符边界

- `project_id` 必须是后端生成的 8 位小写十六进制字符串。
- 上传接口不得直接使用客户端路径；文件名必须取 basename，并由服务端生成唯一前缀。
- 下载只能访问 `PUBLIC_DIR` 内的真实文件，目录归属必须用解析后的路径判断。
- 非法项目 ID 返回 404；目录逃逸下载返回 400。

### 1.4 标签映射（中英文对照）

**前端显示中文，后端存储英文 key。** 映射表在前端 `utils.ts` 的 `LABEL_MAP` 和后端 `models.py` 的 `PURPOSE_MAP`/`AUDIENCE_MAP`/`SCALE_MAP`/`STYLE_MAP` 中维护，**两边必须同步**。

```
purpose:   业务汇报→business_report  项目方案→project_proposal  产品宣讲→product_launch
           培训辅导→training  复盘总结→review  故事路演→story_pitch  其他→other

audience:  老板管理层→executives  客户合作方→clients  一线团队→team  投资人→investors  混合→mixed

scale:     精简8-12页→compact_8_12  标准15-20页→standard_15_20  完整25-35页→full_25_35

style:     专业严谨→professional  科技感→tech  简约商务→minimal  创意活泼→creative  高端大气→bold
```

### 1.5 持久化规则

| 操作 | 是否持久化 |
|------|:---:|
| 创建项目 | ✅ `POST /projects/` |
| 提交素材 | ✅ `POST /projects/{id}/content/` |
| 生成大纲 | ✅ `POST /projects/{id}/outline/` |
| 点击「💾 暂存」 | ✅ `PUT /projects/{id}/outline/` |
| 点击「✅ 确认大纲」 | ✅ `PUT /projects/{id}/outline/` + status→outline_confirmed |
| 点击「上一步」/切换页面不保存 | ❌ 丢弃 |
| 编辑字段但未点暂存 | ❌ 丢弃 |
| 点「重新生成」 | ✅ 新结果自动存（覆盖旧大纲，回到预览模式） |

### 1.6 付费模型交互契约

所有文本、视觉、图像和嵌入模型调用都必须在共享服务边界执行质量门禁，业务接口不得直接调用供应商 SDK。

| 阶段 | 强制行为 |
|------|----------|
| SPEC | 按 `interaction_name` 从持久化 YAML 加载模型参数、输入要求、输出规则、重试模板 |
| INPUT | 拒绝空输入、缺失上下文和超限输入；把规范中的明确要求追加到模型指令 |
| CALL | 使用规范指定的模型、温度、token 上限和超时；记录供应商、模型与 token usage |
| CHECK | 文本使用声明式校验；图片检查可解码性、尺寸、比例、内容质量，并由视觉模型复核主体/页数/顺序/文字；嵌入检查数量、维度和有限数值 |
| RETRY | 失败反馈必须指出具体不合格项；只允许规范定义的有限次数重试 |
| GATE | 未通过全部检查的输出不得写入业务状态、不得流式发送、不得返回给前端；图片只能在 `.gate-*` 临时文件通过验收后原子替换到正式路径 |
| AUDIT | 每次尝试写入脱敏审计记录，包含交互类型、检查结果、重试次数和 token usage，不记录密钥 |

权威规范：文本交互使用 `app/services/llm_interaction_spec.yaml`；拼图 Prompt、通用图片和单页 PPT 图像门禁统一使用 `app/services/collage_prompt_spec.yaml`。

拼图几何采用“生成前固定骨架 + 高置信度检查与无损重排 + 不确定时定向重试”：生图请求必须携带本地生成的等尺寸 16:9 网格参考图；能够可靠识别全部页面边界时，系统可将完整页面以 `contain` 方式放入统一 16:9 单元格并重新检查，不拉伸、不裁掉页面内容；无法可靠分割的无边框/满版设计禁止自动裁切，必须携带实际测量反馈重新生成。Tutujin Gemini 只检查内容、页序、乱码和明显视觉缺陷，不得覆盖像素门禁结论；视觉服务不可用时只能在本地几何已通过后标记人工确认，不得触发重复付费生图。

完整风格方案是原子批次：服务端先选择 A/B/C 三个互斥视觉方向，再固定使用 `tutujin_vip` 和 A/B/C 三个独立凭证槽位并行生成同一 `run_id` 的三张拼图，不把凭证伪装成不同后端，也不自动切换其他生图供应商。每方案最多 2 次付费调用，最多 3 路并发，单次供应商调用上限 300 秒，整批上限 720 秒；数值以 `collage_prompt_spec.yaml:generation_runtime` 为唯一真相来源。只有三张都达到可提交状态时才一次替换 `collages`；任一失败都必须保留上一批完整方案和本批已经通过的暂存结果。

#### 拼图生成进度

`GET /projects/{id}/collages/progress` 返回：

```json
{
  "run_id": "10-char-id",
  "status": "idle|selecting_directions|running|completed|failed|timed_out|cancelled",
  "current_label": "A|B|C|",
  "attempt": 1,
  "completed_labels": ["A"],
  "started_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "elapsed_seconds": 0,
  "message": "正在生成方案 B",
  "error": "",
  "variants": {
    "A": {"status": "generating", "attempt": 1, "elapsed_seconds": 31, "message": "正在生成方案 A", "error": ""},
    "B": {"status": "passed", "attempt": 1, "elapsed_seconds": 28, "message": "方案 B 已通过", "error": ""},
    "C": {"status": "passed_with_manual_review", "attempt": 1, "elapsed_seconds": 29, "message": "结构通过，语义待人工确认", "error": ""}
  }
}
```

前端生成期间每 2 秒轮询。历史 `collages` 只有在 A/B/C 齐全、文件存在、每项 `run_id` 与 `collage_run_id` 一致，且 `collage_quality_status` 不是 `invalid*` 时才可展示和选择。

---

## 二、状态机

```
created ──→ content_added ──→ outline_generated ──→ outline_confirmed
                                                           │
                             ┌─────────────────────────────┘
                             ↓
                    collages_generated ──→ pages_generated ──→ completed
```

### 状态转换条件

| 当前状态 | 可转换到 | 触发动作 |
|---------|---------|---------|
| `created` | `content_added` | 用户提交素材（POST content） |
| `content_added` | `outline_generated` | 生成大纲（POST outline） |
| `outline_generated` | `outline_confirmed` | 确认大纲（PUT outline + status change） |
| `outline_confirmed` | `collages_generated` | 生成缩略图（POST collages） |
| `collages_generated` | `pages_generated` | 生成逐页图（POST pages） |
| `pages_generated` | `completed` | 下载 PPTX 或完成 |

---

## 三、API 接口契约

### 3.1 项目 CRUD

#### `GET /projects/` — 列表
```json
// Response: Project[]
[{ "id": "a1b2c3d4", "name": "项目名", "purpose": "business_report", "status": "created", ... }]
```

#### `POST /projects/` — 创建
```json
// Request
{ "name": "str", "purpose": "str", "audience": "str", "scale": "str",
  "styles": ["str","str","str"], "key_message": "str" }
// Response: Project (status="created")
```

#### `GET /projects/{id}/` — 详情
```json
// Response: Project（完整字段，含 outline_mode、outline_pages、collages、page_images、content_text、content_files、image_backend）
```

#### `PUT /projects/{id}/` — 更新元数据
```json
// Request: ProjectUpdate (部分字段)
// Response: Project
```

#### `DELETE /projects/{id}/` — 删除
```json
// Response: { "success": true, "project_id": "a1b2c3d4" }
```

### 3.2 素材

#### `POST /projects/{id}/content/` — 追加素材
```json
// Request
{ "text": "str", "files": ["path_or_{path,name}_objects"], "feishu_ref": "str" }
// Response: Project (status 变为 content_added)
```

#### `PUT /projects/{id}/content/` — 替换素材（用于删除）
```json
// 同 POST，但是完全替换而非追加
```

### 3.3 大纲

#### `POST /projects/{id}/outline/?mode=conservative|enhanced` — 生成
```json
// Query: mode=conservative (默认) | enhanced
// Response: OutlineResponse
{
  "success": true,
  "project_id": "a1b2c3d4",
  "outline": "原始文本...",
  "pages": [ OutlinePage, ... ],   // ← 前端用这个渲染
  "message": "大纲已生成，共 10 页。"
}
```

#### `PUT /projects/{id}/outline/` — 暂存/确认
```json
// Request: { "outline": "完整大纲文本（由前端从 pages 重建）" }
// Response: OutlineResponse
```

#### OutlinePage 结构
```json
{
  "page_num": 1,
  "title": "封面标题",
  "type": "cover|toc|content|summary",
  "role": "本页在故事中的角色",
  "core_message": "核心信息",
  "points": ["要点1", "要点2", "要点3"],
  "visual_hint": "视觉建议"
}
```

### 3.4 缩略图（已实现）

#### `POST /projects/{id}/collages` — 原子生成三套方案

该请求内部完成视觉方向选择和 A/B/C 生成。成功返回同一 `run_id` 的三张图；失败返回具体方案与门禁原因，项目当前 `collages` 不变。
```json
// Response: CollageGenerateResponse
{
  "success": true,
  "project_id": "a1b2c3d4",
  "collages": [
    { "label": "A", "filename": "ppt_maker_xxx_A.png", "download_url": "/api/skills/download/ppt_maker_xxx_A.png" },
    { "label": "B", "filename": "ppt_maker_xxx_B.png", "download_url": "/api/skills/download/ppt_maker_xxx_B.png" },
    { "label": "C", "filename": "ppt_maker_xxx_C.png", "download_url": "/api/skills/download/ppt_maker_xxx_C.png" }
  ]
}
```

#### `POST /projects/{id}/collages/{label}` — 兼容性生成单套方案

`label` 为 `A|B|C`。响应仍为完整 `CollageGenerateResponse`，用于前端逐套显示进度。

#### `PUT /projects/{id}/collages/{label}` — 按修改意见重生成单套方案

请求体包含 `modifications`，响应为更新后的完整 `CollageGenerateResponse`。

#### `PUT /projects/{id}/collages/select/` — 选择方案
```json
// Request: { "selected_collage": "A|B|C" }
// Response: Project (status→collages_generated)
```

### 3.5 逐页图（已实现）

#### `POST /projects/{id}/pages/` — 生成逐页
```json
// Response: PageGenerateResponse
{ "success": true, "project_id": "a1b2c3d4",
  "pages": [ PageItem, ... ], "total_pages": 10 }
```

#### `PUT /projects/{id}/pages/{page_num}/` — 单页重生成
```json
// Request: { "modifications": "修改意见" }
// Response: PageUpdateResponse
```

#### PageItem 结构
```json
{ "page_num": 1, "title": "封面", "filename": "ppt_maker_xxx_p01.png",
  "download_url": "/api/skills/download/ppt_maker_xxx_p01.png" }
```

---

## 四、前端全局状态（state.ts）

```typescript
// 流程控制
currentStep: number           // 0-6
projectId: string | null      // 当前项目 ID
projects: Project[]           // 项目列表
projectDetail: Project | null // 当前项目详情（GET /projects/{id} 返回）

// 步骤1
formName: string
formScenario: string           // 中文 label
formAudience: string           // 中文 label
formScale: string              // 中文 label
formStyles: string[]           // 中文 labels
formMessages: string

// 步骤2
useKnowledgeBase: boolean      // 默认 true
knowledgeBaseDirs: string[]    // 从 /api/knowledge/config 加载
feishuUrls: string[]
importedFeishuDocs: {url, title}[]
contentFiles: File[]           // 浏览器 File 对象（新上传的）
pastedText: string
activeContentTab: string       // 'upload'|'text'|'feishu'|'knowledge'

// 步骤3
outlineMode: string            // 'conservative'|'enhanced'
outlineSaved: boolean          // 是否已持久化（控制预览/编辑模式）
outlinePages: OutlinePage[]
selectedOutlineIdx: number     // 左侧列表当前选中
```

---

## 五、开发流程（强制）

### 新功能开发顺序

1. **定契约**：在本文档写下 API 路径、请求/响应格式、字段名
2. **后端先跑通**：`curl` 或 Python 脚本验证 API 返回正确数据
3. **前端对接**：按契约写前端，字段名严格对照文档
4. **验收清单**：
   - [ ] API 正常返回
   - [ ] 数据持久化到 JSON 文件
   - [ ] 退出再进来能恢复（resumeProject）
   - [ ] 字段名前后端一致（不出现 undefined/null）
   - [ ] 前端 UI 完整（滚动、响应式、加载态、错误提示）

### 提交前自检

- [ ] 所有用户输入的数据在点击"确认/暂存"后已持久化
- [ ] `resumeProject` 能恢复全部状态到对应步骤
- [ ] 没有硬编码的字段名（全部用本文档定义的常量）
- [ ] LLM prompt 中的约束是硬性的（"必须"），不出现"建议"/"期望"
- [ ] AI 元标记（如 `[AI增强]`）在传给下游（生图）前已过滤
- [ ] `npm run build` 通过（严格 TypeScript，不允许只跑 Vite）
- [ ] 后端全模块导入与核心 pytest 通过
- [ ] 无外部付费调用的 API 冒烟测试通过
- [ ] 模型调用覆盖率扫描通过（无未声明 `interaction_name`、无业务层供应商 SDK 直连）
- [ ] 门禁失败/反馈重试/最终阻断的自动测试通过
- [ ] 使用最小输入完成一次文本、嵌入和已启用图像后端的真实计费冒烟，并记录结果

---

## 六、版本记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-02 | v1.0 | 初始版本，覆盖步骤1-3 |
| 2026-07-16 | v1.1 | 补齐步骤4-5、COSTAR、图像后端、恢复字段、文件边界与验收基线 |
| 2026-07-16 | v1.2 | 增加付费文本、视觉、图像和嵌入模型的强制质量门禁与审计契约 |
