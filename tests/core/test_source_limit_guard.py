"""배치3 ATOM-5 — SOURCE_LIMIT_GUARD 환경변수 오버라이드 회귀 가드.

세션342 ADR: NLM Pro 한도 통상 300, 마진 10 → default 290. 운영자 오버라이드는
NOTEBOOKLM_SOURCE_LIMIT_GUARD 환경변수.

본 테스트가 깨지면 한도 변경 시 운영자가 코드 수정 강제됨 (인지 부담 증가).
"""

import importlib


def test_env_var_overrides_default_guard(monkeypatch):
    """NOTEBOOKLM_SOURCE_LIMIT_GUARD=100 환경변수로 default 290 오버라이드."""
    monkeypatch.setenv("NOTEBOOKLM_SOURCE_LIMIT_GUARD", "100")
    # 모듈 reload로 module-level 상수 재평가
    import notebooklm_tools.core.sources as sources_module

    importlib.reload(sources_module)
    assert sources_module.SOURCE_LIMIT_GUARD == 100

    # cleanup — 다른 테스트에 영향 X
    monkeypatch.delenv("NOTEBOOKLM_SOURCE_LIMIT_GUARD", raising=False)
    importlib.reload(sources_module)
    assert sources_module.SOURCE_LIMIT_GUARD == 290
