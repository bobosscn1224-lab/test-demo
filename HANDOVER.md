# 短视频生成功能 — 交接文档

> 最后更新：2026-07-21

---

## 一、已完成的功能

### 1. 素材管理 (`📦 素材` 页面)

| 功能 | 状态 | 说明 |
|------|------|------|
| 分类上传（数字真人/场景/道具/其他） | ✅ | 只有数字真人走 icover API 拿 asset:// ID，其他本地存储 |
| 分类筛选 | ✅ | 按分类 Tab 过滤，URL 编码中文参数 |
| 素材卡片缩略图 | ✅ | 40×40 预览图 + 标签 + 分类 + 状态 |
| 删除素材 | ✅ | API 素材从 icover 远程删除，本地素材删文件 |
| 本地文件服务 | ✅ | `/api/v1/assets/local-files/{filename}` 提供静态访问 |
| 素材组管理 | ⚠️ 代码还在 | 前端隐藏了，后端 `/api/v1/assets/groups/*` 接口保留 |

**关键 API：**
```
POST   /api/v1/assets/upload          # 上传（数字真人→icover API，其他→本地）
GET    /api/v1/assets?category=xxx    # 列表（支持分类筛选）
DELETE /api/v1/assets/{id}            # 删除
GET    /api/v1/assets/local-files/*   # 本地文件
GET    /api/v1/assets/categories/list # 分类列表
GET    /api/v1/assets/system/status   # API 连通性检查
```

**关键文件：**
- `backend/app/services/asset_library_service.py` — icover API 封装 + 本地文件管理
- `backend/app/api/assets.py` — REST 路由
- `frontend/src/components/AssetManagePage.ts` — 前端页面

### 2. 短视频生成 (`🎬 视频` 页面)

**三段式布局：** 左(420px 配置) | 中(320px 历史) | 右(flex 预览)

| 功能 | 状态 | 说明 |
|------|------|------|
| 4 种生成模式 | ✅ | 参考图 / 首帧 / 首尾帧 / 纯文本 |
| 3 个模型 | ✅ | Fast(720p) / Standard(1080p) / Mini(720p) |
| 分辨率联动模型 | ✅ | 选 Standard 才显示 1080p |
| 素材选择模态框 | ✅ | 从素材库按分类浏览、勾选，确认后带入视频页 |
| 素材用途标注 | ✅ | 选中后自动分配用途（人物角色/场景/道具/风格），点击标签可切换 |
| 缩略图 Chip | ✅ | 40×40 预览 + @引用 + 用途标签 + ×删除 |
| AI 提示词优化 | ✅ | 自动英文翻译 + 人物锚定 + 保留对白 + 禁止画质词 |
| 提示词模板 | ✅ | 📋 按钮插入结构化模板 |
| 生成历史（中面板） | ✅ | 每条记录含视频 ▶/📥 + 尾帧 🖼/+入库 + 🗑删除 |
| 尾帧入库弹窗 | ✅ | 自定义标签 + 分类选择 + 确定/取消 |
| 预览（右面板） | ✅ | 视频播放 / 尾帧显示 |
| 生成中 Loading | ✅ | 视频区显示 ⏳ 动画 |
| 自动轮询 | ✅ | 10秒间隔，任务完成后自动刷新历史 |
| 返回尾帧 | ✅ | 勾选后 Seedance 返回尾帧 URL |
| 生成音频 | ✅ | 勾选后 Seedance 生成同步音频 |

**关键 API：**
```
POST   /api/v1/video-gen/generate              # 创建任务
GET    /api/v1/video-gen/tasks/{id}            # 查询状态
GET    /api/v1/video-gen/tasks                 # 生成历史
DELETE /api/v1/video-gen/tasks/{id}            # 删除任务+视频
GET    /api/v1/video-gen/videos/{id}           # 播放本地视频
POST   /api/v1/video-gen/optimize-prompt       # AI 优化提示词
POST   /api/v1/video-gen/frames/import         # 尾帧入库
GET    /api/v1/video-gen/config                # 模型/参数配置
```

