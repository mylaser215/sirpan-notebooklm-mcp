"""v5 결함 회귀 방지 — refresh_auth() fail-close 가드.

이전 결함 (260512 본 세션 라이브 재현):
    RTS 만료 + 동기 headless 재인증 실패 시 silent debug 로그 후 disk reload로
    fallthrough → stale 만료 토큰을 "Auth tokens reloaded from disk cache"
    거짓 success로 응답. AI/사용자가 nlm login 안내 시점 놓침.

본 테스트가 깨지면 refresh_auth가 옛 fail-open 동작으로 회귀 — 인증 만료 상황에서
침묵의 실패(Ghost Auth) 발생. NLM동기화 본 흐름의 신뢰성 무너짐.

참고: tests/core/test_sources.py의 test_register_file_source_payload_structure_v4_regression
패턴과 동일 스타일 (결함 메커니즘 docstring + assert에 회귀 의미 명시).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patched_refresh_auth_deps(monkeypatch):
    """refresh_auth() 의존성 일괄 mock — 호출자가 RTS·headless·cache·client 동작 결정.

    refresh_auth는 지연 import (`from notebooklm_tools.core.auth import ...`)이므로
    함수 호출 시점에 module attribute를 본다. module 자체를 monkeypatch.
    """
    from notebooklm_tools.core import auth as core_auth
    from notebooklm_tools.mcp.tools import auth as auth_module
    from notebooklm_tools.utils import cdp as cdp_module

    # API client side effects (network) 차단
    monkeypatch.setattr(auth_module, "reset_client", lambda: None)
    monkeypatch.setattr(auth_module, "get_client", lambda: None)

    state = {
        "rts_expiring": True,
        "headless_result": None,
        "headless_exc": None,
        "cached": None,
    }

    monkeypatch.setattr(
        core_auth, "_is_rts_expiring",
        lambda *a, **kw: state["rts_expiring"],
    )
    monkeypatch.setattr(
        core_auth, "load_cached_tokens",
        lambda: state["cached"],
    )

    def fake_headless():
        if state["headless_exc"] is not None:
            raise state["headless_exc"]
        return state["headless_result"]

    monkeypatch.setattr(cdp_module, "run_headless_auth", fake_headless)

    return state


def _stale_tokens():
    """RTS 만료된 stale cache의 MagicMock — refresh_auth가 잘못 reload하면 잡힘."""
    m = MagicMock()
    m.cookies = {"SID": "stale", "SAPISID": "stale"}
    m.csrf_token = "stale-csrf"
    m.session_id = "stale-sid"
    return m


def test_refresh_auth_fail_close_on_rts_expired_headless_exception(patched_refresh_auth_deps):
    """v5 결함 회귀 — RTS 만료 + headless Exception 시 stale disk reload 금지.

    본 테스트가 깨지면 silent catch + disk fallback이 부활 — RTS 만료 상태에서
    "Auth tokens reloaded from disk cache" 거짓 success가 다시 발생.
    """
    from notebooklm_tools.mcp.tools.auth import refresh_auth

    state = patched_refresh_auth_deps
    state["rts_expiring"] = True
    state["headless_exc"] = RuntimeError("chrome profile locked")
    state["cached"] = _stale_tokens()

    result = refresh_auth()

    assert result["status"] == "error", (
        f"v5 결함 회귀: RTS 만료 + headless 예외 시 status:error 기대, got {result!r}. "
        "stale disk reload fallback이 부활하면 거짓 success가 발생함."
    )
    assert "stale" not in result.get("message", "").lower()
    assert (
        "nlm login" in result["error"].lower()
        or "headless" in result["error"].lower()
    ), f"error 메시지에 복구 경로 명시 기대, got {result['error']!r}"
    assert "headless failure" in result.get("hint", "").lower(), (
        f"hint에 headless 실패 사유 기대, got {result.get('hint')!r}"
    )


def test_refresh_auth_fail_close_on_rts_expired_headless_returns_none(patched_refresh_auth_deps):
    """v5 결함 회귀 — RTS 만료 + headless None 반환 시에도 stale disk reload 금지.

    Exception 케이스와 별개로 'headless 실행은 성공했지만 tokens 추출 실패' 경로도
    같은 fail-close 보장이어야 함.
    """
    from notebooklm_tools.mcp.tools.auth import refresh_auth

    state = patched_refresh_auth_deps
    state["rts_expiring"] = True
    state["headless_result"] = None  # 정상 실행이지만 토큰 없음
    state["cached"] = _stale_tokens()

    result = refresh_auth()

    assert result["status"] == "error", (
        f"v5 결함 회귀: headless None 반환 시 status:error 기대, got {result!r}"
    )
    assert "headless auth returned no tokens" in result.get("hint", "").lower(), (
        f"hint에 'returned no tokens' 사유 명시 기대, got {result.get('hint')!r}"
    )


def test_refresh_auth_success_on_rts_expired_headless_success(patched_refresh_auth_deps):
    """sanity — RTS 만료 + headless 성공 시 정상 success 응답 (RTS rotated)."""
    from notebooklm_tools.mcp.tools.auth import refresh_auth

    state = patched_refresh_auth_deps
    state["rts_expiring"] = True
    state["headless_result"] = MagicMock(cookies={"SID": "fresh"})

    result = refresh_auth()

    assert result["status"] == "success"
    assert "RTS rotated" in result["message"], (
        f"RTS rotated 명시 기대, got {result['message']!r}"
    )


def test_refresh_auth_disk_reload_guarded_by_rts_check(patched_refresh_auth_deps):
    """v5 픽스 — RTS healthy 분기 disk reload 시 not _is_rts_expiring() 가드 (TOCTOU 방어).

    cached가 있고 cookies가 있어도 _is_rts_expiring()이 True면 disk reload 차단.
    본 가드가 빠지면 RTS healthy 판정 후 load_cached_tokens 시점에 rotate된 상태에서
    stale 토큰 reload 가능 (race window).
    """
    from notebooklm_tools.mcp.tools.auth import refresh_auth
    from notebooklm_tools.core import auth as core_auth
    from notebooklm_tools.utils import cdp as cdp_module

    state = patched_refresh_auth_deps

    # 첫 _is_rts_expiring 호출은 False(분기 진입), 두 번째는 True (TOCTOU rotated)
    calls = {"n": 0}

    def rts_toctou(*a, **kw):
        calls["n"] += 1
        return calls["n"] > 1  # 1st: False, 2nd+: True

    import notebooklm_tools.core.auth as ca
    monkeypatch_attr = getattr(core_auth, "_is_rts_expiring")
    # 직접 setattr (fixture 후 추가 패치)
    core_auth._is_rts_expiring = rts_toctou
    try:
        state["cached"] = _stale_tokens()
        state["headless_exc"] = RuntimeError("chrome locked")
        result = refresh_auth()
    finally:
        core_auth._is_rts_expiring = monkeypatch_attr

    # cached.cookies 통과했더라도 두 번째 RTS check가 True → fallthrough → 결국 error
    assert result["status"] == "error", (
        f"TOCTOU rotate 시 stale reload 금지, status:error 기대, got {result!r}"
    )


def test_refresh_auth_success_on_rts_healthy_with_cache(patched_refresh_auth_deps):
    """sanity — RTS healthy + 정상 cache + cookies 존재 시 disk reload 정상 동작."""
    from notebooklm_tools.mcp.tools.auth import refresh_auth

    state = patched_refresh_auth_deps
    state["rts_expiring"] = False
    state["cached"] = _stale_tokens()  # 이름은 stale이지만 RTS healthy면 정상

    result = refresh_auth()

    assert result["status"] == "success"
    assert result["message"] == "Auth tokens reloaded from disk cache."
