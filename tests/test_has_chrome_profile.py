"""Regression tests for has_chrome_profile() Chrome path resolution.

Chrome 96+ moved Cookies from `Default/Cookies` to `Default/Network/Cookies`.
The legacy path-only check made run_headless_auth() short-circuit to None,
silently disabling Layer 3 headless auth recovery.
"""

from notebooklm_tools.utils.cdp import has_chrome_profile


def test_new_path_only_returns_true(tmp_path, monkeypatch):
    """Chrome 96+ — Default/Network/Cookies present → True."""
    network_dir = tmp_path / "Default" / "Network"
    network_dir.mkdir(parents=True)
    (network_dir / "Cookies").write_bytes(b"")
    monkeypatch.setattr(
        "notebooklm_tools.utils.cdp.get_chrome_profile_dir",
        lambda name: tmp_path,
    )
    assert has_chrome_profile("default") is True


def test_legacy_path_only_returns_true(tmp_path, monkeypatch):
    """Chrome <96 — Default/Cookies present → True (backwards compat)."""
    default_dir = tmp_path / "Default"
    default_dir.mkdir(parents=True)
    (default_dir / "Cookies").write_bytes(b"")
    monkeypatch.setattr(
        "notebooklm_tools.utils.cdp.get_chrome_profile_dir",
        lambda name: tmp_path,
    )
    assert has_chrome_profile("default") is True


def test_both_paths_missing_warns_and_returns_false(tmp_path, monkeypatch, caplog):
    """Default/ exists but no Cookies file → False + warning (path migration guard)."""
    import logging

    (tmp_path / "Default").mkdir(parents=True)
    monkeypatch.setattr(
        "notebooklm_tools.utils.cdp.get_chrome_profile_dir",
        lambda name: tmp_path,
    )
    with caplog.at_level(logging.WARNING, logger="notebooklm_tools.utils.cdp"):
        result = has_chrome_profile("default")
    assert result is False
    assert any("Chrome Cookies file not found" in r.message for r in caplog.records)


def test_no_default_dir_returns_false_silently(tmp_path, monkeypatch, caplog):
    """No Default/ at all → False, no warning (profile never used)."""
    import logging

    monkeypatch.setattr(
        "notebooklm_tools.utils.cdp.get_chrome_profile_dir",
        lambda name: tmp_path,
    )
    with caplog.at_level(logging.WARNING, logger="notebooklm_tools.utils.cdp"):
        result = has_chrome_profile("default")
    assert result is False
    assert not any("Chrome Cookies file not found" in r.message for r in caplog.records)
