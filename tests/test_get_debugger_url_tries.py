"""run_headless_auth tries 비대칭 회귀 가드 — silent fail 방어.

이전 결함 (260514 본 세션 라이브 재현):
    run_headless_auth가 background ThreadPoolExecutor 환경에서 CDP endpoint
    노출 지연을 5회(약 2.5-5초) 동안만 폴링 → race 시 None 반환, silent fail.
    포그라운드 extract_cookies_via_cdp는 tries=30 (cdp.py:923) — 비대칭이 결정 원인.

본 테스트가 깨지면 run_headless_auth가 옛 tries=5로 회귀 — refresh_auth가
background에서 침묵 실패하여 사용자 수동 nlm login 부담 부활.

참고: NLM 자문 강도 ●●●, 가설 우선순위 #1 (260514 단교차삼단시공 묶음B).
"""

import pytest


@pytest.fixture
def patched_headless_deps(monkeypatch):
    """run_headless_auth headless launch 분기로 진입시키기 위한 의존성 mock.

    run_headless_auth는 cdp 모듈 내부 함수들을 직접 호출 → 모듈 attribute mock.
    finally 블록의 terminate_chrome도 mock — 실제 호출 시 _read_port_map 디스크 IO 발생.
    """
    from notebooklm_tools.utils import cdp as cdp_module

    state = {"get_debugger_url_calls": []}

    # has_chrome_profile True (headless 진입 가능)
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda *a, **kw: True)
    # is_profile_locked False (락 분기 회피)
    monkeypatch.setattr(cdp_module, "is_profile_locked", lambda *a, **kw: False)

    class _FakeProc:
        """subprocess.Popen 인터페이스 stub — finally terminate_chrome에서 잠시 참조됨."""

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            pass

        stderr = None

    monkeypatch.setattr(
        cdp_module, "launch_chrome_process", lambda *a, **kw: _FakeProc()
    )
    # terminate_chrome mock — 디스크 IO + WebSocket 실제 호출 차단
    monkeypatch.setattr(cdp_module, "terminate_chrome", lambda *a, **kw: False)

    def fake_get_debugger_url(port, *, tries=1, timeout=5):
        state["get_debugger_url_calls"].append({"port": port, "tries": tries})
        # 첫 호출(existence check) → None: Chrome 미실행 → headless launch 분기 진입
        # 둘째 호출(launch 후 wait) → None: short-circuit (회귀 검증만 목적)
        return None

    monkeypatch.setattr(cdp_module, "get_debugger_url", fake_get_debugger_url)

    return state


def test_run_headless_auth_uses_cdp_headless_tries(patched_headless_deps):
    """tries=CDP_HEADLESS_TRIES(30) 유지 회귀 가드.

    본 테스트가 깨지면 background ThreadPoolExecutor에서 CDP 폴링 부족으로
    silent fail 재발 — refresh_auth가 침묵 실패하여 사용자가 nlm login 수동 강제.
    """
    from notebooklm_tools.utils.cdp import CDP_HEADLESS_TRIES, run_headless_auth

    state = patched_headless_deps
    result = run_headless_auth(port=9223, profile_name="default")

    # 흐름 검증: existence check + launch 후 wait = 2회 이상
    assert len(state["get_debugger_url_calls"]) >= 2, (
        "get_debugger_url가 최소 2번(existence + launch후 wait) 호출 기대, "
        f"got {state['get_debugger_url_calls']!r}. "
        "흐름 변경 시 본 테스트의 fake mock 분기 재검토 필요."
    )

    # 핵심 회귀 가드: 둘째 호출의 tries = CDP_HEADLESS_TRIES (30)
    second_call = state["get_debugger_url_calls"][1]
    assert second_call["tries"] == CDP_HEADLESS_TRIES, (
        f"회귀: run_headless_auth가 tries={CDP_HEADLESS_TRIES} 사용 기대 "
        "(background race 방어, 260514 silent fail 픽스), "
        f"got tries={second_call['tries']}. tries=5로 회귀하면 침묵 실패 재발."
    )

    # 상수 자체도 30 (포그라운드 extract_cookies_via_cdp:923과 통일)
    assert CDP_HEADLESS_TRIES == 30, (
        "CDP_HEADLESS_TRIES 상수가 30 기대 "
        f"(extract_cookies_via_cdp:923과 통일, 비대칭 해소), got {CDP_HEADLESS_TRIES}"
    )

    # short-circuit 후 None 반환 (debugger_url None → headless 실패)
    assert result is None, (
        f"fake mock에서 둘째 get_debugger_url None → run_headless_auth None 기대, got {result!r}"
    )