**关键文件：**
- `backend/app/services/seedance_service.py` — Seedance API 封装（创建/轮询/下载）
- `backend/app/api/video_gen.py` — REST 路由 + 提示词优化器 + 尾帧入库
- `frontend/src/components/VideoGenPage.ts` — **单文件**，所有功能在一个文件里

### 3. 基础设施（已有，可复用）

| 模块 | 文件 | 用途 |
|------|------|------|
| LLM 服务 | `services/llm_service.py` | 异步调用 `chat()`, `_chat_raw()` |
| LLM 交互框架 | `services/llm_interaction.py` | `execute_with_quality_gate()` 质量门控 |
| 图片生成服务 | `services/image_generation/` | 独立模块化图片生成 |
| JSON 持久化 | `services/json_store.py` | `atomic_write_json()` 原子写入 |
| 质量门控 | `services/image_quality_gate.py` | 图片输出质量检查 |
| 前端 API 封装 | `services/api.ts` | `apiGet`, `apiPost`, `apiDelete` |

---

## 二、配置项

在 `backend/.env` 中新增：

```bash
# 素材库 — icover.ai
ICOVER_API_KEY=sk-486g6pO1mBoKLT0imd9JxfAU7M9A5nyl

# 视频生成 — api.apiyi.com
APIYI_API_KEY=sk-pVfe7KbifcCjd1UV46D81c8dDf96419d80976cE09419DfFb
```

在 `backend/app/config.py` 中对应字段：`icover_api_key`, `apiyi_api_key`, `icover_base_url`

---

## 三、已注册的页面路由

在 `frontend/src/app.ts` 的 `PAGE_REGISTRY` 中：
```typescript
'asset-manage': renderAssetManagePage,   // 📦 素材
'video-gen': renderVideoGenPage,         // 🎬 视频
```

在 `frontend/src/components/TopNav.ts` 的 `NAV_ITEMS` 中：
```typescript
{ page: 'asset-manage', label: '素材', icon: '📦' },
{ page: 'video-gen', label: '视频', icon: '🎬' },
```

---

## 四、已知问题和注意事项

### 4.1 代码结构问题
- **VideoGenPage.ts 是单文件巨无霸**（约 400 行），包含了左侧配置、模态框、生成历史、入库弹窗等所有逻辑。专业模式需要完全拆开。
- **video-gen/ 目录下的 LeftPanel/MiddlePanel/RightPanel.ts** 是废稿，没有在 app.ts 中注册使用，可删除。

### 4.2 数据问题
- `backend/data/asset_library.json` 目前只有 1 条素材记录。之前的测试数据在手动 fix 脚本中断裂丢失。
- `backend/data/video_gen_history.json` 存储生成历史，含视频 URL（24h 过期）。
- 本地素材文件存储在 `backend/data/local_assets/`。
- 下载的视频存储在 `backend/data/videos/`。

### 4.3 Seedance 限制
- 时长 4-15 秒（Fast/Mini 最高 720p，Standard 最高 1080p）
- `asset://` ID 只用于人脸过审，不解决输出内容版权审核问题
- 输出视频可能触发 `PolicyViolation`（版权）、敏感内容拦截
- 视频 CDN 链接 24 小时过期，需及时下载
- Fast 模型 5s 视频约 2-3 分钟，15s 约 8-15 分钟

### 4.4 提示词优化器问题
- 优化器里的 `_chat_raw()` 调用可能超时（当前 timeout=180s）
- 偶尔 LLM 返回非 JSON 格式，解析会失败（已加 try/catch）

### 4.5 尾帧复用问题
- 含真人形象的尾帧被下一个视频使用时，建议走 icover API 重新拿 asset:// ID
- 多人尾帧无法简单复用——需要每人单独认证
- 当前入库弹窗默认"数字真人"，用户可切换分类

---

## 五、下一步：专业模式设计

### 5.1 设计参考
调研了 Seedance、Kling 3.0、LTX Studio、ComfyUI-FunPack、NVIDIA RTX Pipeline 等工具，业界标准工作流：

```
① 预生产层 → ② 生成层 → ③ 后期层
  角色圣经     逐镜生成     质检卡尺
  场景圣经     Shot 1-N    不合格退回重生成
  分镜计划
  导演台
```

