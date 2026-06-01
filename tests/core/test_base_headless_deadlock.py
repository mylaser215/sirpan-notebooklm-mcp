"""세션56 Q4 ●●● — Layer 3 headless auth 데드락 방지 회귀 가드.

이전 결함 (NLM 자문 conv 21df4678 Q4):
    _try_reload_or_headless_auth가 _headless_auth_future가 not None일 때
    무조건 AuthRecoveryInProgress raise → 좀비/무한대기 시 future가 영원히
    done() 안 됨 → 서버 재시작 전까지 모든 도구 호출이 AuthRecoveryInProgress만
    반환되는 영구 잠금 발생.

본 테스트가 깨지면 영구 잠금 가드(timestamp + force-reset)가 회귀 — Layer 3
좀비 데드락 시 서버 사용 불능 상태로 복구 안 됨.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from notebooklm_tools.core.base import HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC
from notebooklm_tools.core.errors import AuthRecoveryInProgress


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


def test_init_started_at_is_none(client):
    """sanity — init 시 _headless_auth_started_at은 None."""
    assert client._headless_auth_started_at is None


def test_deadlock_constant_exists():
    """HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC 상수 존재 + 양수."""
    assert isinstance(HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC, (int, float))
    assert HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC > 0


def test_layer3_deadlock_force_reset_after_threshold(client, monkeypatch):
    """세션56 Q4 ●●● — 좀비 future + threshold 초과 경과 시 강제 리셋 + 새 시도.

    본 테스트가 깨지면 좀비 future가 영원히 AuthRecoveryInProgress 반환되는
    영구 잠금 버그가 회귀.
    """
    from notebooklm_tools.core import base as base_module
    from notebooklm_tools.utils import cdp as cdp_module

    # Layer 2 (disk reload) 우회 — cached None
    monkeypatch.setattr(
        "notebooklm_tools.core.auth.load_cached_tokens",
        lambda: None,
    )
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring",
        lambda *a, **kw: True,
    )
    # Layer 3 chrome profile 있다고 가정
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda profile="default": True)

    # ThreadPoolExecutor → submit이 즉시 not-done future 반환 (실 thread 미가동)
    fresh_future = MagicMock()
    fresh_future.done.return_value = False

    fake_executor = MagicMock()
    fake_executor.submit.return_value = fresh_future

    monkeypatch.setattr(
        base_module.concurrent.futures,
        "ThreadPoolExecutor",
        lambda **kw: fake_executor,
    )

    # 좀비 future 세팅 (threshold + 5초 경과)
    zombie = MagicMock()
    zombie.done.return_value = False
    client._headless_auth_future = zombie
    client._headless_auth_started_at = time.time() - (HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC + 5)

    # 강제 리셋 + 새 시도 → 새 future가 자리잡으면서 AuthRecoveryInProgress raise
    with pytest.raises(AuthRecoveryInProgress):
        client._try_reload_or_headless_auth()

    # 좀비는 사라지고 새 future가 자리잡음
    assert client._headless_auth_future is fresh_future, (
        "좀비 future 강제 리셋 + 새 future 시작 기대"
    )
    assert client._headless_auth_started_at is not None, "새 timestamp 설정 기대"
    assert (time.time() - client._headless_auth_started_at) < 5, (
        "새 timestamp는 방금 설정된 값이어야 함"
    )


def test_layer3_no_reset_within_threshold(client, monkeypatch):
    """좀비 가드 미발동 — threshold 미만 경과 시 기존 AuthRecoveryInProgress 그대로.

    본 테스트가 깨지면 데드락 가드가 과민 반응 — 정상 진행 중 future를
    너무 일찍 죽여서 동시 갱신 중복 발사 발생.
    """
    monkeypatch.setattr(
        "notebooklm_tools.core.auth.load_cached_tokens",
        lambda: None,
    )
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring",
        lambda *a, **kw: True,
    )

    # 정상 진행 중 future (threshold의 절반만 경과)
    in_progress = MagicMock()
    in_progress.done.return_value = False
    client._headless_auth_future = in_progress
    client._headless_auth_started_at = time.time() - (HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC / 2)
    saved_started_at = client._headless_auth_started_at

    with pytest.raises(AuthRecoveryInProgress):
        client._try_reload_or_headless_auth()

    # 가드 미발동 — future/timestamp 무변경
    assert client._headless_auth_future is in_progress, "정상 진행 중 future는 그대로"
    assert client._headless_auth_started_at == saved_started_at, "timestamp 그대로"


def test_layer3_timestamp_cleared_on_done_success(client, monkeypatch):
    """future done(성공) 시 _headless_auth_started_at도 None 리셋.

    본 테스트가 깨지면 다음 인증 만료 시 stale started_at이 남아 잘못된
    데드락 판정 가능.
    """
    monkeypatch.setattr(
        "notebooklm_tools.core.auth.load_cached_tokens",
        lambda: None,
    )
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring",
        lambda *a, **kw: True,
    )

    fresh_tokens = MagicMock(
        cookies={"SID": "fresh"}, csrf_token="fresh", session_id="fresh",
    )
    done_future = MagicMock()
    done_future.done.return_value = True
    done_future.result.return_value = fresh_tokens

    client._headless_auth_future = done_future
    client._headless_auth_started_at = time.time() - 10  # 10초 전 시작

    result = client._try_reload_or_headless_auth()

    assert result is True
    assert client._headless_auth_future is None, "future cleared"
    assert client._headless_auth_started_at is None, "timestamp cleared on success"


def test_layer3_timestamp_cleared_on_done_exception(client, monkeypatch):
    """future done(예외) 시에도 _headless_auth_started_at None 리셋."""
    monkeypatch.setattr(
        "notebooklm_tools.core.auth.load_cached_tokens",
        lambda: None,
    )
    monkeypatch.setattr(
        "notebooklm_tools.core.auth._is_rts_expiring",
        lambda *a, **kw: True,
    )

    failed_future = MagicMock()
    failed_future.done.return_value = True
    failed_future.result.side_effect = RuntimeError("chrome crashed")

    client._headless_auth_future = failed_future
    client._headless_auth_started_at = time.time() - 10

    result = client._try_reload_or_headless_auth()

    assert result is False
    assert client._headless_auth_future is None
    assert client._headless_auth_started_at is None, "timestamp cleared on exception"
