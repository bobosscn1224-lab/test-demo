"""Pro Mode — Pydantic data models (single source of truth)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


# ── Script Analysis ────────────────────────────────────────────────

class ScriptAnalyzeRequest(BaseModel):
    script: str = Field(..., min_length=1, description="剧本全文")


class ScriptStructureRequest(BaseModel):
    story: str = Field(..., min_length=10, description="原始故事/小说文本")
    template: str = Field(default="", description="短剧模板类型：甜恋/悬疑/校园/都市/古风/治愈")


# ── Resources ──────────────────────────────────────────────────────

class ResourceItem(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    image_prompt: str = ""
    generated_image_url: str = ""
    asset_id: str = ""
    status: str = "pending"


class ResourceGenerateRequest(BaseModel):
    project_id: str
    resource_type: str = Field(..., description="characters | scenes | props")
    resource_id: str = Field(..., description="资源 ID")


class ResourceGenerateAllRequest(BaseModel):
    project_id: str


class ResourceUploadAssetRequest(BaseModel):
    """将已有资源图上传到 icover 素材库，获取 asset:// ID。"""
    project_id: str
    resource_type: str = Field(..., description="characters | scenes | props")
    resource_id: str = Field(..., description="资源 ID")


# ── Storyboard ─────────────────────────────────────────────────────

class ShotItem(BaseModel):
    """分镜镜头。extra='allow' 保证前端回传时状态字段不丢失。"""
    model_config = ConfigDict(extra="allow")

    shot_number: int
    description: str = ""
    character_ids: list[str] = Field(default_factory=list)
    scene_id: str = ""
    prop_ids: list[str] = Field(default_factory=list)
    camera: str = ""
    duration: int = Field(default=5, ge=4, le=15)
    dialogue: str = ""
    mood: str = ""
    # ── 镜头级状态机字段（后端维护，前端只读回传）──
    frame_status: str = "pending"      # pending|generating|done|failed|stale
    frame_image_url: str = ""          # 分镜关键帧（首帧锚定用）
    video_status: str = "pending"      # pending|queued|succeeded|failed|stale
    task_id: str = ""                  # Seedance 任务 ID
    video_path: str = ""               # 已归档的本地视频路径
    video_url: str = ""                # CDN 视频地址（24h 过期）
    last_frame_url: str = ""
    error: str = ""


class StoryboardUpdateRequest(BaseModel):
    script: str | None = None
    shots: list[ShotItem] | None = None


# ── Director ───────────────────────────────────────────────────────

class DirectorSuggestRequest(BaseModel):
    project_id: str = Field(..., description="项目 ID")


# ── Generation ─────────────────────────────────────────────────────

class ShotGenerateRequest(BaseModel):
    project_id: str
    shot_number: int
    model: str = Field(default="fast")
    resolution: str = Field(default="720p")
    ratio: str = Field(default="16:9")
    generate_audio: bool = Field(default=False)
    return_last_frame: bool = Field(default=True)


class BatchGenerateRequest(BaseModel):
    """批量生成：为所有 pending/failed/stale 镜头创建任务。"""
    project_id: str
    model: str = Field(default="fast")
    resolution: str = Field(default="720p")
    ratio: str = Field(default="16:9")
    generate_audio: bool = Field(default=False)
    include_failed: bool = Field(default=True, description="是否重试失败的镜头")


class FrameGenerateRequest(BaseModel):
    """分镜关键帧（首帧图）生成请求。"""
    project_id: str
    shot_number: int


class FrameBatchRequest(BaseModel):
    project_id: str


class PortraitRequest(BaseModel):
    project_id: str
    character_ids: list[str] = Field(..., description="要生成合照的角色 ID 列表")
    style_note: str = Field(default="", description="额外风格说明")


# ── Project ────────────────────────────────────────────────────────

class StepUpdateRequest(BaseModel):
    current_step: int = Field(..., ge=0, le=5)


# ── Compose ────────────────────────────────────────────────────────

class ComposeRequest(BaseModel):
    project_id: str
    bgm_type: str = Field(default="auto", description="背景音乐类型：auto/甜蜜/紧张/治愈/无")
    add_subtitles: bool = Field(default=True)


# ── Templates ──────────────────────────────────────────────────────

TEMPLATES = {
    "甜恋": {
        "genre": "甜恋",
        "pace": "张弛交替",
        "performance_style": "自然",
        "color_tone": "暖色调",
        "transitions": "淡入淡出",
        "camera_style": "多用近景和特写，强调人物表情和眼神交流",
        "lighting": "柔光为主，暖色温，高光偏粉",
        "music_style": "轻快钢琴或吉他，中速",
        "structure_hint": "相遇→暧昧→小冲突→甜蜜和解，总镜头控制在15-25个",
    },
    "悬疑": {
        "genre": "悬疑",
        "pace": "慢节奏逐渐加速",
        "performance_style": "克制",
        "color_tone": "高对比",
        "transitions": "硬切",
        "camera_style": "多用中景和特写，强调细节和氛围",
        "lighting": "低调光，高反差，蓝色冷调",
        "music_style": "低沉弦乐或电子氛围音",
        "structure_hint": "铺垫→线索→反转→真相，总镜头控制在20-30个",
    },
    "校园": {
        "genre": "校园",
        "pace": "快节奏",
        "performance_style": "自然",
        "color_tone": "柔和",
        "transitions": "硬切",
        "camera_style": "多用中景和全景，强调青春氛围和群体互动",
        "lighting": "明亮自然光，日系清新色调",
        "music_style": "轻快吉他或尤克里里",
        "structure_hint": "日常→事件→成长→青春感悟，总镜头控制在15-25个",
    },
    "都市": {
        "genre": "都市",
        "pace": "张弛交替",
        "performance_style": "自然",
        "color_tone": "柔和",
        "transitions": "匹配剪辑",
        "camera_style": "多用中全景和跟拍，强调城市空间和人物关系",
        "lighting": "自然光+城市灯光混合，中性色温",
        "music_style": "现代流行或轻电子",
        "structure_hint": "困境→选择→成长→新生活，总镜头控制在20-30个",
    },
    "古风": {
        "genre": "古风",
        "pace": "慢节奏",
        "performance_style": "克制",
        "color_tone": "柔和",
        "transitions": "淡入淡出",
        "camera_style": "多用全景和中景，强调意境和空间留白",
        "lighting": "自然光+烛光，暖黄色调",
        "music_style": "古筝、笛子、琵琶等传统乐器",
        "structure_hint": "意境铺垫→情感递进→诗意收尾，总镜头控制在10-20个",
    },
    "治愈": {
        "genre": "治愈",
        "pace": "慢节奏",
        "performance_style": "自然",
        "color_tone": "暖色调",
        "transitions": "淡入淡出",
        "camera_style": "多用全景和空镜，强调自然环境和人物独处",
        "lighting": "黄金时刻暖光，低对比度，柔焦",
        "music_style": "温暖钢琴或木吉他",
        "structure_hint": "孤独→遇见→温暖→治愈，总镜头控制在10-20个",
    },
}
