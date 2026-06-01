"""배치3 ATOM-5 — _reconcile_source + add_text/drive/url 분기 회귀 가드.

upstream 31df628 + 세션342 ADR 가드 융합. RPC code 3/9 발생 시 source 목록
폴링으로 false-negative 해소. 한도 임계 노트북은 polling 스킵 (Fail-fast).

본 테스트가 깨지면:
- accepted-pending false-negative이 raise되어 호출자가 중복 submission
- 한도 임계 노트북에서 매번 7초+ 지연 안티패턴 회귀
- atomic=True 흐름과의 상태 꼬임 가능성
"""

import threading
from unittest.mock import MagicMock, patch

import httpx
import pytest

from notebooklm_tools.core.errors import RPCError
from notebooklm_tools.core.sources import SOURCE_LIMIT_GUARD, SourceMixin

NOTEBOOK_ID = "nb-test-001"
MOCK_SOURCE_RESPONSE = [[[["src-id-success"], "Title", None, None]]]


def _make_client(sources=None) -> SourceMixin:
    """SourceMixin minimal client. sources: get_notebook_sources_with_types 반환값."""
    with patch.object(SourceMixin, "__init__", lambda self: None):
        client = SourceMixin()
    client._source_rpc_version = None
    client._state_lock = threading.Lock()
    client._call_rpc = MagicMock(return_value=MOCK_SOURCE_RESPONSE)
    client.get_notebook_sources_with_types = MagicMock(return_value=sources or [])
    client.wait_for_source_ready = MagicMock(
        side_effect=lambda nb, sid, _t: {"id": sid, "title": "ready"}
    )
    return client


def _rpc_error(code: int) -> RPCError:
    return RPCError(message="test", error_code=code)


# ---------------------------------------------------------------------------
# (1-4) _reconcile_source 단위
# ---------------------------------------------------------------------------


def test_reconcile_match_on_first_poll():
    """1차 즉시 매칭."""
    client = _make_client(sources=[{"id": "x", "title": "hello"}])
    found = client._reconcile_source(NOTEBOOK_ID, match_fn=lambda s: s["title"] == "hello")
    assert found == {"id": "x", "title": "hello"}


def test_reconcile_match_on_second_poll_uses_exp_backoff():
    """1차 None, 2차 매치 — exp backoff time.sleep(1.0) 1회 호출."""
    client = _make_client()
    # 1차 빈 리스트, 2차 매치
    client.get_notebook_sources_with_types = MagicMock(
        side_effect=[[], [{"id": "y", "title": "match"}]]
    )
    with patch("notebooklm_tools.core.sources.time.sleep") as mock_sleep:
        found = client._reconcile_source(
            NOTEBOOK_ID, match_fn=lambda s: s.get("title") == "match"
        )
    assert found["id"] == "y"
    # 첫 backoff = 1.0 * 2^0 = 1.0
    mock_sleep.assert_called_once_with(1.0)


def test_reconcile_no_match_returns_none():
    """폴링 횟수 끝나도 매치 없으면 None."""
    client = _make_client(sources=[{"id": "wrong", "title": "other"}])
    with patch("notebooklm_tools.core.sources.time.sleep"):
        found = client._reconcile_source(NOTEBOOK_ID, match_fn=lambda s: False)
    assert found is None


def test_reconcile_handles_get_sources_exception():
    """get_notebook_sources_with_types가 예외 raise해도 silent — None 반환."""
    client = _make_client()
    client.get_notebook_sources_with_types = MagicMock(side_effect=httpx.NetworkError("oops"))
    with patch("notebooklm_tools.core.sources.time.sleep"):
        found = client._reconcile_source(NOTEBOOK_ID, match_fn=lambda s: True)
    assert found is None


# ---------------------------------------------------------------------------
# (5-6) 세션342 가드 — 한도 임계 노트북
# ---------------------------------------------------------------------------


def test_session342_guard_skips_poll_when_at_limit():
    """source 개수 ≥ SOURCE_LIMIT_GUARD 시 polling 자체 스킵 (time.sleep 0회)."""
    over_limit = [{"id": f"s{i}", "title": f"t{i}"} for i in range(SOURCE_LIMIT_GUARD)]
    client = _make_client(sources=over_limit)
    with patch("notebooklm_tools.core.sources.time.sleep") as mock_sleep:
        found = client._reconcile_source(NOTEBOOK_ID, match_fn=lambda s: False)
    assert found is None
    mock_sleep.assert_not_called()


def test_session342_guard_does_not_prevent_first_poll_match():
    """가드 hit 직전에 1차 polling에서 매치되면 정상 반환 (가드 미발동)."""
    sources = [{"id": "match-me", "title": "found"} for _ in range(SOURCE_LIMIT_GUARD + 10)]
    client = _make_client(sources=sources)
    with patch("notebooklm_tools.core.sources.time.sleep") as mock_sleep:
        found = client._reconcile_source(
            NOTEBOOK_ID, match_fn=lambda s: s.get("id") == "match-me"
        )
    assert found is not None
    mock_sleep.assert_not_called()  # 1차에서 매치하면 polling loop 미진입


# ---------------------------------------------------------------------------
# (7-9) add_text_source 분기
# ---------------------------------------------------------------------------


def test_add_text_source_code3_reconcile_match():
    """add_text_source: RPC code 3 → reconcile match → 정상 반환 (raise 없음)."""
    client = _make_client(sources=[{"id": "txt-1", "title": "my title"}])
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))
    result = client.add_text_source(NOTEBOOK_ID, text="hello", title="my title")
    assert result == {"id": "txt-1", "title": "my title"}


