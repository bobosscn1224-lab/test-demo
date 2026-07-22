# 专业模式升级总结

> 升级日期：2026-07-22  
> 架构师 / 开发工程师 / 测试工程师 / 质量检查工程师 多维度实施

---

## 一、升级背景

原专业模式存在以下核心问题：

| 问题 | 严重度 | 描述 |
|------|--------|------|
| 镜头→视频→成片断链 | P0 | `/generate/shot` 不持久化 task_id，前端轮询靠内存，刷新即丢；compose 找不到视频时随机拿别的文件凑数 |
| 无分镜图先行 | P0 | 没有关键帧确认环节，直接文生视频，角色/场景一致性无法保证 |
| 无失效传播 | P1 | 改了分镜描述/资源图/导演风格后，旧的分镜图和视频不会标记过期，用户不知道要重新生成 |
| 无批量生成 | P1 | 只能逐个点击生成，10+ 镜头效率极低 |
| ffmpeg 依赖 | P1 | 系统未安装 ffmpeg 时合成直接失败，无降级方案 |
| 前端状态不同步 | P1 | 前端用内存维护镜头状态，刷新后全部丢失 |

## 二、架构改造

### 2.1 七步闭环流程

```
剧本结构化 → 资源固化 → 分镜拆解 → 分镜图确认（首帧锚定）→ 逐镜生成 → 音频 → 剪辑成片
```

本次升级重点实现了 **分镜图确认** 和 **首帧锚定** 环节。

### 2.2 镜头级状态机

每个镜头新增两组状态字段，由后端统一维护：

```
frame_status: pending → generating → done | failed
              done/pending/failed → stale（上游变更失效）

video_status: pending → queued → succeeded | failed
              succeeded/pending/failed → stale（上游变更失效）
```

### 2.3 失效传播规则

| 触发条件 | 影响范围 | 标记字段 |
|----------|----------|----------|
| 分镜视觉字段变更（description/camera/scene_id/character_ids/prop_ids） | 当前镜头 | frame_status + video_status → stale |
| 分镜非视觉字段变更（dialogue/mood/duration） | 当前镜头 | 仅 video_status → stale |
| 导演视觉风格变更（color_tone/performance_style/transitions） | 全部镜头 | frame_status + video_status → stale |
| 资源图重新生成 | 引用该资源的镜头 | frame_status + video_status → stale |

### 2.4 首帧锚定

分镜关键帧图作为 Seedance 的 `first_frame_asset`，将一致性从 prompt 级提升到图像级：

1. 用户在分镜计划页生成关键帧图（调用 ImageGenerationService）
2. 视频生成时，`_frame_url_to_data_uri()` 将本地图片转 base64 data URI
3. 有首帧时不再叠加 `asset://` 参考图，避免模态冲突
4. Seedance 以图生视频模式运行，首帧画面 = 分镜关键帧

## 三、后端改动清单

### 3.1 新建文件

| 文件 | 说明 |
|------|------|
| `pro_mode/shot_state.py` | 镜头级状态机纯函数模块（init_shot_state, diff_storyboard_shots, invalidate_shots_using_resource, shot_is_actionable） |
| `tests/test_shot_state.py` | 状态机单元测试（24 个测试用例） |

### 3.2 重写文件

| 文件 | 关键改动 |
|------|----------|
| `pro_mode/storyboard.py` | 新增 `/frame`、`/frame-all` 分镜关键帧生成端点；`build_frame_prompt()` 组装生图 prompt；更新分镜时调用 `diff_storyboard_shots()` 实现失效传播 |
| `pro_mode/generation.py` | `_frame_url_to_data_uri()` 首帧转 base64；`_submit_shot_task()` 首帧锚定；task_id/video_status 持久化；新增 `/batch` 批量生成；新增 `/shot-status/{pid}/{sn}` 服务端轮询+下载归档；新增 `/shots-status/{pid}` 批量状态 |
| `pro_mode/compose.py` | `find_ffmpeg()` 支持 imageio-ffmpeg；`probe_duration()` 解析真实视频时长；字幕按真实时长对齐；字幕烧录失败降级无字幕拼接；修复随机视频凑数 bug |

