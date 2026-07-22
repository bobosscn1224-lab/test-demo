"""Resolve Tutujin credentials by role without exposing secret values."""

from __future__ import annotations

from app.config import settings


_IMAGE_SLOT_ATTRIBUTES = {
    "A": "tutujin_api_key_a",
    "B": "tutujin_api_key_b",
    "C": "tutujin_api_key_c",
}


def get_image_credential(slot: str) -> str:
    normalized = str(slot or "").strip().upper()
    attribute = _IMAGE_SLOT_ATTRIBUTES.get(normalized)
    if attribute is None:
        raise ValueError(f"unknown Tutujin credential slot: {normalized or '(empty)'}")
    credential = str(getattr(settings, attribute, "") or "").strip()
    if not credential:
        raise ValueError(f"Tutujin credential slot {normalized} is not configured")
    return credential


def get_vision_credential() -> str:
    credential = str(settings.tutujin_vision_api_key or "").strip()
    if not credential:
        raise ValueError("Tutujin credential slot VISION is not configured")
    return credential


def safe_credential_error(slot: str, exc: BaseException) -> str:
    normalized = str(slot or "").strip().upper() or "UNKNOWN"
    return f"Tutujin credential slot {normalized} failed: {exc.__class__.__name__}"
