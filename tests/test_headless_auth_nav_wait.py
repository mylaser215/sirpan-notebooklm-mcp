"""run_headless_auth 네비게이션 대기 회귀 가드 (세션73).

근본원인 (라이브 통제실험 2/2 재현 + NLM ●●● conv 803fdca1):
    갓 띄운 headless Chrome은 페이지 생성 직후 ~1-3s 동안 about:blank를 보고한다.
    run_headless_auth가 대기 없이 is_logged_in(get_current_url())을 즉시 검사하면
    항상 False → return None → 자동 재인증이 결정론적으로 실패, 수동 nlm login 강제.

본 테스트가 깨지면 그 결정론적 실패가 회귀한다. ATOM-1(네비 대기 폴링)과
ATOM-2(신선 쿠키를 프로필에 병렬 저장 — split-brain 방어)를 함께 가드한다.
"""

import notebooklm_tools.core.auth as auth_mod
from notebooklm_tools.utils import cdp as cdp_module

_REQUIRED = ["SID", "HSID", "SSID", "APISID", "SAPISID"]


def _valid_cookie_list():
    """validate_cookies를 통과하는 최소 쿠키 리스트 (expires 메타 포함)."""
    lst = [{"name": n, "value": f"{n}-val", "expires": 9999999999} for n in _REQUIRED]
    lst.append({"name": "__Secure-1PSIDRTS", "value": "rts", "expires": 9999999999})
    return lst


class _FakeManager:
    """AuthManager 스텁 — save_profile 인자만 포착."""

    def __init__(self):
        self.saved = None

    def save_profile(self, cookies, **kw):
        self.saved = {"cookies": cookies, "kw": kw}


def _wire_common(monkeypatch, url_sequence):
    """run_headless_auth 내부 의존을 모킹. url_sequence는 get_current_url 반환 순서."""
    monkeypatch.setattr(cdp_module, "has_chrome_profile", lambda *a, **k: True)
    # get_debugger_url 진입 시 truthy → chrome_was_running=True (launch/terminate 스킵)
    monkeypatch.setattr(cdp_module, "get_debugger_url", lambda *a, **k: "ws://127.0.0.1:9223/x")
    monkeypatch.setattr(
        cdp_module,
        "find_or_create_notebooklm_page",
        lambda *a, **k: {"webSocketDebuggerUrl": "ws://127.0.0.1:9223/page"},
    )
    monkeypatch.setattr(cdp_module, "get_page_cookies", lambda *a, **k: _valid_cookie_list())
    monkeypatch.setattr(cdp_module, "get_page_html", lambda *a, **k: "<html>SNlM0e</html>")
    monkeypatch.setattr(cdp_module, "extract_csrf_token", lambda *a, **k: "csrf")
    monkeypatch.setattr(cdp_module, "extract_session_id", lambda *a, **k: "sid")
    monkeypatch.setattr(cdp_module, "extract_email", lambda *a, **k: "user@example.com")
    monkeypatch.setattr(cdp_module, "extract_build_label", lambda *a, **k: "bl")
    monkeypatch.setattr(cdp_module, "cleanup_chrome_profile_cache", lambda *a, **k: 0)
    monkeypatch.setattr(cdp_module, "terminate_chrome", lambda *a, **k: True)
    # core.auth 내부 import 대상 — 프로필 저장 스텁, auth.json 저장 no-op
    fake_mgr = _FakeManager()
    monkeypatch.setattr(auth_mod, "get_auth_manager", lambda *a, **k: fake_mgr)
    monkeypatch.setattr(auth_mod, "save_tokens_to_cache", lambda *a, **k: None)

    # get_current_url: 순서대로 반환 후 마지막 값 고정
    seq = list(url_sequence)

    def _next_url(*a, **k):
        return seq.pop(0) if len(seq) > 1 else seq[0]

    monkeypatch.setattr(cdp_module, "get_current_url", _next_url)
    return fake_mgr


def test_immediate_about_blank_does_not_abort(monkeypatch):
    """about:blank → notebooklm 순서로 정착하면 None이 아니라 tokens 반환 (핵심 재현 방어)."""
    _wire_common(monkeypatch, ["about:blank", "about:blank", "https://notebooklm.google.com/"])
    tokens = cdp_module.run_headless_auth(port=9223)
    assert tokens is not None, "about:blank 이후 정착했는데 None 반환 = 근본버그 회귀"
    assert tokens.csrf_token == "csrf"


def test_profile_persisted_on_success(monkeypatch):
    """성공 시 전체 쿠키 list가 프로필에 저장돼야 함 (ATOM-2 split-brain 방어)."""
    fake_mgr = _wire_common(monkeypatch, ["about:blank", "https://notebooklm.google.com/"])
    tokens = cdp_module.run_headless_auth(port=9223)
    assert tokens is not None
    assert fake_mgr.saved is not None, "save_profile 미호출 = split-brain 회귀"
    assert isinstance(fake_mgr.saved["cookies"], list), "프로필 저장은 list(expires 포함)여야 함"
    assert any(c["name"] == "__Secure-1PSIDRTS" for c in fake_mgr.saved["cookies"])


def test_early_exit_on_accounts_google(monkeypatch):
    """accounts.google.com(진짜 미로그인)이면 대기 소진 없이 빠르게 None."""
    _wire_common(monkeypatch, ["about:blank", "https://accounts.google.com/signin"])
    tokens = cdp_module.run_headless_auth(port=9223)
    assert tokens is None, "세션 사망 시 headless는 복구 불가 → None"


def test_get_current_url_exception_is_fail_open(monkeypatch):
    """네비 중 get_current_url 예외가 나도 죽지 않고 다음 폴에서 성공해야 함 (fail-open)."""
    calls = {"n": 0}

    def _flaky_wire():
        fake_mgr = _wire_common(monkeypatch, ["https://notebooklm.google.com/"])
        return fake_mgr

    fake_mgr = _flaky_wire()

    real_seq = [RuntimeError("cdp hiccup"), "https://notebooklm.google.com/"]

    def _url(*a, **k):
        v = real_seq[min(calls["n"], len(real_seq) - 1)]
        calls["n"] += 1
        if isinstance(v, Exception):
            raise v
        return v

    monkeypatch.setattr(cdp_module, "get_current_url", _url)
    tokens = cdp_module.run_headless_auth(port=9223)
    assert tokens is not None, "예외 후 정착했는데 None = fail-open 회귀"
