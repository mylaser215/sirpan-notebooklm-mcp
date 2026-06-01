"""배치2 ATOM-1 — terminate_chrome null-safety 회귀 가드.

upstream f2fb921 (v0.6.13) 동형. double-call 시 _cached_ws가 None이면
AttributeError 발생 → ref를 try 진입 전 캡쳐 + None 가드.

본 테스트가 깨지면 Chrome 종료 흐름 중 _cached_ws 가비지 콜렉션 race에서
AttributeError 회귀.
"""

from unittest.mock import MagicMock, patch


def test_terminate_chrome_with_cached_ws_none_no_attribute_error(monkeypatch):
    """_cached_ws=None 상태에서 terminate_chrome 호출 시 AttributeError 없음."""
    from notebooklm_tools.utils import cdp

    # 전역 상태 설정: _cached_ws_url은 있지만 _cached_ws는 None (race condition 시뮬레이션)
    monkeypatch.setattr(cdp, "_cached_ws", None)
    monkeypatch.setattr(cdp, "_cached_ws_url", "ws://fake:9222/devtools")
    monkeypatch.setattr(cdp, "_chrome_port", 9222)
    monkeypatch.setattr(cdp, "_chrome_process", MagicMock())

    # execute_cdp_command은 mock — Browser.close 호출 자체는 검증 불필요
    with patch.object(cdp, "execute_cdp_command", return_value={}):
        # null-safety 패치 전이라면 _cached_ws.close()에서 AttributeError 발생
        result = cdp.terminate_chrome(port=9222)

    # AttributeError 없이 정상 흐름 통과 (return value는 process가 None이라 False 가능)
    assert result in (True, False)
