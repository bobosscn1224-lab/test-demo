# 专业模式（Pro Mode）— 设计与功能文档

> 最后更新：2026-07-22 | 总代码量：~2300 行（后端 943 行 + 前端 1373 行）

---

## 一、概述

专业模式是数字分身系统中短视频生成的高级工作流，核心理念是：

```
剧本驱动 → AI 自动提取资源 → 批量生图确定视觉 → 逐镜分镜 → 导演统筹 → 高质量逐镜生成
```

**与简易模式的关系**：简易模式（VideoGenPage）适合快速单段视频生成；专业模式适合多镜头、有叙事结构的短剧制作。两者共享同一套 Seedance 视频生成 + 素材管理 + LLM 调用基础设施，互不干扰。

---

## 二、设计原则

### 0. 需求驱动开发流程（继承项目宪法）

```
需求 → 分析 → 设计 → 评审 → 实现 → 验证
```

所有改动先更新规范文档，再写代码。复用已有设计模式，不重复造轮子。

### 1. 剧本先行原则

**剧本是整个工作流的起点**。用户不需要预先定义角色、场景、道具——AI 从剧本中自动提取一切。这避免了"先有鸡还是先有蛋"的问题：用户不知道需要什么角色，直到看到剧本分析结果。

### 2. 资源确定原则

在分镜之前，必须确定所有视觉资源（角色形象、场景空间、关键道具）。这样分镜中的每个镜头都能引用具体的视觉锚点，保证 5 个镜头的角色长相、场景氛围、打光风格完全一致。

### 3. 一致性优先原则

> "一致性不是一个选项，是质量标准。"

每个镜头的 Seedance prompt 末尾都附带 CONSISTENCY RULES 段落，明确声明：
- 所有镜头中的人物外观必须完全一致
- 所有镜头使用相同的光照质量和色彩分级
- 所有镜头保持统一的画面风格

这解决了 AI 视频生成中最大的痛点——同一角色在不同镜头中长得不一样。

### 4. 持久化优先原则

项目数据（剧本、角色、场景、分镜、导演配置、当前步骤）全部持久化到 `backend/data/pro_mode/projects.json`。每完成一步自动保存进度到后端，刷新页面、关闭浏览器都不会丢失。用户可以从项目仪表盘恢复任何项目到之前做到的步骤。

### 5. 质量门控原则（继承项目宪法）

每个步骤的 AI 输出都经过：
- **结构化校验**：解析 JSON 响应，确保字段完整
- **重试机制**：解析失败自动重试（最多 2 次）
- **错误反馈**：失败时返回具体错误信息而非崩溃

---

## 三、工作流架构

```
┌────────────────────────────────────────────────────────────────────┐
│                    PRO MODE WORKFLOW                                │
│                                                                    │
│  Step 1          Step 2          Step 3          Step 4    Step 5  │
│  ┌────────┐     ┌────────┐     ┌────────┐     ┌──────┐  ┌──────┐  │
│  │ 剧本   │ ──→ │ 资源   │ ──→ │ 分镜   │ ──→ │ 导演 │→│ 逐镜 │  │
│  │ 导入   │     │ 生成   │     │ 计划   │     │ 台   │  │ 生成 │  │
│  └────────┘     └────────┘     └────────┘     └──────┘  └──────┘  │
│       │              │              │              │         │     │
│  AI 提取：     AI/手动生图：  AI 拆解：    AI 建议：  Seedance │
│  · 角色列表    · 角色定妆照   · 逐镜描述    · 节奏     · 逐镜    │
│  · 场景列表    · 场景空间图   · 角色关联    · 表演风格 · 生成    │
│  · 关键道具    · 道具图       · 场景关联    · 色调     · 轮询    │
│                              · 镜头运动    · 转场     · 可重试  │
│                              · 对白/情绪              │         │
│                                                                    │
│  输出：        输出：        输出：        输出：     输出：      │
│  Project       视觉资源      分镜表       导演方案   5段视频     │
│  (JSON)        (图片+        (Shot×N)    (Config)   +质检标记   │
│                asset://ID)                                     │
└────────────────────────────────────────────────────────────────────┘
```

### 步骤详解

#### Step 1 — 剧本导入（ScriptImport.ts）

| AI 做什么 | 人做什么 |
|-----------|---------|
| 解析剧本全文，提取角色（含外貌描述 + 生图 prompt）、场景（含空间描述 + 生图 prompt）、关键道具 | 粘贴剧本，确认 AI 提取结果，不满意可修改剧本重新分析 |