### 3.3 修改文件

| 文件 | 改动 |
|------|------|
| `pro_mode/models.py` | ShotItem 加 `ConfigDict(extra="allow")`；新增状态机字段；新增 BatchGenerateRequest / FrameGenerateRequest / FrameBatchRequest |
| `pro_mode/director.py` | 导演视觉风格变化 → 全部分镜标 stale；改用 `save_project()` 整体保存 |
| `pro_mode/resources.py` | 资源图生成成功后调用 `invalidate_shots_using_resource()` 标记引用分镜 stale |

## 四、前端改动清单

| 文件 | 关键改动 |
|------|----------|
| `types.ts` | Shot 接口加状态机字段（frame_status/video_status/task_id 等）；ShotTask 状态对齐后端；Project 加 raw_story/template/structured_script 等可选字段；新增 ProjectSummary 导出 |
| `StoryboardPlanner.ts` | 新增分镜关键帧生成 UI（单个 + 批量）；关键帧缩略图显示；帧状态徽章（pending/generating/done/failed/stale）；保存时显示失效传播统计 |
| `ShotGenerator.ts` | 改用服务端轮询 `/shot-status/{pid}/{sn}`（不再用前端内存 task_id）；新增批量生成按钮；首帧锚定标记显示；视频成功后内联预览；初始加载用 `/shots-status/{pid}` 恢复状态 |
| `AutoCompose.ts` | 支持部分合成（仅就绪镜头）；显示缺失镜头列表；ffmpeg 可用性检查；合成结果显示跳过镜头编号 |

## 五、测试验证

### 5.1 后端单元测试

```
============================== 24 passed in 9.15s ==============================
```

覆盖：
- `init_shot_state`：幂等补齐字段（3 tests）
- `diff_storyboard_shots`：视觉/非视觉字段变更失效传播、新增镜头、pending 不标 stale、状态继承（6 tests）
- `invalidate_shots_using_resource`：角色/场景/道具资源失效传播（4 tests）
- `shot_is_actionable`：各状态下的可操作判断（8 tests）
- 字段常量完整性验证（3 tests）

### 5.2 前端编译验证

```
pro-mode TypeScript errors: 0
```

### 5.3 后端 import 验证

```
All imports OK
Smoke test OK
```

## 六、新增 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/pro-mode/storyboard/frame` | 为单个镜头生成关键帧 |
| POST | `/v1/pro-mode/storyboard/frame-all` | 批量生成所有待生成关键帧 |
| POST | `/v1/pro-mode/generate/batch` | 批量提交所有待生成镜头到 Seedance |
| GET | `/v1/pro-mode/generate/shot-status/{pid}/{sn}` | 服务端轮询单个镜头状态（自动下载归档） |
| GET | `/v1/pro-mode/generate/shots-status/{pid}` | 一次性拉取所有镜头状态 |

## 七、技术决策记录

| 决策 | 理由 |
|------|------|
| 后端为状态唯一权威 | 前端刷新/断线不丢状态，可断点续做 |
| 首帧图转 base64 data URI | Seedance API 无法访问 localhost，必须内联上传 |
| imageio-ffmpeg 优先级低于系统 ffmpeg | 不污染系统环境，系统已有 ffmpeg 时直接用 |
| 字幕烧录失败降级无字幕 | 不让字幕问题阻断整个成片流程 |
| 按 shot_number 对齐新旧分镜 | 前端编辑不改变镜头顺序时最直观 |
| init_shot_state 在继承之后调用 | 避免 setdefault 用 "pending" 占位阻止旧状态继承 |

---

*升级完成。如需回滚，参考 git 历史。*
