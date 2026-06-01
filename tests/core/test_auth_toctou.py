"""배치2 ATOM-1 — TOCTOU 차단 회귀 가드.

upstream f2fb921 (v0.6.13) 동형. write_text + chmod 사이의 잠깐 world-readable
윈도우 제거 — `os.open(O_CREAT, 0o600)` + `os.fdopen` 패턴.

본 테스트가 깨지면 토큰/쿠키/메타데이터 파일 권한이 0o600 이전 상태로
세팅되거나 fd 누수 회귀.
"""

import json
import os
import stat
from unittest.mock import patch

import pytest

from notebooklm_tools.core.auth import AuthManager, AuthTokens, save_tokens_to_cache

_SKIP_ON_WINDOWS = pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX 권한 모드 검증 (chmod) — Windows는 의미 없음",
)


@pytest.fixture
def tmp_cache_path(tmp_path, monkeypatch):
    """get_cache_path를 tmp_path로 격리."""
    cache = tmp_path / "auth_tokens.json"
    monkeypatch.setattr("notebooklm_tools.core.auth.get_cache_path", lambda: cache)
    return cache


def _make_tokens() -> AuthTokens:
    return AuthTokens(
        cookies={"SID": "x", "HSID": "y"},
        csrf_token="dummy",
        session_id="dummy",
        build_label="dummy",
    )


@_SKIP_ON_WINDOWS
def test_save_tokens_creates_with_0o600(tmp_cache_path):
    """새로 생성된 토큰 캐시 파일은 0o600 권한으로 생성."""
    save_tokens_to_cache(_make_tokens(), silent=True)
    mode = stat.S_IMODE(tmp_cache_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


@_SKIP_ON_WINDOWS
def test_save_tokens_overwrites_preserves_0o600(tmp_cache_path):
    """덮어쓰기 후에도 권한 0o600 유지."""
    tmp_cache_path.write_text("{}", encoding="utf-8")
    tmp_cache_path.chmod(0o644)  # 기존에 노출 권한이었다고 가정
    save_tokens_to_cache(_make_tokens(), silent=True)
    mode = stat.S_IMODE(tmp_cache_path.stat().st_mode)
    assert mode == 0o600


def test_save_tokens_writes_valid_json(tmp_cache_path):
    """크로스플랫폼 sanity — 토큰 내용이 올바른 JSON으로 저장."""
    save_tokens_to_cache(_make_tokens(), silent=True)
    data = json.loads(tmp_cache_path.read_text(encoding="utf-8"))
    assert data["csrf_token"] == "dummy"
    assert data["cookies"]["SID"] == "x"


def test_save_tokens_no_fd_leak_on_fdopen_failure(tmp_cache_path):
    """os.fdopen이 BaseException raise해도 fd가 누수 안 됨."""
    real_close = os.close
    closed_fds: list[int] = []

    def tracking_close(fd):
        closed_fds.append(fd)
        return real_close(fd)

    with (
        patch("notebooklm_tools.core.auth.os.fdopen", side_effect=KeyboardInterrupt),
        patch("notebooklm_tools.core.auth.os.close", side_effect=tracking_close),
        pytest.raises(KeyboardInterrupt),
    ):
        save_tokens_to_cache(_make_tokens(), silent=True)

    # fdopen 실패 분기에서 os.close(fd)가 정확히 1회 호출됐어야 함
    assert len(closed_fds) == 1, f"expected 1 close, got {len(closed_fds)}: {closed_fds}"


@_SKIP_ON_WINDOWS
def test_save_profile_cookies_and_metadata_0o600(tmp_path):
    """AuthManager.save_profile — cookies.json + metadata.json 둘 다 0o600."""
    mgr = AuthManager("test_profile")
    # profile_dir을 tmp_path로 격리
    mgr.profile_dir = tmp_path / "profile"
    mgr.cookies_file = mgr.profile_dir / "cookies.json"
    mgr.metadata_file = mgr.profile_dir / "metadata.json"

    mgr.save_profile(
        cookies={"SID": "x"},
        csrf_token="t",
        session_id="s",
        email="e@e.com",
        build_label="b",
    )

    cookies_mode = stat.S_IMODE(mgr.cookies_file.stat().st_mode)
    metadata_mode = stat.S_IMODE(mgr.metadata_file.stat().st_mode)
    assert cookies_mode == 0o600, f"cookies mode {oct(cookies_mode)}"
    assert metadata_mode == 0o600, f"metadata mode {oct(metadata_mode)}"


def test_save_port_map_writes_with_utf8_json(tmp_path, monkeypatch):
    """_save_port_map TOCTOU 패치 — 한글 키도 정상 JSON 저장."""
    from notebooklm_tools.utils import cdp

    map_file = tmp_path / "port_map.json"
    monkeypatch.setattr(cdp, "_get_port_map_file", lambda: map_file)

    cdp._save_port_map({"9472": {"profile": "기본", "pid": 12345}})
    data = json.loads(map_file.read_text(encoding="utf-8"))
    assert data["9472"]["pid"] == 12345


@_SKIP_ON_WINDOWS
def test_save_port_map_0o600(tmp_path, monkeypatch):
    """_save_port_map TOCTOU — 0o600 권한."""
    from notebooklm_tools.utils import cdp

    map_file = tmp_path / "port_map.json"
    monkeypatch.setattr(cdp, "_get_port_map_file", lambda: map_file)
    cdp._save_port_map({"9472": {"profile": "x", "pid": 1}})
    mode = stat.S_IMODE(map_file.stat().st_mode)
    assert mode == 0o600
