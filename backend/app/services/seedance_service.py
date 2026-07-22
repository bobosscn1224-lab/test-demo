"""Seedance Video Generation Service — wraps api.apiyi.com Seedance 2.0 API.

Provides:
- Text-to-video generation
- Image-reference video generation (using asset:// IDs from Asset Library)
- Task status polling
- Video download & local caching
- Generation history tracking
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.services.json_store import atomic_write_json

logger = logging.getLogger(__name__)

# ── Seedance API constants ──────────────────────────────────────
SEEDANCE_BASE = "https://api.apiyi.com/seedance/api/v3/contents/generations/tasks"

MODELS = {
    "standard": "doubao-seedance-2-0-260128",
    "fast": "doubao-seedance-2-0-fast-260128",
    "mini": "doubao-seedance-2-0-mini-260615",
}

RESOLUTIONS = ["480p", "720p", "1080p"]
RATIOS = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
DURATION_RANGE = (4, 15)

# ── Local history store ─────────────────────────────────────────
_HISTORY_DIR = Path(os.path.dirname(__file__)).parent.parent / "data"
_HISTORY_FILE = _HISTORY_DIR / "video_gen_history.json"
_VIDEO_OUTPUT_DIR = _HISTORY_DIR / "videos"


def _load_history() -> dict[str, Any]:
    if _HISTORY_FILE.exists():
        try:
            import json
            return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"tasks": {}}
    return {"tasks": {}}


def _save_history(data: dict[str, Any]) -> None:
    atomic_write_json(str(_HISTORY_FILE), data)


# ── Service ─────────────────────────────────────────────────────

class SeedanceService:
    """Encapsulates api.apiyi.com Seedance 2.0 video generation."""

    def __init__(self) -> None:
        self._api_key = settings.apiyi_api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(300.0),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",  # Critical: prevent gzip decode errors
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Task creation ───────────────────────────────────────────

    async def create_task(
        self,
        prompt: str,
        reference_assets: list[str] | None = None,
        first_frame_asset: str | None = None,
        last_frame_asset: str | None = None,
        model: str = "fast",
        resolution: str = "720p",
        ratio: str = "16:9",
        duration: int = 5,
        generate_audio: bool = False,
        return_last_frame: bool = False,
        seed: int = -1,
    ) -> dict[str, Any]:
        """Create a Seedance video generation task.

        Args:
            prompt: Text prompt describing the video (Chinese ≤500 chars)
            reference_assets: List of asset:// IDs or local URLs for reference images (0-9)
            first_frame_asset: URL for the first frame (image-to-video start frame)
            last_frame_asset: URL for the last frame (requires first_frame_asset)
            model: "standard", "fast", or "mini"
            resolution: "480p", "720p", or "1080p" (1080p only for standard)
            ratio: Aspect ratio
            duration: Video length in seconds (4-15, or -1 for auto)
            generate_audio: Whether to generate audio
            return_last_frame: Whether to return the last frame as PNG
            seed: Random seed (-1 for random)

        Returns:
            {"task_id": "cgt-xxx", "status": "queued", ...}
        """
        if not self.is_configured:
            raise RuntimeError("APIYI_API_KEY not configured")

        model_id = MODELS.get(model, model)

        # Build content array
        content: list[dict] = []

        # Add text prompt
        content.append({"type": "text", "text": prompt})

        # Add reference images (for reference mode)
        if reference_assets:
            for asset_url in reference_assets:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": asset_url},
                    "role": "reference_image",
                })

        # Add first frame (takes precedence over reference mode)
        if first_frame_asset:
            content.append({
                "type": "image_url",
                "image_url": {"url": first_frame_asset},
                "role": "first_frame",
            })
            # Add last frame if provided
            if last_frame_asset:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": last_frame_asset},
                    "role": "last_frame",
                })

        body: dict[str, Any] = {
            "model": model_id,
            "content": content,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "generate_audio": generate_audio,
            "return_last_frame": return_last_frame,
        }
        if seed >= 0:
            body["seed"] = seed

        logger.info("Creating Seedance task: model=%s, resolution=%s, ratio=%s, duration=%d, assets=%d",
                     model, resolution, ratio, duration, len(reference_assets or []))

        client = await self._get_client()
        resp = await client.post(SEEDANCE_BASE, json=body)
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("id", "")
        if not task_id:
            raise RuntimeError(f"No task ID in response: {data}")

        # Save to local history
        self._save_task_record(
            task_id=task_id,
            prompt=prompt,
            model=model,
            resolution=resolution,
            ratio=ratio,
            duration=duration,
            reference_assets=reference_assets or [],
            status="queued",
        )

        return {
            "task_id": task_id,
            "status": "queued",
            "model": model,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
        }

    # ── Task status ──────────────────────────────────────────────

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Query a task's current status and result."""
        client = await self._get_client()
        resp = await client.get(f"{SEEDANCE_BASE}/{task_id}")
        resp.raise_for_status()
        data = resp.json()

        # Update local history
        status = data.get("status", "unknown")
        record = self._update_task_status(task_id, status, data)

        return record

    async def poll_task(
        self,
        task_id: str,
        poll_interval: float = 15.0,
        max_wait: float = 900.0,
    ) -> dict[str, Any]:
        """Poll a task until it reaches a terminal state (succeeded/failed/expired).

        Args:
            task_id: The task ID to poll
            poll_interval: Seconds between polls (API recommends 15-30s)
            max_wait: Maximum total wait time in seconds (default 15 min)

        Returns:
            Task record with status and video_url if succeeded
        """
        elapsed = 0.0
        while elapsed < max_wait:
            record = await self.get_task(task_id)
            status = record.get("status", "")

            if status in ("succeeded", "failed", "expired"):
                return record

            logger.debug("Task %s: %s (%.0fs elapsed)", task_id, status, elapsed)
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"Task {task_id} did not complete within {max_wait}s")

    # ── Video download ──────────────────────────────────────────

    async def download_video(self, task_id: str, video_url: str) -> str:
        """Download a generated video to local storage.

        Returns the local file path.
        """
        _VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = _VIDEO_OUTPUT_DIR / f"{task_id}.mp4"

        # Don't re-download if already exists
        if output_path.exists():
            logger.info("Video already cached: %s", output_path)
            return str(output_path)

        logger.info("Downloading video %s -> %s", task_id, output_path)
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as dl_client:
            resp = await dl_client.get(video_url)
            resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(resp.content)

        # Update local record
        self._update_task_record(task_id, {"local_path": str(output_path)})

        return str(output_path)

    # ── Local history ───────────────────────────────────────────

    def _save_task_record(self, task_id: str, **fields) -> None:
        history = _load_history()
        now = datetime.now(timezone.utc).isoformat()

        history["tasks"][task_id] = {
            "task_id": task_id,
            "created_at": now,
            "updated_at": now,
            **fields,
        }
        _save_history(history)

    def _update_task_status(self, task_id: str, status: str, api_data: dict) -> dict:
        history = _load_history()
        record = history["tasks"].get(task_id, {"task_id": task_id})

        now = datetime.now(timezone.utc).isoformat()
        record["status"] = status
        record["updated_at"] = now

        # Extract video URL if succeeded
        content = api_data.get("content", {}) or {}
        video_url = content.get("video_url", "")
        if video_url:
            record["video_url"] = video_url

        # Extract last frame URL if available
        last_frame_url = content.get("last_frame_url", "") or content.get("last_frame", "")
        if last_frame_url:
            record["last_frame_url"] = last_frame_url

        # Extract usage info
        usage = api_data.get("usage", {}) or {}
        if usage.get("completion_tokens"):
            record["tokens"] = usage["completion_tokens"]

        # Extract error if failed
        error = api_data.get("error", {}) or {}
        if error:
            record["error"] = str(error)

        history["tasks"][task_id] = record
        _save_history(history)

        return record

    def _update_task_record(self, task_id: str, updates: dict) -> None:
        history = _load_history()
        if task_id in history["tasks"]:
            history["tasks"][task_id].update(updates)
            history["tasks"][task_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_history(history)

    def list_tasks(self, limit: int = 50) -> list[dict]:
        """List recent generation tasks, newest first."""
        history = _load_history()
        tasks = list(history.get("tasks", {}).values())
        tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks[:limit]

    def get_task_record(self, task_id: str) -> dict | None:
        """Get a single task's local record."""
        history = _load_history()
        return history.get("tasks", {}).get(task_id)

    def delete_task_record(self, task_id: str) -> bool:
        """Delete a task from local history. Also removes cached video."""
        history = _load_history()
        if task_id in history.get("tasks", {}):
            del history["tasks"][task_id]
            _save_history(history)

            # Delete cached video
            video_path = _VIDEO_OUTPUT_DIR / f"{task_id}.mp4"
            try:
                video_path.unlink(missing_ok=True)
            except Exception:
                pass

            return True
        return False


# ── Singleton ───────────────────────────────────────────────────

seedance_service = SeedanceService()
