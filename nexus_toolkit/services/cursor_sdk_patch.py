"""Patches for cursor-sdk runtime issues in standalone desktop apps."""

from __future__ import annotations

import secrets

_PATCHED = False


def apply_cursor_sdk_patches() -> None:
    """Avoid bridge launch failures when callback auth tokens start with '-'."""
    global _PATCHED
    if _PATCHED:
        return

    try:
        import cursor_sdk._store_callback as store_callback
        import cursor_sdk._tool_callback as tool_callback
    except ImportError:
        return

    def safe_new_auth_token() -> str:
        for _ in range(32):
            token = secrets.token_urlsafe(32)
            if token and not token.startswith("-"):
                return token
        return secrets.token_hex(32)

    tool_callback._new_auth_token = safe_new_auth_token
    store_callback._new_auth_token = safe_new_auth_token
    _PATCHED = True
