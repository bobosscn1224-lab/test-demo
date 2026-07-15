"""Single source of truth for project paths. Import from here, not from __file__ tricks."""
from pathlib import Path

# _paths.py is at: backend/app/services/_paths.py
# Go up 4 levels to reach project root (backend → app → services → _paths.py)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent

DATA_DIR: Path = PROJECT_ROOT / "data"
UPLOADS_DIR: Path = DATA_DIR / "uploads"
OUTPUTS_DIR: Path = DATA_DIR / "outputs"
REPORT_DRAFTS_DIR: Path = DATA_DIR / "report_drafts"

# Public output directory — served by /api/skills/download/{filename}
PUBLIC_DIR: Path = PROJECT_ROOT / "outputs"

# Weekly report specific output directory
WEEKLY_REPORT_DIR: Path = PROJECT_ROOT / "工作周报" / "输出"
WEEKLY_REPORT_TEMPLATE: Path = PROJECT_ROOT / "工作周报" / "template & history.xlsx"

# Backend directory (for restart scripts, etc.)
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent.parent


def ensure_dirs() -> None:
    """Create all standard output directories if they don't exist."""
    for d in (OUTPUTS_DIR, UPLOADS_DIR, PUBLIC_DIR, WEEKLY_REPORT_DIR, REPORT_DRAFTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
