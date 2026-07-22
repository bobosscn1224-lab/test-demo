"""Data types for image generation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GridLayout:
    """Precise pixel layout for a collage grid."""
    canvas_w: int
    canvas_h: int
    columns: int
    rows: int
    total_pages: int
    cell_w: int
    cell_h: int
    gap: int
    margin: int
    positions: list[tuple[int, int, int, int]]  # [(page, x, y, w, h), ...]

    def to_prompt_block(self) -> str:
        """Render as a concise prompt block for gpt-image-2."""
        lines = [
            f"Canvas: {self.canvas_w}×{self.canvas_h}px. "
            f"{self.total_pages} thumbnails in {self.rows}×{self.columns} grid. "
            f"Each thumbnail: {self.cell_w}×{self.cell_h}px (16:9). Gap: {self.gap}px. Margin: {self.margin}px.",
        ]
        for page, x, y, w, h in self.positions:
            lines.append(f"  Slide {page}: ({x},{y}) {w}×{h}px")
        last_row_count = self.total_pages - (self.rows - 1) * self.columns
        lines.append(
            f"Last row has {last_row_count} thumbnails — keep them {self.cell_w}×{self.cell_h}px, do NOT stretch."
        )
        return "\n".join(lines)


@dataclass
class GenerationResult:
    """Single image generation result."""
    success: bool
    label: str = ""
    filename: str = ""
    path: str = ""
    download_url: str = ""
    error: str = ""
    backend: str = ""
    elapsed_seconds: float = 0


@dataclass
class CollageBatchResult:
    """Batch collage generation result (may be partial)."""
    success: bool
    collages: list[GenerationResult] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    visual_directions: dict[str, str] = field(default_factory=dict)
    run_id: str = ""
