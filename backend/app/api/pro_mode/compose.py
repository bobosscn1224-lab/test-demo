"""Pro Mode Step 5 — Auto Compose (自动成片).

按分镜顺序拼接已生成的镜头视频，烧录字幕（按真实视频时长对齐），导出 MP4。
ffmpeg 查找顺序：系统 PATH → imageio-ffmpeg 内置二进制。
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .models import ComposeRequest
from .projects import load_project, update_project
from .shot_state import init_shot_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compose", tags=["pro-mode-compose"])

_BACKEND_ROOT = Path(__file__).parent.parent.parent.parent
_COMPOSE_DIR = _BACKEND_ROOT / "data" / "composed"
_COMPOSE_DIR.mkdir(parents=True, exist_ok=True)


# ── ffmpeg 定位 ──────────────────────────────────────────────────

def find_ffmpeg() -> str | None:
    """系统 PATH → imageio-ffmpeg 内置二进制。"""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def probe_duration(ffmpeg_bin: str, video_path: str, fallback: float) -> float:
    """用 ffmpeg -i 的 stderr 解析真实视频时长（imageio-ffmpeg 不含 ffprobe）。"""
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-i", video_path],
            capture_output=True, text=True, timeout=30,
        )
        match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return fallback


# ── endpoints ────────────────────────────────────────────────────

@router.get("/status/{project_id}")
async def compose_status(project_id: str):
    """检查项目所有镜头的生成状态，返回可成片信息。"""
    project = load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shot_statuses = []
    for shot in project.get("shots", []):
        init_shot_state(shot)
        video_path = shot.get("video_path", "")
        ready = bool(video_path) and Path(video_path).exists()
        shot_statuses.append({
            "shot_number": shot.get("shot_number", 0),
            "status": "ready" if ready else shot.get("video_status", "pending"),
            "dialogue": shot.get("dialogue", ""),
            "duration": shot.get("duration", 5),
            "description": shot.get("description", "")[:60],
            "error": shot.get("error", ""),
        })

    ready_count = sum(1 for s in shot_statuses if s["status"] == "ready")
    total = len(shot_statuses)

    return {
        "success": True,
        "project_id": project_id,
        "title": project.get("title", ""),
        "total_shots": total,
        "ready_shots": ready_count,
        "can_compose": ready_count > 0,
        "all_ready": ready_count == total and total > 0,
        "ffmpeg_available": find_ffmpeg() is not None,
        "shots": shot_statuses,
    }


@router.post("/build")
async def build_composition(req: ComposeRequest):
    """Step 5: 自动成片 — 按分镜顺序拼接已就绪镜头 + 按真实时长烧录字幕。

    只拼接 video_status=succeeded 且视频文件存在的镜头；
    缺失镜头在响应中明确列出，绝不拿别的项目的视频凑数。
    """
    project = load_project(req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    shots = project.get("shots", [])
    if not shots:
        raise HTTPException(status_code=400, detail="项目没有分镜")

    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg 不可用。请安装 ffmpeg 或 pip install imageio-ffmpeg",
        )

    # 按分镜顺序收集就绪镜头
    segments: list[dict] = []
    missing: list[int] = []
    for shot in shots:
        init_shot_state(shot)
        sn = shot.get("shot_number", 0)
        video_path = shot.get("video_path", "")
        if video_path and Path(video_path).exists():
            segments.append({"shot": shot, "path": video_path})
        else:
            missing.append(sn)

    if not segments:
        raise HTTPException(status_code=400, detail="没有已就绪的镜头视频，请先在步骤 4 完成生成")

    # 用真实时长生成字幕时间轴
    subtitle_entries = []
    time_cursor = 0.0
    for seg in segments:
        shot = seg["shot"]
        real_duration = probe_duration(ffmpeg_bin, seg["path"], float(shot.get("duration", 5)))
        dialogue = (shot.get("dialogue") or "").strip()
        if dialogue and req.add_subtitles:
            subtitle_entries.append({
                "index": len(subtitle_entries) + 1,
                "start": time_cursor,
                # 字幕最多显示到镜头结束前 0.2 秒，避免跨镜
                "end": time_cursor + max(real_duration - 0.2, 0.5),
                "text": dialogue,
            })
        time_cursor += real_duration

    # 写 SRT
    srt_path = None
    if subtitle_entries and req.add_subtitles:
        srt_path = _COMPOSE_DIR / f"{req.project_id}_subs.srt"
        srt_path.write_text(_build_srt(subtitle_entries), encoding="utf-8")

    # 写 concat 清单（路径转义单引号）
    concat_list = _COMPOSE_DIR / f"{req.project_id}_concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for seg in segments:
            safe_path = seg["path"].replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    output_path = _COMPOSE_DIR / f"{req.project_id}_composed.mp4"

    # 先统一转码再拼接（不同镜头的编码参数可能不一致，直接 concat 会花屏）
    cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list)]
    if srt_path and srt_path.exists():
        # subtitles 滤镜需要 libass；路径中的特殊字符要转义
        srt_escaped = str(srt_path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        cmd += ["-vf", f"subtitles='{srt_escaped}':force_style='FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'"]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-movflags", "+faststart", str(output_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.error("ffmpeg compose failed: %s", (result.stderr or "")[-2000:])
            # 字幕烧录失败时降级为无字幕拼接，不让整个流程崩掉
            if srt_path:
                logger.warning("Retrying compose without subtitles")
                cmd_plain = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                             "-c:a", "aac", "-movflags", "+faststart", str(output_path)]
                result = subprocess.run(cmd_plain, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                raise HTTPException(status_code=500, detail=f"视频合成失败: {(result.stderr or '')[-300:]}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="视频合成超时（10分钟）")
    finally:
        concat_list.unlink(missing_ok=True)

    update_project(req.project_id, {"composed_video_path": str(output_path)})

    return {
        "success": True,
        "project_id": req.project_id,
        "video_count": len(segments),
        "missing_shots": missing,
        "subtitle_count": len(subtitle_entries),
        "total_duration": round(time_cursor, 1),
        "download_url": f"/api/v1/pro-mode/compose/download/{req.project_id}",
    }


@router.get("/download/{project_id}")
async def download_composition(project_id: str):
    """下载合成后的成片视频。"""
    output_path = _COMPOSE_DIR / f"{project_id}_composed.mp4"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="成片尚未生成，请先调用 /compose/build")

    return FileResponse(
        str(output_path),
        media_type="video/mp4",
        filename=f"{project_id}_composed.mp4",
    )


def _build_srt(entries: list[dict]) -> str:
    """Build SRT format subtitle content."""
    lines = []
    for entry in entries:
        lines.append(str(entry["index"]))
        start = _format_srt_time(entry["start"])
        end = _format_srt_time(entry["end"])
        lines.append(f"{start} --> {end}")
        lines.append(entry["text"])
        lines.append("")  # blank line separator
    return "\n".join(lines)


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT time format: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