**输出**：
- 角色：名称、外貌描述（面部/发型/体型/服装）、性格标签、英文生图 prompt
- 场景：名称、空间描述、光照条件、时间段、英文生图 prompt
- 关键道具：仅提取反复出现/推动情节的道具（0-3 个），普通物品交给 Seedance 自由发挥
- 项目元信息：标题、类型标签、一句话概述

**设计要点**：道具宁少勿多。一次性出现的普通物品（水杯、书本等）不预设图片，让视频模型根据场景上下文自行生成，避免过度约束。

#### Step 2 — 资源生成（ResourceGen.ts）

| AI 做什么 | 人做什么 |
|-----------|---------|
| 调用 apiyi 图片生成服务为每个资源生图；真人角色走 icover API 拿 asset:// ID | 确认/重新生成/从素材库替换；可一键生成全部或逐个生成 |

**三种资源来源**：
1. **AI 生图**（🎨 生成）：用 AI 分析时提取的英文 prompt 调用图片生成 API
2. **素材库选择**（📂 素材库）：从已上传的素材中直接选取
3. **定妆照生成**（🎭 生成人物定妆照）：白色背景、全身、多人并肩站立、面部清晰——专门用于 Seedance 角色锚定

**asset:// ID 策略**：
- 真人角色（数字真人分类）：走 icover API → 获得 `asset://` ID → 嵌入 Seedance prompt → 避免人脸审核策略拦截
- 场景/道具：本地存储，不需要 asset:// ID

#### Step 3 — 分镜计划（StoryboardPlanner.ts）

| AI 做什么 | 人做什么 |
|-----------|---------|
| 根据剧本 + 已确定资源，拆解为逐镜分镜表，每个镜头自动关联角色/场景/道具 ID | 查看/编辑分镜（描述、角色、场景、镜头运动、时长、对白、情绪），增删镜头 |

**分镜表结构**（每行一个 Shot）：
| 字段 | 说明 | 示例 |
|------|------|------|
| shot_number | 镜头编号 | 1 |
| description | 画面描述（中文） | 课桌上的糖，女生戳男生后背递橘子糖 |
| character_ids | 关联角色 ID | `[char-xxx, char-yyy]` |
| scene_id | 关联场景 ID | `scene-xxx` |
| camera | 镜头运动（英文） | close-up gentle shake on hand passing candy |
| duration | 时长（秒） | 4 |
| dialogue | 对白 | 女生软声："给你，橘子味的。" |
| mood | 情绪关键词 | 软萌甜喜 |

**一致性圣经（Consistency Bible）**：
分镜生成时自动创建一致性圣经——将所有角色锚定描述、场景描述、风格规则整理为一段共享文本，附加到每个镜头的 prompt 末尾。

#### Step 4 — 导演台（DirectorDesk.ts）

| AI 做什么 | 人做什么 |
|-----------|---------|
| 综合分析角色/场景/分镜，建议节奏、表演风格、色调、转场方案 | 查看 AI 建议，确认即可 |

**四项导演决策**：
- **节奏**：快节奏 / 慢节奏 / 张弛交替
- **表演风格**：自然 / 夸张 / 克制
- **色调方案**：暖色调 / 冷色调 / 高对比 / 柔和
- **转场风格**：硬切 / 淡入淡出 / 匹配剪辑

这些决策会直接嵌入每个镜头的 CONSISTENCY RULES 中，确保所有镜头风格统一。

#### Step 5 — 逐镜生成（ShotGenerator.ts）

| AI 做什么 | 人做什么 |
|-----------|---------|
| 为每个镜头自动构建高质量 Seedance prompt → 提交任务 → 自动轮询 | 逐个点击生成，查看 prompt 预览，失败可重试，可复制 prompt 调试 |

**Prompt 组装引擎**（`_build_shot_prompt()`）：
```
CHARACTERS:
@女生: 十六七岁，齐肩短发，空气刘海，皮肤白皙...身穿蓝白校服。(asset://xxx)
@男生: 十七岁左右，干净利落的短发，单眼皮，眼神温和...(asset://xxx)

SCENE:
@早读课教室: 明亮的教室，清晨阳光从窗户斜射进来...
Time: 清晨

ACTION:
课桌上的糖，女生偷偷戳男生后背递橘子糖
[Camera: close-up gentle shake on hand passing candy]
[Dialogue: 女生软声：给你，橘子味的。]

MOOD: 软萌甜喜

CONSISTENCY:
@女生: ...（完整锚定描述）
@男生: ...（完整锚定描述）
@早读课教室: ... | Time: 清晨
CONSISTENCY RULES: All shots maintain identical character appearance,
same lighting quality, same color grading, same film stock look
throughout the entire sequence.
```

