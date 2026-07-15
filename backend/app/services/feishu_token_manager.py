"""Shared Feishu user token manager — single source of truth for all skills.

Used by feishu_doc_reader, feishu_minutes_reader, and knowledge import.
Only one token file: data/feishu_kb_import_user_token.json
"""
from __future__ import annotations

import json
import logging
import os
import time

from app.services.feishu_service import feishu_service

logger = logging.getLogger(__name__)

TOKEN_PATH = os.path.abspath(os.path.join("data", "feishu_kb_import_user_token.json"))
LEGACY_TOKEN_PATH = os.path.abspath(os.path.join("data", "feishu_user_token.json"))

# KB OAuth scope (shared with knowledge page)
KB_OAUTH_SCOPE = os.environ.get(
    "FEISHU_KB_OAUTH_SCOPE",
    "drive:drive:readonly drive:drive.metadata:readonly wiki:wiki:readonly "
    "docx:document:readonly space:document:retrieve minutes:minutes:readonly "
    "minutes:minutes.transcript:export minutes:minutes.basic:read offline_access",
)
KB_OAUTH_STATE = "knowledge_feishu_import"


class FeishuTokenManager:
    """Manages Feishu user OAuth tokens shared across all skills."""

    # ── Token file I/O ──────────────────────────────────────────────

    @staticmethod
    def load_token() -> dict | None:
        """Load saved token from unified file. Migrates legacy token if found."""
        token = FeishuTokenManager._read_file(TOKEN_PATH)
        if token:
            return token
        # Migration: move legacy token to unified file
        legacy = FeishuTokenManager._read_file(LEGACY_TOKEN_PATH)
        if legacy:
            FeishuTokenManager.save_token_data(legacy)
            try:
                os.remove(LEGACY_TOKEN_PATH)
            except Exception:
                pass
            return legacy
        return None

    @staticmethod
    def save_token_data(token_data: dict) -> None:
        """Persist token data to unified file."""
        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        now = time.time()
        expires_in = int(token_data.get("expires_in") or 0)
        refresh_expires_in = int(token_data.get("refresh_expires_in") or 0)
        if not refresh_expires_in and token_data.get("refresh_token"):
            refresh_expires_in = 30 * 24 * 3600
        saved = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": now + expires_in,
            "refresh_expires_at": now + refresh_expires_in,
            "scope": KB_OAUTH_SCOPE,
            "saved_at": now,
        }
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(saved, f, ensure_ascii=False, indent=2)

    # ── Token lifecycle ─────────────────────────────────────────────

    @staticmethod
    async def get_valid_access_token() -> str | None:
        """Return a valid (non-expired) access token. Refreshes if needed."""
        token_data = FeishuTokenManager.load_token()
        if not token_data:
            return None

        now = time.time()
        access_token = token_data.get("access_token")
        expires_at = float(token_data.get("expires_at") or 0)

        # Token still valid (with 2min buffer)
        if access_token and now < expires_at - 120:
            return access_token

        # Try refresh
        refresh_token = token_data.get("refresh_token")
        refresh_expires_at = float(token_data.get("refresh_expires_at") or 0)
        if refresh_token and now < refresh_expires_at - 120:
            try:
                data = await feishu_service.refresh_user_access_token_v2(refresh_token)
                if data.get("code") != 0:
                    data = await feishu_service.refresh_user_access_token_non_oidc(refresh_token)
                if data.get("code") == 0 and data.get("data", {}).get("access_token"):
                    FeishuTokenManager.save_token_data(data["data"])
                    return data["data"]["access_token"]
            except Exception as exc:
                logger.warning("Feishu token refresh failed: %s", exc)

        return None

    @staticmethod
    async def exchange_code(code: str) -> dict | None:
        """Exchange OAuth code for token, save and return token data."""
        try:
            data = await feishu_service.exchange_oauth_code_v2(code)
        except Exception as exc:
            logger.warning("OAuth code exchange failed: %s", exc)
            return None

        if data.get("code") != 0:
            return None

        token_data = data.get("data") or {}
        access_token = token_data.get("access_token")
        if not access_token:
            return None

        FeishuTokenManager.save_token_data(token_data)
        return token_data

    @staticmethod
    def build_oauth_url() -> str:
        """Build the Feishu OAuth authorization URL."""
        return feishu_service.build_oauth_authorize_url(
            state=KB_OAUTH_STATE,
            scope=KB_OAUTH_SCOPE,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _read_file(path: str) -> dict | None:
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
