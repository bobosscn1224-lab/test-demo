"""Asset Library Service — wraps icover.ai API for digital human asset management.

Provides:
- Virtual human image upload & registration (no real-person auth needed)
- Asset CRUD (list, get, delete)
- Group management

icover.ai is a proxy for Volcengine's Seedance asset library.
asset:// IDs returned here can be used in Seedance video generation.
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

# ── Local asset metadata store ──────────────────────────────────
_ASSET_STORE_DIR = Path(os.path.dirname(__file__)).parent.parent / "data"
_ASSET_STORE_FILE = _ASSET_STORE_DIR / "asset_library.json"


def _load_store() -> dict[str, Any]:
    """Load local asset metadata store."""
    if _ASSET_STORE_FILE.exists():
        try:
            import json
            return json.loads(_ASSET_STORE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"assets": {}, "groups": {}}
    return {"assets": {}, "groups": {}}


def _save_store(data: dict[str, Any]) -> None:
    """Persist local asset metadata store."""
    atomic_write_json(str(_ASSET_STORE_FILE), data)


# ── Asset categories ────────────────────────────────────────────
ASSET_CATEGORIES = ["数字真人", "场景", "道具", "其他"]
# Only 数字真人 needs icover API (real person face review)
API_REQUIRED_CATEGORY = "数字真人"

# ── Local asset storage ────────────────────────────────────────
_LOCAL_ASSETS_DIR = Path(os.path.dirname(__file__)).parent.parent / "data" / "local_assets"
_LOCAL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

class AssetLibraryService:
    """Encapsulates icover.ai asset library API calls."""

    def __init__(self) -> None:
        self._api_key = settings.icover_api_key
        self._base = settings.icover_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # ── Low-level API methods ───────────────────────────────────

    async def presign_upload(self, ext: str = "jpg", content_type: str = "image/jpeg") -> dict:
        """Request a presigned upload URL from icover.ai."""
        client = await self._get_client()
        resp = await client.post(
            f"{self._base}/api/storage/presign",
            headers=self._headers(),
            json={"ext": ext, "contentType": content_type},
        )
        resp.raise_for_status()
        return resp.json()

    async def upload_to_presigned_url(self, upload_url: str, file_data: bytes, content_type: str) -> None:
        """PUT file binary to the presigned URL."""
        client = await self._get_client()
        # Use a separate client call without the auth header
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as put_client:
            resp = await put_client.put(
                upload_url,
                content=file_data,
                headers={"Content-Type": content_type},
            )
            resp.raise_for_status()

    async def create_asset(
        self,
        image_url: str,
        label: str = "",
        group_id: str | None = None,
        asset_type: str = "Image",
    ) -> dict:
        """Register an image as an asset in the library."""
        client = await self._get_client()
        body: dict[str, Any] = {"imageUrl": image_url, "assetType": asset_type}
        if label:
            body["label"] = label
        if group_id:
            body["groupId"] = group_id

        logger.info("Creating asset: label=%s, group=%s", label, group_id)
        resp = await client.post(
            f"{self._base}/api/asset-library/assets",
            headers=self._headers(),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_asset(self, asset_id: str) -> dict:
        """Query a single asset's status."""
        client = await self._get_client()
        resp = await client.get(
            f"{self._base}/api/asset-library/assets/{asset_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def list_assets(
        self,
        group_id: str | None = None,
        page_number: int = 1,
        page_size: int = 100,
    ) -> dict:
        """List assets (optionally filtered by group)."""
        client = await self._get_client()
        params: dict[str, str] = {
            "pageNumber": str(page_number),
            "pageSize": str(min(page_size, 100)),
        }
        if group_id:
            params["groupId"] = group_id

        resp = await client.get(
            f"{self._base}/api/asset-library/assets",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_asset(self, asset_id: str) -> dict:
        """Delete an asset from the library."""
        client = await self._get_client()
        resp = await client.delete(
            f"{self._base}/api/asset-library/assets/{asset_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def update_asset_label(self, asset_id: str, label: str) -> dict:
        """Update an asset's label."""
        client = await self._get_client()
        resp = await client.patch(
            f"{self._base}/api/asset-library/assets/{asset_id}",
            headers=self._headers(),
            json={"label": label},
        )
        resp.raise_for_status()
        return resp.json()

    async def list_groups(self) -> dict:
        """List all asset groups."""
        client = await self._get_client()
        resp = await client.get(
            f"{self._base}/api/asset-library/groups",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def create_group(self, name: str, description: str = "") -> dict:
        """Create a new asset group."""
        client = await self._get_client()
        body: dict[str, str] = {"name": name}
        if description:
            body["description"] = description

        resp = await client.post(
            f"{self._base}/api/asset-library/groups",
            headers=self._headers(),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    # ── High-level combined operations ──────────────────────────

    async def upload_and_register(
        self,
        file_data: bytes,
        filename: str,
        label: str = "",
        group_id: str | None = None,
        category: str = "人物",
        poll_interval: float = 3.0,
        max_wait: float = 90.0,
    ) -> dict[str, Any]:
        """Complete flow: upload image to CDN → register as asset → poll until Active.

        Returns:
            {
                "asset_id": "asset-xxx",
                "asset_url": "asset://asset-xxx",
                "label": "...",
                "category": "人物|场景|道具|其他",
                "group_id": "...",
                "public_url": "https://cdn.icover.ai/...",
                "status": "Active",
            }
        """
        if not self.is_configured:
            raise RuntimeError("ICOVER_API_KEY not configured")

        # 1. Determine extension and content type
        ext = os.path.splitext(filename)[1].lower().lstrip(".") or "jpg"
        content_type_map = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp",
            "bmp": "image/bmp", "gif": "image/gif",
        }
        content_type = content_type_map.get(ext, "image/jpeg")

        # 2. Get presigned upload URL
        logger.info("Step 1/4: Requesting presigned upload URL...")
        presign_result = await self.presign_upload(ext=ext, content_type=content_type)
        data = presign_result.get("data", presign_result)
        upload_url = data.get("uploadUrl") or data.get("upload_url")
        public_url = data.get("publicUrl") or data.get("public_url")

        if not upload_url:
            raise RuntimeError(f"Failed to get upload URL: {presign_result}")

        # 3. Upload file to CDN
        logger.info("Step 2/4: Uploading file to CDN (%d bytes)...", len(file_data))
        await self.upload_to_presigned_url(upload_url, file_data, content_type)

        # 4. Register as asset
        logger.info("Step 3/4: Registering asset in library...")
        asset_result = await self.create_asset(
            image_url=public_url,
            label=label or filename,
            group_id=group_id,
        )
        asset_id = asset_result.get("Result", {}).get("Id", "")
        if not asset_id:
            # Try alternative response format
            asset_id = asset_result.get("data", {}).get("Id", "") or asset_result.get("Id", "")

        if not asset_id:
            raise RuntimeError(f"Failed to get asset ID from response: {asset_result}")

        # 5. Poll until Active
        logger.info("Step 4/4: Polling asset status for %s...", asset_id)
        status = await self._poll_asset_status(asset_id, poll_interval, max_wait)

        asset_url = f"asset://{asset_id}"

        # 6. Save to local store
        self._save_local_asset(
            asset_id=asset_id,
            asset_url=asset_url,
            label=label or filename,
            category=category if category in ASSET_CATEGORIES else "人物",
            group_id=group_id or "",
            public_url=public_url,
            status=status,
            filename=filename,
        )

        return {
            "asset_id": asset_id,
            "asset_url": asset_url,
            "label": label or filename,
            "category": category if category in ASSET_CATEGORIES else "人物",
            "group_id": group_id or "",
            "public_url": public_url,
            "status": status,
        }

    async def _poll_asset_status(
        self, asset_id: str, interval: float, max_wait: float
    ) -> str:
        """Poll asset status until Active or Failed, or timeout."""
        elapsed = 0.0
        while elapsed < max_wait:
            result = await self.get_asset(asset_id)
            status = (result.get("Result", {}) or {}).get("Status", "")
            if not status:
                status = result.get("Status", "")

            if status == "Active":
                return status
            if status == "Failed":
                raise RuntimeError(f"Asset {asset_id} failed to process")

            logger.debug("Asset %s status: %s (%.1fs elapsed)", asset_id, status, elapsed)
            await asyncio.sleep(interval)
            elapsed += interval

        raise TimeoutError(f"Asset {asset_id} did not become Active within {max_wait}s")

    # ── Local metadata management ───────────────────────────────

    def _save_local_asset(
        self,
        asset_id: str,
        asset_url: str,
        label: str,
        group_id: str,
        public_url: str,
        status: str,
        filename: str,
        category: str = "人物",
    ) -> None:
        """Persist asset metadata to local JSON store."""
        store = _load_store()
        now = datetime.now(timezone.utc).isoformat()

        store["assets"][asset_id] = {
            "asset_id": asset_id,
            "asset_url": asset_url,
            "label": label,
            "category": category if category in ASSET_CATEGORIES else "人物",
            "group_id": group_id,
            "public_url": public_url,
            "status": status,
            "filename": filename,
            "created_at": now,
            "updated_at": now,
        }
        _save_store(store)

    def list_local_assets(
        self, group_id: str | None = None, category: str | None = None
    ) -> list[dict]:
        """List locally tracked assets, optionally filtered by group and/or category."""
        store = _load_store()
        assets = list(store.get("assets", {}).values())
        if group_id:
            assets = [a for a in assets if a.get("group_id") == group_id]
        if category and category in ASSET_CATEGORIES:
            assets = [a for a in assets if a.get("category", "人物") == category]
        # Sort by created_at descending
        assets.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        return assets

    def get_local_asset(self, asset_id: str) -> dict | None:
        """Get a single locally tracked asset."""
        store = _load_store()
        return store.get("assets", {}).get(asset_id)

    def delete_local_asset(self, asset_id: str) -> bool:
        """Remove an asset from local store. Returns True if existed."""
        store = _load_store()
        if asset_id in store.get("assets", {}):
            del store["assets"][asset_id]
            _save_store(store)
            return True
        return False

    def update_local_asset_label(self, asset_id: str, label: str) -> bool:
        """Update an asset's label in local store."""
        store = _load_store()
        if asset_id in store.get("assets", {}):
            store["assets"][asset_id]["label"] = label
            store["assets"][asset_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            _save_store(store)
            return True
        return False


    # ── Local file management (non-API assets: 场景/道具/其他) ────

    def save_local_file(self, file_data: bytes, filename: str, label: str, category: str) -> dict:
        """Save a file locally (no icover API call). Returns local metadata."""
        import uuid as _uuid

        asset_id = f"local-{_uuid.uuid4().hex[:12]}"
        ext = os.path.splitext(filename)[1].lower() or ".png"
        saved_name = f"{asset_id}{ext}"
        saved_path = _LOCAL_ASSETS_DIR / saved_name

        saved_path.write_bytes(file_data)
        public_url = f"/api/v1/assets/local-files/{saved_name}"

        self._save_local_asset(
            asset_id=asset_id,
            asset_url=public_url,  # local URL instead of asset://
            label=label or filename,
            category=category if category in ASSET_CATEGORIES else "其他",
            group_id="",
            public_url=public_url,
            status="Active",  # Local files are always Active
            filename=filename,
        )

        return {
            "asset_id": asset_id,
            "asset_url": public_url,
            "label": label or filename,
            "category": category,
            "group_id": "",
            "public_url": public_url,
            "status": "Active",
        }

    def delete_local_file(self, asset_id: str) -> bool:
        """Delete a local file and its metadata record."""
        store = _load_store()
        asset = store.get("assets", {}).get(asset_id)
        if asset:
            # Delete file from disk
            public_url = asset.get("public_url", "")
            if public_url.startswith("/api/v1/assets/local-files/"):
                filename = public_url.split("/")[-1]
                filepath = _LOCAL_ASSETS_DIR / filename
                try:
                    filepath.unlink(missing_ok=True)
                except Exception:
                    pass
        return self.delete_local_asset(asset_id)

    def needs_api(self, category: str) -> bool:
        """Check if this category requires icover API (only 数字真人)."""
        return category == API_REQUIRED_CATEGORY


# ── Singleton ───────────────────────────────────────────────────

asset_library_service = AssetLibraryService()
