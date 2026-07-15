"""Skill session registry — single source of truth for session management.

Each skill registers itself with its session dict and name.
The chat route uses this registry instead of importing skill internals.
"""
from __future__ import annotations

_registry: dict[str, dict[str, dict]] = {}


def register(name: str, sessions: dict[str, dict]) -> None:
    """Register a skill's session store under its name."""
    _registry[name] = sessions


def get_active_skill(session_id: str) -> str | None:
    """Return the name of the skill that owns this session, or None."""
    for name, sessions in _registry.items():
        if session_id in sessions:
            return name
    return None


def clear_session(session_id: str) -> str | None:
    """Clear a session from whichever skill owns it. Returns the skill name or None."""
    for name, sessions in _registry.items():
        if session_id in sessions:
            sessions.pop(session_id, None)
            return name
    return None


def is_stateless_skill(skill_name: str) -> bool:
    """Stateless skills (image_gen, etc.) don't hold sessions and can interrupt."""
    return skill_name not in _registry