**关键设计**：
- **@ 角色锚定**：遵循 Seedance prompt 最佳实践，用 `@角色名` 引用已锚定的人物
- **asset:// ID 注入**：真人角色的 asset:// ID 自动附加到角色描述后，帮助 Seedance 人脸过审
- **一致性段落**：每个 prompt 末尾的 CONSISTENCY RULES 确保跨镜头的一致性
- **可复制 prompt**：每个镜头可一键复制完整 prompt 用于手动调试

---

## 四、数据模型

### Project（项目）

```typescript
interface Project {
  id: string;                    // "proj-xxxx"
  title: string;                 // AI 推断的标题
  genre: string;                 // 类型标签
  summary: string;               // 一句话概述
  script: string;                // 原始剧本全文
  characters: ExtractedCharacter[];
  scenes: ExtractedScene[];
  props: ExtractedProp[];
  shots: Shot[];
  director_config: DirectorConfig | null;
  current_step: number;          // 1-5，持久化进度
  created_at: string;
  updated_at: string;
}
```

### ExtractedCharacter（角色）

```typescript
interface ExtractedCharacter {
  id: string;             // "char-xxxx"
  name: string;           // 角色名
  description: string;    // 中文外貌描述
  traits: string[];       // 性格标签
  image_prompt: string;   // 英文生图 prompt
  generated_image_url: string;  // 生成/选取的图片 URL
  asset_id: string;       // icover asset:// ID（真人角色）
  status: 'pending' | 'generating' | 'done' | 'failed';
}
```

### ExtractedScene（场景）

```typescript
interface ExtractedScene {
  id: string;
  name: string;
  description: string;     // 空间描述
  time_of_day: string;     // 白天/夜晚/黄昏/清晨
  image_prompt: string;    // 英文生图 prompt
  generated_image_url: string;
  asset_id: string;
  status: 'pending' | 'generating' | 'done' | 'failed';
}
```

### Shot（分镜）

```typescript
interface Shot {
  shot_number: number;
  description: string;      // 画面描述
  character_ids: string[];  // 关联角色 ID
  scene_id: string;         // 关联场景 ID
  prop_ids: string[];       // 关联道具 ID
  camera: string;           // 镜头运动（英文）
  duration: number;         // 4-15 秒
  dialogue: string;         // 对白
  mood: string;             // 情绪关键词
}
```

### DirectorConfig（导演配置）

```typescript
interface DirectorConfig {
  pace: string;              // 节奏
  performance_style: string; // 表演风格
  color_tone: string;        // 色调
  transitions: string;       // 转场
  overall_note: string;      // 导演思路概述
}
```

---

## 五、API 参考

所有端点挂载在 `/api/v1/pro-mode/*`，共 13 个端点：

### 剧本分析
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/script/analyze` | AI 分析剧本，提取角色/场景/道具，创建项目 |

### 资源生成
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/resource/generate` | 为单个资源生图 |
| POST | `/resource/generate-all` | 批量生成所有未完成的资源图 |

### 分镜
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/storyboard/create` | AI 拆解分镜（含一致性圣经） |
| PUT | `/storyboard/{project_id}` | 手动调整分镜表 |

### 导演
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/director/suggest` | AI 生成导演建议 |

### 视频生成
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/generate/shot-prompt/{project_id}/{shot_number}` | 预览镜头的完整 Seedance prompt |
| POST | `/generate/shot` | 提交单个镜头到 Seedance（含 asset:// 引用） |
| POST | `/generate/portrait` | 生成人物定妆照（白色背景全身合照，走 icover） |

### 项目管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/project/list` | 列出所有项目（含当前步骤） |
| GET | `/project/{project_id}` | 获取项目完整详情 |
| PATCH | `/project/{project_id}/step` | 更新项目当前步骤 |
| DELETE | `/project/{project_id}` | 删除项目 |

---

## 六、技术架构

### 前端

