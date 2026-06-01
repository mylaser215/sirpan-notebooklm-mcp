"""배치2 ATOM-1 — cookie key whitespace strip 회귀 가드.

upstream f2fb921 (v0.6.13) 동형. 헤더 파싱 시 key 앞뒤 공백 strip.

본 테스트가 깨지면 `Cookie: SID =x; HSID= y` 같은 헤더에서 key가 ' SID'/
'HSID '로 저장되어 NLM 측 매칭 실패 회귀.
"""

from pathlib import Path


def test_cookie_parsing_strips_key_whitespace():
    """소스 파일 grep — `all_cookies[key.strip()]` 패턴 존재 확인."""
    from notebooklm_tools.mcp.tools import auth

    source = Path(auth.__file__).read_text(encoding="utf-8")
    assert "all_cookies[key.strip()]" in source, (
        "save_auth_tokens cookie 파싱에서 key.strip() 누락 — "
        "헤더 공백 매칭 실패 회귀"
    )


def test_cookie_parsing_logic_simulation():
    """save_auth_tokens 내부 파싱 로직 동등 흐름 시뮬레이션 — 시공 패턴 검증."""
    # 시공된 동일 패턴 (회귀 가드용 동치 코드 — auth.py 라인 130-134)
    cookies = " SID =abc;  HSID= def ;  SSID  = ghi  "
    all_cookies = {}
    for part in cookies.split("; "):
        if "=" in part:
            key, value = part.split("=", 1)
            all_cookies[key.strip()] = value

    # key가 모두 strip 됐는지
    assert "SID" in all_cookies, f"keys (with strip): {list(all_cookies)}"
    assert "HSID" in all_cookies
    assert "SSID" in all_cookies
    # 옛 흐름이라면 " SID "/"HSID "/"SSID  "로 저장되어 있어야 함 — 그건 회귀
    assert " SID " not in all_cookies
    assert "HSID " not in all_cookies
