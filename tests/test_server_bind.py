"""배치1 ATOM-3 — HTTP/SSE external-bind fail-close 회귀 가드.

upstream 8f63d6f (v0.6.13) 동형. 비-loopback 바인딩 시
NOTEBOOKLM_ALLOW_EXTERNAL_BIND 미설정이면 SystemExit(1) 강제.

본 테스트가 깨지면 외부 네트워크에 Google 쿠키 누출 가드가 회귀.
"""

from unittest.mock import patch

import pytest

from notebooklm_tools.mcp.server import _env_bool, main


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """모든 테스트마다 ALLOW_EXTERNAL_BIND env 정리."""
    monkeypatch.delenv("NOTEBOOKLM_ALLOW_EXTERNAL_BIND", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_MCP_TRANSPORT", raising=False)
    monkeypatch.delenv("NOTEBOOKLM_MCP_HOST", raising=False)


def _run_main(monkeypatch, argv):
    """sys.argv를 세팅하고 main() 호출."""
    monkeypatch.setattr("sys.argv", ["notebooklm-mcp", *argv])
    with patch("notebooklm_tools.mcp.server.mcp.run") as mock_run:
        main()
    return mock_run


def test_loopback_http_runs_normally(monkeypatch):
    """127.0.0.1 + http → mcp.run 호출 정상."""
    mock_run = _run_main(monkeypatch, ["--transport", "http", "--host", "127.0.0.1"])
    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("host") == "127.0.0.1"
    assert kwargs.get("transport") == "streamable-http"


def test_external_http_no_env_exits(monkeypatch):
    """0.0.0.0 + http + env 미설정 → SystemExit(1)."""
    monkeypatch.setattr("sys.argv", ["notebooklm-mcp", "--transport", "http", "--host", "0.0.0.0"])
    with (
        patch("notebooklm_tools.mcp.server.mcp.run") as mock_run,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
    mock_run.assert_not_called()


def test_external_http_env_set_warns_and_runs(monkeypatch):
    """0.0.0.0 + http + env=1 → warnings.warn + mcp.run 호출."""
    monkeypatch.setenv("NOTEBOOKLM_ALLOW_EXTERNAL_BIND", "1")
    monkeypatch.setattr(
        "sys.argv", ["notebooklm-mcp", "--transport", "http", "--host", "0.0.0.0"]
    )
    with (
        patch("notebooklm_tools.mcp.server.mcp.run") as mock_run,
        pytest.warns(UserWarning, match="SECURITY WARNING"),
    ):
        main()
    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("host") == "0.0.0.0"


def test_external_sse_no_env_exits(monkeypatch):
    """0.0.0.0 + sse + env 미설정 → SystemExit(1) (SSE도 동일 가드)."""
    monkeypatch.setattr("sys.argv", ["notebooklm-mcp", "--transport", "sse", "--host", "0.0.0.0"])
    with (
        patch("notebooklm_tools.mcp.server.mcp.run") as mock_run,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
    mock_run.assert_not_called()


def test_loopback_sse_runs_normally(monkeypatch):
    """127.0.0.1 + sse → mcp.run 호출 정상 (회귀 가드)."""
    mock_run = _run_main(monkeypatch, ["--transport", "sse", "--host", "127.0.0.1"])
    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs.get("transport") == "sse"


# _env_bool 매트릭스 — 미설정/empty/false/0/no/off/true 모두 정의대로
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, False),  # 미설정
        ("", False),  # empty
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("True", True),
        ("yes", True),
        ("anything_else", True),
    ],
)
def test_env_bool_matrix(monkeypatch, value, expected):
    """_env_bool 해석 매트릭스."""
    if value is None:
        monkeypatch.delenv("NLM_TEST_ENV_BOOL", raising=False)
    else:
        monkeypatch.setenv("NLM_TEST_ENV_BOOL", value)
    assert _env_bool("NLM_TEST_ENV_BOOL") is expected


def test_env_bool_default_true_when_unset(monkeypatch):
    """미설정 시 default 인자 우선 (True 명시 시 True 반환)."""
    monkeypatch.delenv("NLM_TEST_DEFAULT", raising=False)
    assert _env_bool("NLM_TEST_DEFAULT", default=True) is True
