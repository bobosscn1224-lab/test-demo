"""PPT Maker Feature API — Pydantic models for request/response schemas."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field, field_validator


# ── Enums / validation constants ────────────────────────────────────

# Maps both Chinese labels (frontend) and English keys (internal)
PURPOSE_MAP = {
    "业务汇报": "business_report", "项目方案": "project_proposal",
    "产品宣讲": "product_launch", "培训辅导": "training",
    "复盘总结": "review", "故事路演": "story_pitch", "其他": "other",
    "business_report": "business_report", "project_proposal": "project_proposal",
    "product_launch": "product_launch", "training": "training",
    "review": "review", "story_pitch": "story_pitch", "other": "other",
}
AUDIENCE_MAP = {
    "老板管理层": "executives", "客户合作方": "clients", "一线团队": "team",
    "投资人": "investors", "混合": "mixed",
    "executives": "executives", "clients": "clients", "team": "team",
    "investors": "investors", "mixed": "mixed",
}
SCALE_MAP = {
    "精简8-12页": "compact_8_12", "标准15-20页": "standard_15_20", "完整25-35页": "full_25_35",
    "compact_8_12": "compact_8_12", "standard_15_20": "standard_15_20", "full_25_35": "full_25_35",
}
STYLE_MAP = {
    "专业严谨": "professional", "科技感": "tech", "简约商务": "minimal",
    "创意活泼": "creative", "高端大气": "bold",
    "professional": "professional", "tech": "tech", "minimal": "minimal",
    "creative": "creative", "bold": "bold",
}

VALID_PURPOSES = list(PURPOSE_MAP.keys())
VALID_AUDIENCES = list(AUDIENCE_MAP.keys())
VALID_SCALES = list(SCALE_MAP.keys())
VALID_STYLES = list(STYLE_MAP.keys())

VALID_STATUSES: list[str] = [
    "created", "content_added", "outline_generated",
    "outline_confirmed", "collages_generated", "pages_generated", "completed",
]

COLLAGE_LABELS: list[str] = ["A", "B", "C"]


# ── Project models ──────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    purpose: str = Field(..., description="One of: " + ", ".join(VALID_PURPOSES))
    audience: str = Field(..., description="One of: " + ", ".join(VALID_AUDIENCES))
    scale: str = Field(..., description="One of: " + ", ".join(VALID_SCALES))
    styles: list[str] = Field(default_factory=list, description="Visual styles from: " + ", ".join(VALID_STYLES))
    key_message: str = Field(default="", max_length=2000)  # 补充要求，可选
    # COSTAR additions — captured at briefing time
    narrative_style: str = Field(default="auto", description="auto|narrative|data_report|business_proposal|technical")
    narrative_framework: str = Field(default="auto", description="auto|conflict_driven|scr|problem_driven|opportunity_driven|abt|hook_progressive")
    objective: str = Field(default="auto", description="auto|drive_decision|show_results|secure_resources|build_consensus|transfer_knowledge")
    tone: str = Field(default="auto", description="auto|professional|storytelling|inspirational|concise|humorous")

    @field_validator("purpose")
    @classmethod
    def _check_purpose(cls, v: str) -> str:
        if v not in VALID_PURPOSES:
            raise ValueError(f"Invalid purpose '{v}'. Must be one of: {VALID_PURPOSES}")
        return v

    @field_validator("audience")
    @classmethod
    def _check_audience(cls, v: str) -> str:
        if v not in VALID_AUDIENCES:
            raise ValueError(f"Invalid audience '{v}'. Must be one of: {VALID_AUDIENCES}")
        return v

    @field_validator("scale")
    @classmethod
    def _check_scale(cls, v: str) -> str:
        if v not in VALID_SCALES:
            raise ValueError(f"Invalid scale '{v}'. Must be one of: {VALID_SCALES}")
        return v

    @field_validator("styles")
    @classmethod
    def _check_styles(cls, v: list[str]) -> list[str]:
        if not v:  # styles are optional at creation time (moved to Step 4)
            return v
        invalid = [s for s in v if s not in VALID_STYLES]
        if invalid:
            raise ValueError(f"Invalid styles: {invalid}. Must be from: {VALID_STYLES}")
        return v


class Project(BaseModel):
    id: str
    name: str
    purpose: str
    audience: str
    scale: str
    styles: list[str]
    key_message: str
    status: str = "created"
    created_at: str = ""
    updated_at: str = ""
    # COSTAR fields
    narrative_style: str = "auto"
    narrative_framework: str = "auto"
    objective: str = "auto"
    tone: str = "auto"
    outline: str = ""
    outline_mode: str = "conservative"  # conservative | enhanced
    selected_collage: str = ""
    image_backend: str = ""  # user-selected image gen backend for collages + pages
    content_text: str = ""
    content_files: list = Field(default_factory=list)   # file path strings or dicts
    outline_pages: list = Field(default_factory=list)   # structured outline pages (OutlinePage dicts)
    collages: list = Field(default_factory=list)         # CollageItem dicts with prompt
    collage_run_id: str = ""
    collage_visual_directions: dict[str, str] = Field(default_factory=dict)
    collage_generation: dict = Field(default_factory=dict)
    page_images: list = Field(default_factory=list)      # generated page images (PageItem dicts)
    pages: list = Field(default_factory=list)            # legacy — mixed outline+images, kept for compat


class ProjectUpdate(BaseModel):
    name: str | None = None
    purpose: str | None = None
    audience: str | None = None
    scale: str | None = None
    styles: list[str] | None = None
    key_message: str | None = None
    narrative_style: str | None = None
    narrative_framework: str | None = None
    objective: str | None = None
    tone: str | None = None
    image_backend: str | None = None


# ── Content models ─────────────────────────────────────────────────

class ContentAdd(BaseModel):
    text: str = ""
    files: list = Field(default_factory=list)  # list of file path strings OR dicts
    feishu_ref: str = ""


# ── Outline models ─────────────────────────────────────────────────

class OutlinePage(BaseModel):
    """A single page in the structured outline."""
    page_num: int
    title: str = ""
    type: str = "content"  # cover/toc/content/summary
    role: str = ""          # narrative role of this page
    core_message: str = ""  # one key takeaway
    points: list[str] = Field(default_factory=list)  # 3-5 bullet points
    visual_hint: str = ""   # chart type / layout suggestion


class OutlineResponse(BaseModel):
    success: bool
    project_id: str
    outline: str = ""                      # raw LLM output (for reference)
    pages: list[OutlinePage] = Field(default_factory=list)  # structured pages
    message: str = ""


class OutlineConfirm(BaseModel):
    outline: str = Field(..., min_length=1)


# ── Collage models ─────────────────────────────────────────────────

class CollageItem(BaseModel):
    label: str
    filename: str
    download_url: str = ""


class CollageGenerateResponse(BaseModel):
    success: bool
    project_id: str
    collages: list[CollageItem] = Field(default_factory=list)
    message: str = ""


class CollageSelectRequest(BaseModel):
    selected_collage: str = Field(..., description="A, B, or C")

    @field_validator("selected_collage")
    @classmethod
    def _check_label(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in COLLAGE_LABELS:
            raise ValueError(f"Invalid collage label '{v}'. Must be one of: {COLLAGE_LABELS}")
        return v


# ── Page models ────────────────────────────────────────────────────

class PageItem(BaseModel):
    page_num: int
    title: str = ""
    filename: str = ""
    download_url: str = ""


class PageGenerateResponse(BaseModel):
    success: bool
    project_id: str
    pages: list[PageItem] = Field(default_factory=list)
    total_pages: int = 0
    message: str = ""


class PageRegenerateRequest(BaseModel):
    modifications: str = ""
    style_preference: str = ""


class PageUpdateResponse(BaseModel):
    success: bool
    project_id: str
    page_num: int
    filename: str = ""
    download_url: str = ""
    message: str = ""
