"""Pro Mode — 镜头级状态机 + 失效传播（纯函数，可单测）。

状态机：
  frame_status: pending → generating → done | failed
                done/pending/failed → stale（上游变更失效）
  video_status: pending → queued → succeeded | failed
                succeeded/pending/failed → stale（上游变更失效）

失效传播规则：
  - 分镜的视觉字段（description/camera/scene_id/character_ids/prop_ids）变化
    → frame_status + video_status 都置 stale
  - 分镜的非视觉字段（dialogue/mood/duration）变化
    → 仅 video_status 置 stale（分镜图仍然有效）
  - 角色/场景/道具资源图变更
    → 所有引用该资源的分镜 frame_status + video_status 置 stale
"""

from __future__ import annotations

# 分镜视觉字段：变了会导致"画面不一样"
VISUAL_FIELDS = ("description", "camera", "scene_id", "character_ids", "prop_ids")
# 分镜非视觉字段：变了只影响视频内容/音频，不影响分镜图
NON_VISUAL_FIELDS = ("dialogue", "mood", "duration")

TERMINAL_OK = ("done", "succeeded")


def init_shot_state(shot: dict) -> dict:
    """为镜头补齐状态机字段（幂等，不覆盖已有状态）。"""
    shot.setdefault("frame_status", "pending")
    shot.setdefault("frame_image_url", "")
    shot.setdefault("video_status", "pending")
    shot.setdefault("task_id", "")
    shot.setdefault("video_path", "")
    shot.setdefault("video_url", "")
    shot.setdefault("last_frame_url", "")
    shot.setdefault("error", "")
    return shot


def _mark_stale(shot: dict, field: str) -> bool:
    """将指定状态字段置为 stale。已终态成功或进行中的才需要标，pending 保持不变。"""
    current = shot.get(field, "pending")
    if current in ("pending",):
        return False
    shot[field] = "stale"
    return True


def diff_storyboard_shots(old_shots: list[dict], new_shots: list[dict]) -> dict:
    """比较新旧分镜表，对新表应用失效传播（原地修改 new_shots）。

    返回统计信息 {"stale_visual": [...], "stale_video": [...], "kept": [...]}。
    匹配规则：按 shot_number 对齐（前端编辑不改变镜头数量顺序时最直观）。
    """
    old_map = {s.get("shot_number"): s for s in old_shots}
    stats: dict[str, list[int]] = {"stale_visual": [], "stale_video": [], "kept": []}

    for new_shot in new_shots:
        sn = new_shot.get("shot_number")
        old_shot = old_map.get(sn)

        if old_shot is None:
            # 新增镜头：全部从零开始
            init_shot_state(new_shot)
            new_shot["frame_status"] = "pending"
            new_shot["video_status"] = "pending"
            continue

        # 先继承旧镜头的状态字段（前端可能只回了编辑字段）
        # 必须在 init_shot_state 之前，否则 setdefault 会用 "pending" 占位
        for key in ("frame_status", "frame_image_url", "video_status", "task_id",
                    "video_path", "video_url", "last_frame_url", "error"):
            if key not in new_shot or new_shot.get(key) in (None, ""):
                if old_shot.get(key) not in (None, ""):
                    new_shot[key] = old_shot[key]

        # 再用 init_shot_state 补齐仍然缺失的字段（幂等）
        init_shot_state(new_shot)

        visual_changed = any(new_shot.get(f) != old_shot.get(f) for f in VISUAL_FIELDS)
        non_visual_changed = any(new_shot.get(f) != old_shot.get(f) for f in NON_VISUAL_FIELDS)

        if visual_changed:
            if _mark_stale(new_shot, "frame_status"):
                stats["stale_visual"].append(sn)
            if _mark_stale(new_shot, "video_status"):
                stats["stale_video"].append(sn)
        elif non_visual_changed:
            if _mark_stale(new_shot, "video_status"):
                stats["stale_video"].append(sn)
            else:
                stats["kept"].append(sn)
        else:
            stats["kept"].append(sn)

    return stats


def invalidate_shots_using_resource(project: dict, resource_type: str, resource_id: str) -> list[int]:
    """资源（角色/场景/道具）图变更后，将引用它的分镜标记为 stale（原地修改）。

    resource_type: characters | scenes | props
    返回受影响的 shot_number 列表。
    """
    affected: list[int] = []
    for shot in project.get("shots", []):
        init_shot_state(shot)
        used = False
        if resource_type == "characters":
            used = resource_id in (shot.get("character_ids") or [])
        elif resource_type == "scenes":
            used = shot.get("scene_id") == resource_id
        elif resource_type == "props":
            used = resource_id in (shot.get("prop_ids") or [])

        if used:
            _mark_stale(shot, "frame_status")
            _mark_stale(shot, "video_status")
            affected.append(shot.get("shot_number"))
    return affected


def shot_is_actionable(shot: dict, include_failed: bool = True) -> bool:
    """判断镜头是否需要（重新）提交视频生成。"""
    status = shot.get("video_status", "pending")
    if status == "pending":
        return True
    if include_failed and status in ("failed", "stale"):
        return True
    return False
