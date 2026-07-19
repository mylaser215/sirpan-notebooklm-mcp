"""_cleanup_zombie_chrome 회귀 가드 — Windows 좀비 Chrome 자가치유.

근본원인 (led 세션 진단 + CC Windows 실측 + NLM ●●● conv 803fdca1):
    이전 headless-auth의 좀비 chrome.exe가 프로필을 Named Mutex로 점유하면,
    동일 --user-data-dir 재실행이 좀비로 forward 후 즉시 종료 → 디버깅 포트
    미개방 → auth 복구 무한루프 → 사용자 `nlm login --clear` 오버킬 강제.
    SingletonLock은 POSIX 전용이라 Windows에선 is_profile_locked가 무력.

본 테스트가 깨지면 좀비 청소가 회귀 → --clear 반복 부활, 또는 사용자 실 Chrome
오살(다른 프로필 경로) 위험. cmdline 매칭은 PID-BFS 대비 robust (NLM_MCP_Archive 선례).
"""

import os

import psutil
import pytest

from notebooklm_tools.utils import cdp as cdp_module
from notebooklm_tools.utils.cdp import _cleanup_zombie_chrome


class _FakeProc:
    """psutil Process stub — .info dict + .kill() 인터페이스만 구현."""

    def __init__(self, pid, name, cmdline, kill_exc=None):
        self.pid = pid
        self.info = {"name": name, "cmdline": cmdline}
        self._kill_exc = kill_exc
        self.killed = False

    def kill(self):
        if self._kill_exc is not None:
            raise self._kill_exc
        self.killed = True


def _patch_procs(monkeypatch, procs):
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **kw: list(procs))


def test_kills_only_matching_profile(tmp_path, monkeypatch):
    """해당 --user-data-dir을 쥔 chrome만 kill, 타 프로필·비-chrome은 보호."""
    profile = tmp_path / "chrome-profiles" / "default"
    profile.mkdir(parents=True)
    other = tmp_path / "chrome-profiles" / "someones_real_chrome"

    match = _FakeProc(101, "chrome.exe", ["chrome.exe", f"--user-data-dir={profile}", "--headless=new"])
    other_profile = _FakeProc(102, "chrome.exe", ["chrome.exe", f"--user-data-dir={other}"])
    not_chrome = _FakeProc(103, "python.exe", ["python.exe", f"--user-data-dir={profile}"])

    _patch_procs(monkeypatch, [match, other_profile, not_chrome])

    killed = _cleanup_zombie_chrome(profile)

    assert killed == 1
    assert match.killed is True
    assert other_profile.killed is False, "사용자 실 Chrome(다른 프로필) 오살 금지"
    assert not_chrome.killed is False, "비-chrome 프로세스는 표적 아님"


def test_split_form_user_data_dir(tmp_path, monkeypatch):
    """`--user-data-dir <path>` 분리 형태도 매칭."""
    profile = tmp_path / "p"
    profile.mkdir()
    proc = _FakeProc(201, "chromium", ["chromium", "--user-data-dir", str(profile)])
    _patch_procs(monkeypatch, [proc])

    assert _cleanup_zombie_chrome(profile) == 1
    assert proc.killed is True


def test_access_denied_is_skipped(tmp_path, monkeypatch):
    """kill이 AccessDenied면 그 프로세스만 skip하고 나머지는 계속 청소 (fail-open)."""
    profile = tmp_path / "p"
    profile.mkdir()
    denied = _FakeProc(301, "chrome", ["chrome", f"--user-data-dir={profile}"], kill_exc=psutil.AccessDenied(301))
    ok = _FakeProc(302, "chrome", ["chrome", f"--user-data-dir={profile}"])
    _patch_procs(monkeypatch, [denied, ok])

    killed = _cleanup_zombie_chrome(profile)

    assert killed == 1, "AccessDenied는 카운트 제외, 정상 프로세스는 kill"
    assert ok.killed is True


def test_no_match_returns_zero(tmp_path, monkeypatch):
    """프로필 미점유 시 kill 0회, 예외 없음."""
    profile = tmp_path / "p"
    profile.mkdir()
    _patch_procs(monkeypatch, [_FakeProc(401, "chrome", ["chrome", "--user-data-dir=/somewhere/else"])])

    assert _cleanup_zombie_chrome(profile) == 0


def test_singleton_lock_unlinked(tmp_path, monkeypatch):
    """POSIX SingletonLock 잔재는 청소 후 제거 (Windows에선 부재라 no-op)."""
    profile = tmp_path / "p"
    profile.mkdir()
    lock = profile / "SingletonLock"
    lock.write_text("stale")
    _patch_procs(monkeypatch, [])

    _cleanup_zombie_chrome(profile)

    assert not lock.exists(), "stale SingletonLock이 unlink 되어야 함"


def test_missing_singleton_lock_no_error(tmp_path, monkeypatch):
    """SingletonLock 부재 시 unlink(missing_ok=True)로 무예외 (Windows 상시 케이스)."""
    profile = tmp_path / "p"
    profile.mkdir()
    _patch_procs(monkeypatch, [])

    # 예외 없이 완료되어야 함
    assert _cleanup_zombie_chrome(profile) == 0


def test_process_iter_failure_is_fail_open(tmp_path, monkeypatch):
    """psutil.process_iter 자체가 터져도 auth 흐름을 깨지 않음 (fail-open)."""
    profile = tmp_path / "p"
    profile.mkdir()

    def boom(*a, **kw):
        raise RuntimeError("psutil exploded")

    monkeypatch.setattr(psutil, "process_iter", boom)

    # 예외를 삼키고 0 반환 (SingletonLock 청소는 여전히 시도)
    assert _cleanup_zombie_chrome(profile) == 0


def test_launch_chrome_process_invokes_cleanup(tmp_path, monkeypatch):
    """launch_chrome_process 진입 시 _cleanup_zombie_chrome이 호출되는지 배선 검증."""
    calls = []
    monkeypatch.setattr(cdp_module, "get_chrome_path", lambda: None)  # 이후 즉시 return None
    monkeypatch.setattr(cdp_module, "get_chrome_profile_dir", lambda *a, **kw: tmp_path)
    monkeypatch.setattr(cdp_module, "_cleanup_zombie_chrome", lambda p: calls.append(p))

    # get_chrome_path None이라 launch는 None 반환하지만, 그 전에 cleanup 호출돼야 함.
    # 단, cleanup 배선은 profile_dir 확보 직후 → get_chrome_path None이면 그 전에 return.
    # 실제 코드 순서: chrome_path 확인 → profile_dir → cleanup. 따라서 chrome_path 존재 필요.
    monkeypatch.setattr(cdp_module, "get_chrome_path", lambda: "/fake/chrome")
    monkeypatch.setattr(
        cdp_module.subprocess, "Popen", lambda *a, **kw: (_ for _ in ()).throw(OSError("no launch"))
    )

    cdp_module.launch_chrome_process(port=9299, profile_name="default")

    assert calls, "launch_chrome_process가 _cleanup_zombie_chrome을 호출해야 함"
    assert os.fspath(calls[0]) == os.fspath(tmp_path)