def test_add_text_source_code3_reconcile_none_raises():
    """add_text_source: RPC code 3 → reconcile None → 원본 RPCError raise."""
    client = _make_client(sources=[])
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))
    with patch("notebooklm_tools.core.sources.time.sleep"), pytest.raises(RPCError) as exc_info:
        client.add_text_source(NOTEBOOK_ID, text="hello", title="ghost")
    assert exc_info.value.error_code == 3


def test_add_text_source_code9_text_variant_retry_still_works():
    """기존 흐름 회귀 가드: code 9 + text variant retry는 그대로 유지."""
    client = _make_client(sources=[{"id": "txt-2", "title": "ok"}])
    # 첫 호출은 code 9 + variant 다름 → continue (variants가 2개일 때)
    # 본 테스트에서는 단순화 — text == normalized면 variants=[text] 1개라서
    # code 9에서 바로 reconcile 분기.
    client._call_rpc = MagicMock(side_effect=_rpc_error(9))
    result = client.add_text_source(NOTEBOOK_ID, text="hello", title="ok")
    assert result == {"id": "txt-2", "title": "ok"}


# ---------------------------------------------------------------------------
# (10) add_drive_source 분기
# ---------------------------------------------------------------------------


def test_add_drive_source_code3_reconcile_match():
    """add_drive_source: code 3 → drive_doc_id 매칭 → 정상 반환."""
    client = _make_client(
        sources=[{"id": "drive-1", "title": "doc", "drive_doc_id": "doc-id-xyz"}]
    )
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))
    result = client.add_drive_source(NOTEBOOK_ID, document_id="doc-id-xyz", title="doc")
    assert result == {"id": "drive-1", "title": "doc"}


# ---------------------------------------------------------------------------
# (11-12) add_url_source v1 fallback 분기
# ---------------------------------------------------------------------------


def test_add_url_source_v1_code3_reconcile_match_skips_v2():
    """v1 code 3 → reconcile match → v2 미호출 (중복 submission 차단)."""
    client = _make_client(sources=[{"id": "url-1", "title": "page", "url": "https://x.com"}])
    # v1은 raise, v2는 mock으로 추적
    client._add_url_source_v1 = MagicMock(side_effect=_rpc_error(3))
    client._add_url_source_v2 = MagicMock(return_value=MOCK_SOURCE_RESPONSE)
    result = client.add_url_source(NOTEBOOK_ID, url="https://x.com")
    assert result == {"id": "url-1", "title": "page"}
    client._add_url_source_v2.assert_not_called()


def test_add_url_source_v1_code3_reconcile_none_falls_back_to_v2():
    """v1 code 3 → reconcile None → v2 fallback 정상 호출 (기존 흐름 보존)."""
    client = _make_client(sources=[])
    client._add_url_source_v1 = MagicMock(side_effect=_rpc_error(3))
    client._add_url_source_v2 = MagicMock(return_value=MOCK_SOURCE_RESPONSE)
    client._parse_source_result = MagicMock(return_value={"id": "v2-1", "title": "v2"})
    with patch("notebooklm_tools.core.sources.time.sleep"):
        result = client.add_url_source(NOTEBOOK_ID, url="https://unknown.com")
    client._add_url_source_v2.assert_called_once()
    assert result == {"id": "v2-1", "title": "v2"}


# ---------------------------------------------------------------------------
# (13) 동명 title 가짜 매칭 한계 — 운영 주의 명시
# ---------------------------------------------------------------------------


def test_add_text_source_duplicate_title_false_positive_documented_limitation():
    """⚠️ 한계 명시: 기존 동명 title source 있으면 reconcile이 가짜 매칭.

    upstream 31df628도 동일 한계 수용. text source는 created_at 분리 어려움.
    본 테스트는 *한계가 존재함*을 명시적으로 박제 (운영 docstring + 본 가드).
    """
    # 기존에 동명 source가 있는 상태에서 add_text_source 호출
    existing = {"id": "old-source-id", "title": "duplicate title"}
    client = _make_client(sources=[existing])
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))

    # 새 source 등록 의도였으나 reconcile이 기존 source를 가짜 매칭 — 이게 한계
    result = client.add_text_source(NOTEBOOK_ID, text="new content", title="duplicate title")
    # 의도와 무관하게 기존 source를 반환 — *한계 명시*
    assert result == {"id": "old-source-id", "title": "duplicate title"}
    # 향후 강화 옵션: created_at 추가 매칭 (현재는 NLM API 미제공)


# ---------------------------------------------------------------------------
# (14) reconcile은 code 7/8/16 등에는 발동 안 함
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error_code", [7, 8, 16])
def test_real_error_codes_bypass_reconcile(error_code):
    """code 3/9 외의 진짜 에러(7=auth, 8=resource_exhausted, 16=unauth)는 즉시 raise."""
    client = _make_client(sources=[{"id": "x", "title": "anything"}])
    client._call_rpc = MagicMock(side_effect=_rpc_error(error_code))
    with pytest.raises(RPCError) as exc_info:
        client.add_text_source(NOTEBOOK_ID, text="t", title="anything")
    assert exc_info.value.error_code == error_code
    # get_notebook_sources_with_types 호출 0회 — reconcile 미진입
    client.get_notebook_sources_with_types.assert_not_called()