### 5.2 专业模式模块

| 模块 | AI 做什么 | 人做什么 |
|------|----------|---------|
| 角色圣经 | 根据多角度照片生成特征描述、色彩方案 | 上传素材，确认/微调 |
| 场景圣经 | 根据场景图生成空间布局、光照、机位建议 | 上传场景图，确认机位 |
| 分镜计划 | 根据剧本自动拆解分镜表 | 确认/调整结构 |
| 导演台 | 自动建议节奏、表演风格、色调 | 确认方向 |
| 一键生成 | 批量生成 + 质检 + 重试 | 最终确认 |

### 5.3 技术要求
- **完全独立的新文件**，不动现有 VideoGenPage.ts
- 前端：`components/pro-mode/` 目录，独立模块
- 后端：`api/pro_mode.py` 新路由，挂载到 `/api/v1/pro-mode/*`
- 注册方式：`app.ts` 加 `'pro-mode': renderProModePage`
- **复用已有基础设施**：
  - LLM 调用 → `llm_service._chat_raw()`
  - 图片生成 → `services/image_generation/service.py`
  - JSON 持久化 → `json_store.atomic_write_json()`
  - 视频生成 API → `seedance_service.create_task()`
  - 素材管理 API → `asset_library_service`
  - 前端 API → `apiGet/apiPost`

### 5.4 新页面入口
在现有视频页左上方加一个按钮 `🎬 专业模式`，点击进入新页面。新页面顶部加 `[返回简易模式]`。

### 5.5 设计原则（铁律）
1. **不动已验证的功能** — VideoGenPage.ts 一行都不改
2. **新功能独立文件** — pro-mode/ 目录完全独立
3. **复用不重复造轮子** — 视频生成、素材管理、LLM 调用全部复用已有服务
4. **模块化注册** — 页面通过 PAGE_REGISTRY 注册，API 通过 feature_router 挂载
5. **通用功能封装** — 可被多个模块共用的逻辑抽取为独立模块

---

## 六、关键复用清单（给下一个会话）

新功能开发时，直接调用这些已有的服务和 API，不要重新实现：

| 需求 | 已有实现 | 导入方式 |
|------|---------|---------|
| 调用 LLM | `services/llm_service.py` → `llm_service._chat_raw()` | `from app.services.llm_service import llm_service` |
| 视频生成 | `services/seedance_service.py` → `seedance_service.create_task()` | `from app.services.seedance_service import seedance_service` |
| 素材上传/管理 | `services/asset_library_service.py` | `from app.services.asset_library_service import asset_library_service` |
| 持久化存储 | `services/json_store.py` → `atomic_write_json()` | `from app.services.json_store import atomic_write_json` |
| 图片生成 | `services/image_generation/service.py` | `from app.services.image_generation.service import ImageGenerationService` |
| 前端 HTTP | `services/api.ts` → `apiGet()`, `apiPost()` | `import { apiGet, apiPost } from '../services/api'` |
| 前端页面注册 | `app.ts` → `PAGE_REGISTRY` | 加一行 `'page-name': renderFunc` |
| 前端导航 | `TopNav.ts` → `NAV_ITEMS` | 加一行 `{page, label, icon}` |
| API 路由注册 | `api/__init__.py` → `feature_router` | `from app.api.new_module import router; feature_router.include_router(router)` |

---

## 七、环境信息

- **后端**：Python 3.9, FastAPI, uvicorn, 端口 8001
- **前端**：Vite + TypeScript, 端口 5173（代理 /api → 8001）
- **数据库**：SQLite（`backend/data/digital_twin.db`）
- **JSON 存储**：`backend/data/asset_library.json`, `backend/data/video_gen_history.json`
- **文件存储**：`backend/data/local_assets/`, `backend/data/videos/`
- **启动命令**：
  - 后端：`cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001`
  - 前端：`cd frontend && ./node_modules/.bin/vite --port 5173 --host 0.0.0.0`
- **LLM**：DeepSeek v4-pro (Anthropic 兼容接口)
- **视频生成**：Seedance 2.0 via api.apiyi.com
- **素材库**：icover.ai（火山引擎代理）
