# 会话交接 — 2026-07-16 / 07-17

> 新 session 读完 CLAUDE.md 后再读本文档，即可接续工作。

---

## 本期做了什么

### 1. 大纲重新生成——用户反馈未生效（已修复）

**文件**：`backend/app/api/ppt_maker/outline.py`

| 问题 | 修复 |
|------|------|
| `revision` 变量名错误（应为 `revision_text`），每次重新生成大纲都 500 | 改名 |
| 重新生成时现有大纲被丢弃，LLM 不知道要改什么 | 传 `existing_outline` 给 LLM 作为上下文 |
| 用户在反馈框输入大量新内容，但被当作"修改意见"塞在 prompt 末尾 | 长反馈（>200字符）合并到 `full_source` 作为"优先级最高"的核心素材 |
| 短反馈保留为修改意见模式 | 不变 |

### 2. 拼图 prompt——视觉方向未被注入（已修复）

**文件**：`backend/app/api/ppt_maker/collage.py`

- `_build_visual_directions(styles)` 计算结果被丢弃，A/B/C 三个 prompt 完全相同
- 现在使用 `collage_prompt_spec.yaml` 的 `visual_directions`，每个方案有不同方向

### 3. 视觉规范过度约束 gpt-image-2（已简化）

**文件**：`backend/app/services/collage_prompt_spec.yaml`

| 改前 | 改后 |
|------|------|
| `visual_directions`：5 行英文详细描述 | 1 行中文方向提示 |
| `style_systems`：含色号/字体/px 的像素级规范 | 一句话气质描述 |
| `_build_briefing_context`：逐条注入 `get_style_system` | 只传风格名称 + 叙事/语调/汇报目标等高层上下文 |
| prompt 含 scale 范围（跟大纲实际页数冲突） | 删除 scale 引用，页数严格从大纲提取 |

### 4. Vision review 导致生图成功后误报失败（已修复）

**文件**：`backend/app/services/collage_prompt_spec.yaml` → `image_interactions.ppt_collage`

- **问题链**：tutujin 生图成功 → 文件校验通过 → Agnes vision review 审查 → 审查失败 → 重试仍失败 → 返回错误给用户
- **修复**：设置 `vision_review: false`
- 文件级校验（尺寸/宽高比/亮度标准差）仍然保留

### 5. Karpathy 技能已安装

**路径**：`.claude/skills/karpathy-guidelines/SKILL.md`
**状态**：需新 session 才能识别 `/karpathy-guidelines` 命令

---

## 当前运行时状态

- 后端运行在 8001（uvicorn，无 `--reload`）
- 前端运行在 5173（Vite）
- 测试项目 ID：`070eb33c`（出口管制合规预审前置方案，outline_confirmed 状态，已有 3 张拼图）

---

## 当前存在的问题

### ⚠️ 性能：生图耗时 + 超时风险

- 单张拼图 tutujin 生图 ~5-7 分钟
- `max_batch_concurrency` 当前为 **1**（YAML 第 18 行）
- 意味着三张串行，总计 ~15-21 分钟
- **待讨论**：tutujin API 是否支持并发？并发数设多少？
- 如果并发可行，改 `max_batch_concurrency`；如果不可行，需要前端轮询或 SSE

### 待讨论：参考图方案

- 当前三次独立调用，每次完整 prompt
- 理论上可用方案 A 的图作为 B/C 的 `reference_url`，缩短 prompt
- 代价：B/C 构图被 A 锁死，失去差异化。**当前倾向保持独立调用**

---

## 历史高频问题

1. **Vite/后端进程堆积**：多次启动导致端口被占，`lsof -i :端口 -t | xargs kill -9` 清理
2. **后端改代码后必须重启**：无 `--reload`
3. **日志经常为空**：`_server_err3.log` / `_server_out2.log`，排错时可能需要直接看终端输出
4. **前端 `reRender()` 重建 DOM**：异步操作中注意闭包引用

---

## 下一步建议

1. 跟用户确认 tutujin 并发策略，确定 `max_batch_concurrency` 最终值
2. 测试完整流程：创建项目 → 大纲 → 风格方案 → 逐页生成
3. 如需，给前端 `fetch` 加 `AbortController` + 超时
4. `max_batch_concurrency` > 1 后验证三张并行生成的总耗时
