"""Regression guards for the cdp.run_headless_auth module-level single-flight.

세션75 — refresh_auth(mcp/tools/auth.py)가 base.py 공유 lock/future를 우회해
run_headless_auth를 직접 호출 → 이중 headless Chrome 레이스(_cleanup_zombie_chrome
상호 kill). 자원(port 9223 물리 싱글턴)이 사는 cdp.py에 single-flight를 두어
모든 프로세스-내 호출자를 자동 직렬화. NLM+신드리 ●●● 합의.

계약:
- 동시 호출(같은 profile) → impl 정확히 1회 + 결과 공유 (재실행 아님)
- leader 예외/hang → follower graceful None + 모듈 상태 클리어 (영구 잠금 방지)
- 순차 호출 → 매번 impl 실행 (캐싱 아님 — 기존 직접호출 테스트 호환의 계약)
- 좀비 가드: in-flight 나이 > _SINGLEFLIGHT_ZOMBIE_SEC → 강제 클리어 + 새 leader
"""

import concurrent.futures
import threading
import time

from notebooklm_tools.utils import cdp


def _reset_state():
    cdp._singleflight_future = None
    cdp._singleflight_started_at = None
    cdp._singleflight_profile = None


def setup_function(_func):
    _reset_state()


def teardown_function(_func):
    _reset_state()


def test_concurrent_same_profile_runs_impl_once(monkeypatch):
    """두 스레드 동시 호출(같은 profile) → impl 1회 실행 + 동일 토큰 공유."""
    calls = []
    entered = threading.Event()
    release = threading.Event()

    def slow_impl(port=9223, timeout=30, profile_name="default"):
        calls.append(profile_name)
        entered.set()
        release.wait(timeout=5)
        return "TOKEN"

    monkeypatch.setattr(cdp, "_run_headless_auth_impl", slow_impl)

    results = {}

    def leader():
        results["leader"] = cdp.run_headless_auth()

    def follower():
        results["follower"] = cdp.run_headless_auth()

    t1 = threading.Thread(target=leader)
    t1.start()
    assert entered.wait(timeout=5)  # leader is inside impl → future registered

    t2 = threading.Thread(target=follower)
    t2.start()
    time.sleep(0.1)  # let follower register as follower on the leader's future
    release.set()

    t1.join(timeout=5)
    t2.join(timeout=5)

    assert calls == ["default"]  # impl ran exactly once
    assert results["leader"] == "TOKEN"
    assert results["follower"] == "TOKEN"  # shared, not re-run
    # state cleared
    assert cdp._singleflight_future is None
    assert cdp._singleflight_started_at is None
    assert cdp._singleflight_profile is None


def test_leader_exception_follower_none_and_state_cleared(monkeypatch):
    """leader가 예외로 죽어도 follower는 graceful None + 모듈 상태 클리어 + 후속 fresh."""
    entered = threading.Event()
    release = threading.Event()

    def boom_impl(port=9223, timeout=30, profile_name="default"):
        entered.set()
        release.wait(timeout=5)
        raise RuntimeError("headless boom")

    monkeypatch.setattr(cdp, "_run_headless_auth_impl", boom_impl)

    results = {}

    def leader():
        try:
            results["leader"] = cdp.run_headless_auth()
        except Exception as e:  # noqa: BLE001 — leader may propagate (impl in prod swallows)
            results["leader_exc"] = type(e).__name__

    def follower():
        results["follower"] = cdp.run_headless_auth()

    t1 = threading.Thread(target=leader)
    t1.start()
    assert entered.wait(timeout=5)

    t2 = threading.Thread(target=follower)
    t2.start()
    time.sleep(0.1)
    release.set()

    t1.join(timeout=5)
    t2.join(timeout=5)

    # follower must never hang or crash — graceful None
    assert results.get("follower") is None
    # module state must be clean regardless of leader outcome (no permanent lock)
    assert cdp._singleflight_future is None
    assert cdp._singleflight_started_at is None
    assert cdp._singleflight_profile is None

    # a subsequent call runs impl fresh (not a stuck/cached flight)
    monkeypatch.setattr(cdp, "_run_headless_auth_impl", lambda **k: "OK2")
    assert cdp.run_headless_auth() == "OK2"


def test_sequential_calls_run_impl_each_time(monkeypatch):
    """순차 2회 호출 → impl 2회 (결과 캐싱 아님 — 직접호출 테스트 호환 계약)."""
    calls = []

    def impl(port=9223, timeout=30, profile_name="default"):
        calls.append(1)
        return "T"

    monkeypatch.setattr(cdp, "_run_headless_auth_impl", impl)

    assert cdp.run_headless_auth() == "T"
    assert cdp.run_headless_auth() == "T"
    assert len(calls) == 2


def test_zombie_guard_promotes_new_leader(monkeypatch):
    """in-flight future가 좀비 임계 초과 → 강제 클리어 + 새 leader가 fresh 실행."""
    stuck = concurrent.futures.Future()  # never resolved (wedged leader)
    cdp._singleflight_future = stuck
    cdp._singleflight_started_at = time.time() - (cdp._SINGLEFLIGHT_ZOMBIE_SEC + 10)
    cdp._singleflight_profile = "default"

    monkeypatch.setattr(cdp, "_run_headless_auth_impl", lambda **k: "FRESH")

    # Must NOT block on the stuck future; force-clear and run fresh.
    assert cdp.run_headless_auth() == "FRESH"
    assert cdp._singleflight_future is None
    assert cdp._singleflight_started_at is None
    assert cdp._singleflight_profile is None


def test_follower_timeout_returns_none(monkeypatch):
    """leader가 follower 대기 상한을 넘겨 hang → follower graceful None (무한 대기 금지)."""
    monkeypatch.setattr(cdp, "_SINGLEFLIGHT_ZOMBIE_SEC", 0.4)
    entered = threading.Event()
    release = threading.Event()

    def slow(port=9223, timeout=30, profile_name="default"):
        entered.set()
        release.wait(timeout=5)
        return "LATE"

    monkeypatch.setattr(cdp, "_run_headless_auth_impl", slow)

    results = {}

    def leader():
        results["leader"] = cdp.run_headless_auth()

    def follower():
        results["follower"] = cdp.run_headless_auth()

    t1 = threading.Thread(target=leader)
    t1.start()
    assert entered.wait(timeout=5)

    t2 = threading.Thread(target=follower)
    t2.start()
    t2.join(timeout=5)  # follower returns None after ~0.4s bounded wait

    assert results.get("follower") is None

    release.set()
    t1.join(timeout=5)
    assert results["leader"] == "LATE"
