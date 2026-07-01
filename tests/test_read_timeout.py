"""무거운 메타 read RPC timeout 회귀 가드.

배경: 대형 노트북(172소스, 번들 .md 대형 텍스트)에서 get_notebook /
get_notebook_sources_with_types / query 내부 source_id 추출이 httpx.Client의
고정 30초 read timeout을 초과해 "read operation timed out" 발생.
(sirpan개선 세션393 핸드오프 → sirpan-notebooklm-mcp 세션59 픽스)

픽스: _get_client()/_get_async_client()의 timeout을 httpx.Timeout으로 분리해
read만 READ_TIMEOUT(기본 180s)로 확대. connect는 15s로 짧게 유지(네트워크
끊김 빠른 감지). _call_rpc의 `if timeout:` → `if timeout is not None:` 견고화.
"""

import importlib
from unittest.mock import MagicMock, patch

import httpx
import pytest

from notebooklm_tools.core.client import NotebookLMClient


@pytest.fixture
def client():
    with patch.object(NotebookLMClient, "_refresh_auth_tokens"):
        return NotebookLMClient(cookies={"SID": "x"}, csrf_token="t", session_id="s")


def test_get_client_uses_extended_read_timeout(client):
    """sync client: read는 ≥180s로 확대, connect/write/pool은 짧게 유지."""
    with patch("notebooklm_tools.core.base.httpx.Client") as MockClient:
        client._client = None  # 재생성 강제
        client._get_client()
    _, kwargs = MockClient.call_args
    t = kwargs["timeout"]
    assert isinstance(t, httpx.Timeout)
    assert t.read >= 180.0  # 핵심: 무거운 메타 응답이 30초 초과해도 견딤
    assert t.connect == 15.0  # 진짜 네트워크 끊김은 빨리 감지
    assert t.write == 30.0
    assert t.pool == 30.0


def test_get_async_client_uses_extended_read_timeout(client):
    """async client도 동일한 read timeout 정책."""
    with patch("notebooklm_tools.core.base.httpx.AsyncClient") as MockAsync:
        client._get_async_client()
    _, kwargs = MockAsync.call_args
    t = kwargs["timeout"]
    assert isinstance(t, httpx.Timeout)
    assert t.read >= 180.0
    assert t.connect == 15.0


def test_read_timeout_env_override(monkeypatch):
    """NOTEBOOKLM_READ_TIMEOUT env로 read timeout 튜닝 가능."""
    import notebooklm_tools.core.base as base_mod

    monkeypatch.setenv("NOTEBOOKLM_READ_TIMEOUT", "250")
    try:
        importlib.reload(base_mod)
        assert base_mod.READ_TIMEOUT == 250.0
    finally:
        monkeypatch.delenv("NOTEBOOKLM_READ_TIMEOUT", raising=False)
        importlib.reload(base_mod)
    assert base_mod.READ_TIMEOUT == 180.0  # 기본값 복원


def test_call_rpc_passes_explicit_zero_timeout(client):
    """`if timeout is not None` 가드: timeout=0.0(falsy)도 post에 전달된다.

    구버전 `if timeout:`은 0.0을 누락시켜 client 기본값으로 떨어졌음.
    """
    mock_resp = MagicMock()
    mock_resp.text = "dummy"
    fake_client = MagicMock()
    fake_client.post.return_value = mock_resp
    with (
        patch.object(client, "_get_client", return_value=fake_client),
        patch.object(client, "_build_request_body", return_value="body"),
        patch.object(client, "_build_url", return_value="http://x"),
        patch.object(client, "_parse_response", return_value=[]),
        patch.object(client, "_extract_rpc_result", return_value={"ok": True}),
    ):
        result = client._call_rpc("rpc", [], timeout=0.0)
    assert result == {"ok": True}
    _, kwargs = fake_client.post.call_args
    assert kwargs.get("timeout") == 0.0


def test_add_timeout_default_and_env(monkeypatch):
    """SOURCE_ADD_TIMEOUT: 기본 180s + NOTEBOOKLM_ADD_TIMEOUT env 오버라이드.

    파일 업로드 경로(register RPC + resumable upload 세션)가 옛 60s 하드코딩에서
    풀려 다른 소스 add(url/text/drive)와 동일한 확장 timeout을 공유하는지 가드.
    (add-timeout 픽스: 120→180 env화 + file 경로 편입)
    """
    import notebooklm_tools.core.base as base_mod

    assert base_mod.SOURCE_ADD_TIMEOUT == 180.0  # 기본값 (120→180 상향, READ_TIMEOUT과 대칭)

    monkeypatch.setenv("NOTEBOOKLM_ADD_TIMEOUT", "300")
    try:
        importlib.reload(base_mod)
        assert base_mod.SOURCE_ADD_TIMEOUT == 300.0
    finally:
        monkeypatch.delenv("NOTEBOOKLM_ADD_TIMEOUT", raising=False)
        importlib.reload(base_mod)
    assert base_mod.SOURCE_ADD_TIMEOUT == 180.0  # 기본값 복원
