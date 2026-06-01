"""배치2 ATOM-2 — debug log redaction 회귀 가드.

upstream cecd757 (v0.6.13 직전) 동형. 세션 쿠키(SID, HSID, SSID, APISID,
SAPISID, NID, __Secure-*) 값이 디버그 로그(NLM_MCP_DEBUG=1)에 평문으로
노출되지 않도록 정규식 마스킹.

본 테스트가 깨지면 디버그 로그/세션 캡쳐에 사용자 쿠키 평문 노출 회귀.
"""

import re
from pathlib import Path

# 본 테스트는 모듈 내부 redaction 정규식을 직접 검증 (mock 비용 회피).
# core/base.py 시공 코드와 동일한 패턴이어야 함 — 둘이 어긋나면 둘 다 회귀.
_REDACT_PATTERN = re.compile(
    r'"(SID|HSID|SSID|APISID|SAPISID|NID|__Secure-\w+)":\s*"[^"]*"'
)
_REDACT_REPLACEMENT = r'"\1":"[REDACTED]"'


def _apply_redaction(raw: str) -> str:
    return _REDACT_PATTERN.sub(_REDACT_REPLACEMENT, raw)


def test_redact_standard_session_cookies():
    """SID/HSID/SSID/APISID/SAPISID/NID 모두 마스킹."""
    raw = '{"SID":"abc123","HSID":"def","other":"keep","SSID":"ghi"}'
    out = _apply_redaction(raw)
    assert '"SID":"[REDACTED]"' in out
    assert '"HSID":"[REDACTED]"' in out
    assert '"SSID":"[REDACTED]"' in out
    assert '"other":"keep"' in out  # 비-민감 필드 무영향


def test_redact_secure_wildcard():
    """__Secure-1PSID 같은 와일드카드 쿠키 매칭."""
    raw = '{"__Secure-1PSID":"sensitive_value","__Secure-3PAPISID":"another"}'
    out = _apply_redaction(raw)
    assert '"__Secure-1PSID":"[REDACTED]"' in out
    assert '"__Secure-3PAPISID":"[REDACTED]"' in out
    assert "sensitive_value" not in out
    assert "another" not in out


def test_non_sensitive_fields_untouched():
    """일반 필드(title, status, url 등)는 영향 없음."""
    raw = '{"title":"hello","SID":"x","status":"ok"}'
    out = _apply_redaction(raw)
    assert '"title":"hello"' in out
    assert '"status":"ok"' in out
    assert '"SID":"[REDACTED]"' in out


def test_base_module_uses_same_pattern():
    """core/base.py 시공 코드와 회귀 가드 정규식 일치 확인 (실 코드 grep)."""
    from notebooklm_tools.core import base

    source = Path(base.__file__).read_text(encoding="utf-8")
    # 정규식 자체가 base.py 안에 있는지 확인
    assert 'SID|HSID|SSID|APISID|SAPISID|NID|__Secure-' in source, (
        "core/base.py에서 redaction 정규식이 사라짐 — 회귀"
    )
    assert "[REDACTED]" in source, "REDACTED 마스킹 토큰이 사라짐 — 회귀"


def test_conversation_raw_response_is_empty():
    """core/conversation.py raw_response가 빈 문자열로 비워짐."""
    from notebooklm_tools.core import conversation

    source = Path(conversation.__file__).read_text(encoding="utf-8")
    # 옛 패턴(`response.text[:1000]`)이 raw_response 필드에 직접 들어가면 회귀
    # raw_response 필드는 빈 문자열이어야 함
    assert '"raw_response": ""' in source, (
        "raw_response가 빈 문자열로 비워지지 않음 — 세션 데이터 노출 회귀"
    )
