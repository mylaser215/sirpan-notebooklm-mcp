"""세션72 — Proactive RTS 선제갱신 회귀 가드 (NLM ●●● conv 803fdca1).

_maybe_proactive_rts_refresh: RPC 성공 핫패스에서 RTS 임박 만료(<120s) 시
백그라운드로 headless auth를 선제 트리거하여 디스크 cookies.json을 신선화한다.

핵심 불변식:
    1. RTS 여유 충분 → 선제 submit 안 함
    2. RTS 임박(<120s) + future 유휴 → 선제 submit 1회
    3. 60초 쓰로틀 내 재호출 → _is_rts_expiring 미호출(파싱 스킵)
    4. future 실행 중 → 선제 skip(Layer 3와 레이스 방지 = 단일 직렬화)
    5. chrome profile 부재 → submit 안 함

본 테스트가 깨지면 선제갱신이 상시 데몬화(쓰로틀 회귀)되거나, Layer 3와
동시 headless를 띄워 세션71 좀비청소가 서로를 kill하는 파국이 회귀한다.
"""

from unittest.mock import MagicMock, patch

import pytest

from notebooklm_tools.utils import cdp as cdp_module


@pytest.fixture
def client():
    """BaseClient 인스턴스 — _refresh_auth_tokens 네트워크 호출 차단."""
    from notebooklm_tools.core.base import BaseClient

    with patch.object(BaseClient, "_refresh_auth_tokens", lambda self: None):
        c = BaseClient(
            cookies={"SID": "x", "HSID": "x"},
            csrf_token="dummy",
            session_id="dummy",
            build_label="dummy",
        )
    return c


@pytest.fixture
def fake_executor(monkeypatch):
    """ThreadPoolExecutor → submit이 not-done future 반환 (실 thread 미가동)."""
    from notebooklm_tools.core import base as base_module

    fresh_future = MagicMock()
    fresh_future.done.return_value = False
    executor = MagicMock()
    executor.submit.return_value = fresh_future
    monkeypatch.setattr(
        base_module.concurrent.futures, "ThreadPoolExecutor", lambda **kw: executor
    )
    return executor, fresh_future


def test_init_precheck_timestamp_zero(client):
    """sanity — init 시 _last_rts_precheck_at은 0.0."""
    assert client._last_rts_precheck_at == 0.0


def test_no_submit_when_rts_healthy(client, monkeypatch, fake_executor):
    """불변식 1 — RTS 여유 충분(만료 임박 아님) → 선제 submit 안 함."""
    executor, _ = fake_executor
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring", lambda *a, **kw: False
    )
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda profile="default": True)

    client._maybe_proactive_rts_refresh()

    executor.submit.assert_not_called()
    assert client._headless_auth_future is None


def test_submit_when_rts_expiring(client, monkeypatch, fake_executor):
    """불변식 2 — RTS 임박(<120s) + future 유휴 → 선제 submit 1회."""
    executor, fresh_future = fake_executor
    captured = {}

    def _spy_rts(*a, **kw):
        captured["margin"] = kw.get("margin_sec", a[1] if len(a) > 1 else None)
        return True

    monkeypatch.setattr("notebooklm_tools.core.auth._is_rts_expiring", _spy_rts)
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda profile="default": True)

    client._maybe_proactive_rts_refresh()

    executor.submit.assert_called_once()
    assert client._headless_auth_future is fresh_future
    assert client._headless_auth_started_at is not None
    assert captured["margin"] == 120, "margin_sec=120 계약 유지"


def test_throttle_skips_second_call(client, monkeypatch, fake_executor):
    """불변식 3 — 60초 쓰로틀 내 재호출 시 _is_rts_expiring 미호출(파싱 스킵)."""
    executor, _ = fake_executor
    calls = {"n": 0}

    def _counting_rts(*a, **kw):
        calls["n"] += 1
        return False  # submit까지 가지 않게

    monkeypatch.setattr("notebooklm_tools.core.auth._is_rts_expiring", _counting_rts)
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda profile="default": True)

    client._maybe_proactive_rts_refresh()  # 1회차 — 쓰로틀 통과, rts 체크
    client._maybe_proactive_rts_refresh()  # 2회차 — 쓰로틀에 막혀 즉시 return

    assert calls["n"] == 1, "쓰로틀 내 2회차는 _is_rts_expiring 파싱 스킵"


def test_skip_when_future_in_progress(client, monkeypatch, fake_executor):
    """불변식 4 — future 실행 중이면 선제 skip (Layer 3와 단일 직렬화, 레이스 방지)."""
    executor, _ = fake_executor
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring", lambda *a, **kw: True
    )
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda profile="default": True)

    in_progress = MagicMock()
    in_progress.done.return_value = False
    client._headless_auth_future = in_progress

    client._maybe_proactive_rts_refresh()

    executor.submit.assert_not_called()
    assert client._headless_auth_future is in_progress, "진행 중 future 무변경"


def test_no_submit_without_chrome_profile(client, monkeypatch, fake_executor):
    """불변식 5 — chrome profile 부재 시 submit 안 함 (헛 기동 방지)."""
    executor, _ = fake_executor
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring", lambda *a, **kw: True
    )
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda profile="default": False)

    client._maybe_proactive_rts_refresh()

    executor.submit.assert_not_called()
    assert client._headless_auth_future is None