```
frontend/src/components/pro-mode/
├── index.ts              # 主入口：项目列表 ↔ 工作流 双视图切换
├── state.ts              # 集中状态管理（当前项目、步骤、视图模式）
├── types.ts              # TypeScript 类型定义
├── ProjectList.ts        # 项目仪表盘（入口页面）
├── ScriptImport.ts       # Step 1：剧本导入
├── ResourceGen.ts        # Step 2：资源生成（AI 生图 + 素材库选择 + 定妆照）
├── StoryboardPlanner.ts  # Step 3：分镜计划
├── DirectorDesk.ts       # Step 4：导演台
└── ShotGenerator.ts      # Step 5：逐镜生成
```

**技术栈**：纯原生 TypeScript + DOM 操作 + 内联 CSS，无框架依赖。与项目其他页面风格一致。

**状态管理**：模块级闭包变量 + `state.ts` 集中管理。项目切换通过 `setProject()` / `getProject()` 共享全局状态。

**视图模式**：
- `list`：项目仪表盘（默认入口）
- `workflow`：5 步工作流（点击项目卡片进入）

### 后端

```
backend/app/api/pro_mode.py    # 独立路由文件，943 行
backend/data/pro_mode/
└── projects.json              # 所有项目数据持久化（JSON）
```

**复用服务**（零重复实现）：
| 功能 | 复用模块 |
|------|---------|
| LLM 调用 | `llm_service._chat_raw()` |
| 视频生成 | `seedance_service.create_task()` |
| 图片生成 | `ImageGenerationService.text_to_image()` |
| 素材管理 | `asset_library_service` |
| JSON 持久化 | `json_store.atomic_write_json()` |
| 前端 HTTP | `apiGet()` / `apiPost()` / `apiPut()` / `apiPatch()` / `apiDelete()` |

**Prompt 设计**：
- 所有 AI 分析 prompt 使用**结构化 JSON 输出格式**，`_ai_analyze()` 自动处理 JSON 提取、解析和重试
- 图片生图使用 apiyi 后端（与 Seedance 视频生成同源）
- 定妆照走 icover API 获取 `asset:// ID`

### 注册方式

专业模式通过标准注册机制集成到系统：

```typescript
// frontend/src/app.ts
PAGE_REGISTRY['pro-mode'] = renderProModePage;

// frontend/src/components/TopNav.ts
{ page: 'pro-mode', label: '专业模式', icon: '🎥' }

// backend/app/api/__init__.py
from app.api.pro_mode import router as pro_mode_router
feature_router.include_router(pro_mode_router)
```

简易模式（VideoGenPage）左上方有"🎥 专业模式"入口按钮。

---

## 七、已知限制 & 待改进

### 当前限制

1. **Seedance 时长限制**：单段视频 4-15 秒，不支持更短（如用户希望的 3 秒镜头）
2. **图片生图后端**：固定使用 apiyi，暂不支持用户切换后端
3. **分镜编辑器**：纯文本编辑，不支持拖拽排序
4. **批量生成**：需要手动逐个点击生成，暂无"全部生成"一键操作
5. **素材库联动**：从素材库选图时需要先切换到素材页上传，再回到专业模式选择（已支持直接生图作为替代方案）

### 设计决策记录

| 决策 | 理由 |
|------|------|
| 道具只提取关键道具（0-3 个） | 普通物品交给 Seedance 自由发挥效果更好，预设反而限制模型 |
| 定妆照使用白色背景全身照 | 白色背景让 Seedance 更容易将人物从背景中分离，合成到不同场景 |
| 一致性圣经附加到每个 prompt | 跨镜头一致性是 AI 视频生成的最大痛点，需要在每个 prompt 中反复强调 |
| 使用 `@角色名` 而非 "image N" | Seedance 对中文 @ 锚定的响应优于数字索引 |

---

## 八、版本记录

| 日期 | 变更 |
|------|------|
| 2026-07-21 | 初始实现：5 步工作流 + 项目仪表盘 + 持久化 + Prompt 组装引擎 |
| 2026-07-22 | 修正工作流顺序（剧本先行→资源后定）；添加一致性圣经；支持素材库选择；添加定妆照生成；道具策略优化（只提取关键道具） |

---

## 附录 A：快速开始

1. 进入「🎥 专业模式」→ 看到项目仪表盘
2. 点击「📝 + 新建短剧项目」→ 粘贴剧本 → AI 分析
3. 确认角色/场景/道具 → 生成定妆照或逐个生图
4. AI 拆解分镜 → 手动调整
5. AI 导演建议 → 确认
6. 逐个镜头生成 → 轮询查看结果

每个步骤的进度自动保存，随时可以关闭浏览器，下次从仪表盘恢复。
