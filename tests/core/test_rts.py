"""Tests for RTS (Rotating Token Service) expiry detection helper.

Google's `__Secure-1PSIDRTS` / `__Secure-3PSIDRTS` rotate every 10 minutes.
`_is_rts_expiring()` detects when these are expired or about to expire so that
Layer 2 disk-cache reload doesn't short-circuit Layer 3 headless re-auth.
"""

import json
import time

from notebooklm_tools.core.auth import _is_rts_expiring


def test_is_rts_expiring_within_margin(tmp_path, monkeypatch):
    """RTS expires < now + margin_sec → True (treated as expiring)."""
    cookies_path = tmp_path / "cookies.json"
    cookies_path.write_text(
        json.dumps(
            [
                {"name": "__Secure-1PSIDRTS", "expires": time.time() + 30},
                {"name": "SID", "expires": time.time() + 31_536_000},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "notebooklm_tools.utils.config.get_profile_dir",
        lambda name: tmp_path,
    )
    assert _is_rts_expiring(margin_sec=60) is True


def test_is_rts_expiring_healthy(tmp_path, monkeypatch):
    """RTS expires > now + margin_sec → False (healthy)."""
    cookies_path = tmp_path / "cookies.json"
    cookies_path.write_text(
        json.dumps(
            [
                {"name": "__Secure-1PSIDRTS", "expires": time.time() + 600},
                {"name": "__Secure-3PSIDRTS", "expires": time.time() + 600},
                {"name": "SID", "expires": time.time() + 31_536_000},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "notebooklm_tools.utils.config.get_profile_dir",
        lambda name: tmp_path,
    )
    assert _is_rts_expiring(margin_sec=60) is False
