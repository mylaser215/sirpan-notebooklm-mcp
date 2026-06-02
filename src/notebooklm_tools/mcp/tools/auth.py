"""Auth tools - Authentication management."""

import time
import urllib.parse

from ._utils import (
    ESSENTIAL_COOKIES,
    ResultDict,
    error_result,
    get_client,
    logged_tool,
    mcp_logger,
    reset_client,
)


@logged_tool()
def refresh_auth() -> ResultDict:
    """Reload auth tokens from disk or run headless re-authentication.

    Call this after running `nlm login` to pick up new tokens,
    or to attempt automatic re-authentication if Chrome profile has saved login.

    Returns status indicating if tokens were refreshed successfully.
    """
    try:
        from notebooklm_tools.core.auth import _is_rts_expiring, load_cached_tokens

        # When Google RTS (10-min rotating token) has expired, disk reload alone
        # returns stale cookies and falsely reports success. Headless re-auth is
        # the only path that can actually recover. Try it first, then fail-close
        # if headless also fails (no stale-fallback to disk cache).
        if _is_rts_expiring():
            headless_failure: str | None = None
            try:
                from notebooklm_tools.utils.cdp import run_headless_auth

                tokens = run_headless_auth()
                if tokens:
                    reset_client()
                    get_client()
                    mcp_logger.info("RTS token expired. Refreshed via headless auth.")
                    return {
                        "status": "success",
                        "message": "RTS rotated. Auth refreshed via headless Chrome.",
                    }
                headless_failure = "headless auth returned no tokens"
            except Exception as e:
                headless_failure = f"{type(e).__name__}: {e}"
                mcp_logger.warning(
                    f"Headless auth on RTS rotation failed: {headless_failure}"
                )

            # Fail-close: do NOT fall through to stale disk reload when RTS has
            # rotated. Returning a false "success" with expired tokens misleads
            # callers into believing auth is recovered.
            return {
                "status": "error",
                "error": (
                    "RTS token expired and headless auth failed. "
                    "Run '! nlm login' manually."
                ),
                "hint": (
                    "Foreground `nlm login` (5-10s) is the reliable recovery path. "
                    f"Headless failure: {headless_failure}"
                ),
            }

        # RTS healthy: disk reload is meaningful. Guard with _is_rts_expiring()
        # to defend against TOCTOU races where rotation occurs between the
        # initial check and load_cached_tokens().
        cached = load_cached_tokens()
        if cached and cached.cookies and not _is_rts_expiring():
            reset_client()
            get_client()

            # 세션58 ATOM-2 (upstream eadb8c3 #212): live HTTP 검증 layer.
            # 우리 fork `bbae413` RTS fail-close와 직교 방어 (NLM Q3 ●●●):
            # - RTS 가드는 *예측 가능* 10분 만료 차단 (O(1))
            # - 본 layer는 *예측 불가* 외부 로그아웃 / Google 측 세션 무효화
            #   (RTS 미만료 윈도우 내 거짓 success) 차단
            from notebooklm_tools.core.auth import check_auth

            check = check_auth(live=True)
            if not check.valid:
                return error_result(
                    "Auth tokens were reloaded from disk but are no longer valid "
                    f"(reason: {check.reason}). A disk reload cannot revive expired "
                    "credentials — run `nlm login` in a terminal to re-authenticate.",
                    status="expired",
                    reason=check.reason,
                )
            return {
                "status": "success",
                "message": "Auth tokens reloaded from disk cache and validated.",
            }

        # No cache (or RTS rotated mid-call): try headless auth if Chrome profile exists
        try:
            from notebooklm_tools.utils.cdp import run_headless_auth

            tokens = run_headless_auth()
            if tokens:
                reset_client()
                get_client()
                return {
                    "status": "success",
                    "message": "Auth tokens refreshed via headless Chrome.",
                }
        except Exception as e:
            mcp_logger.warning(f"Headless auth (no-cache path) failed: {e}")

        return {
            "status": "error",
            "error": "No valid cached tokens. Run '! nlm login' to authenticate.",
        }
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def save_auth_tokens(
    cookies: str,
    csrf_token: str = "",
    session_id: str = "",
    request_body: str = "",
    request_url: str = "",
) -> ResultDict:
    """Save NotebookLM cookies (FALLBACK method - try `nlm login` first!).

    IMPORTANT FOR AI ASSISTANTS:
    - First, run `nlm login` via Bash/terminal (automated, preferred)
    - Only use this tool if the automated CLI fails

    Args:
        cookies: Cookie header from Chrome DevTools (only needed if CLI fails)
        csrf_token: Deprecated - auto-extracted
        session_id: Deprecated - auto-extracted
        request_body: Optional - contains CSRF if extracting manually
        request_url: Optional - contains session ID if extracting manually
    """
    try:
        from notebooklm_tools.core.auth import AuthTokens, get_cache_path, save_tokens_to_cache

        # Parse cookie string to dict
        all_cookies = {}
        for part in cookies.split("; "):
            if "=" in part:
                key, value = part.split("=", 1)
                # 배치2 ATOM-1 (upstream f2fb921): cookie 헤더 앞뒤 공백 처리
                all_cookies[key.strip()] = value

        # Validate required cookies
        required = ["SID", "HSID", "SSID", "APISID", "SAPISID"]
        missing = [c for c in required if c not in all_cookies]
        if missing:
            return {
                "status": "error",
                "error": f"Missing required cookies: {missing}",
            }

        # Filter to only essential cookies
        cookie_dict = {k: v for k, v in all_cookies.items() if k in ESSENTIAL_COOKIES}

        # Try to extract CSRF token from request body if provided
        if not csrf_token and request_body and "at=" in request_body:
            at_part = request_body.split("at=")[1].split("&")[0]
            csrf_token = urllib.parse.unquote(at_part)

        # Try to extract session ID from request URL if provided
        if not session_id and request_url and "f.sid=" in request_url:
            sid_part = request_url.split("f.sid=")[1].split("&")[0]
            session_id = urllib.parse.unquote(sid_part)

        # Try to extract build label from request URL if provided
        build_label = ""
        if request_url and "bl=" in request_url:
            bl_part = request_url.split("bl=")[1].split("&")[0]
            build_label = urllib.parse.unquote(bl_part)

        # Create and save tokens
        tokens = AuthTokens(
            cookies=cookie_dict,
            csrf_token=csrf_token,
            session_id=session_id,
            build_label=build_label,
            extracted_at=time.time(),
        )
        save_tokens_to_cache(tokens)

        # Reset client so next call uses fresh tokens
        reset_client()

        # Build status message
        if csrf_token and session_id:
            token_msg = "CSRF token and session ID extracted from network request - no page fetch needed! ⚡"
        elif csrf_token:
            token_msg = "CSRF token extracted from network request. Session ID will be auto-extracted on first use."
        elif session_id:
            token_msg = "Session ID extracted from network request. CSRF token will be auto-extracted on first use."
        else:
            token_msg = "CSRF token and session ID will be auto-extracted on first API call (~1-2s one-time delay)."

        return {
            "status": "success",
            "message": f"Saved {len(cookie_dict)} essential cookies (filtered from {len(all_cookies)}). {token_msg}",
            "cache_path": str(get_cache_path()),
            "extracted_csrf": bool(csrf_token),
            "extracted_session_id": bool(session_id),
        }
    except Exception as e:
        return error_result(str(e))
