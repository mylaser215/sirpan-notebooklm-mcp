"""배치3 ATOM-5 — import_research_sources reconcile + 세션46 slot_0 회귀 가드.

upstream 31df628 + 세션46 LBwxtb slot_0 envelope 보존 + 세션342 가드 inline.

본 테스트가 깨지면:
- research import false-negative이 raise되어 41→38 잔존 사고 회귀
- 세션46 LBwxtb slot_0 envelope 변경 시 import 자체 깨짐
- 한도 임계 노트북에서 매번 7s+ 지연 안티패턴 회귀
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from notebooklm_tools.core.errors import RPCError
from notebooklm_tools.core.research import ResearchMixin
from notebooklm_tools.core.sources import SOURCE_LIMIT_GUARD

NOTEBOOK_ID = "nb-research-001"
TASK_ID = "task-001"


def _make_client(pre_sources=None, post_sources=None) -> ResearchMixin:
    """ResearchMixin minimal client. pre_sources: 사전 snapshot 반환, post_sources: code 3 후 폴링."""
    with patch.object(ResearchMixin, "__init__", lambda self: None):
        client = ResearchMixin()
    client._state_lock = threading.Lock()
    client._call_rpc = MagicMock(return_value=[[[["src-success"], "Title", None]]])
    # get_notebook_sources_with_types는 1차 pre snapshot + 이후 폴링 시퀀스
    if post_sources is None:
        client.get_notebook_sources_with_types = MagicMock(return_value=pre_sources or [])
    else:
        client.get_notebook_sources_with_types = MagicMock(
            side_effect=[pre_sources or []] + ([post_sources] * 3)
        )
    return client


def _rpc_error(code: int) -> RPCError:
    return RPCError(message="test", error_code=code)


# ---------------------------------------------------------------------------
# (14-15) code 3 + 새 source 1건 / 0건
# ---------------------------------------------------------------------------


def test_research_import_code3_with_new_source_returns_it():
    """code 3 발생 → 사후 폴링에서 신규 source 1건 발견 → 정상 반환."""
    pre = [{"id": "old-1", "title": "existing"}]
    post = [
        {"id": "old-1", "title": "existing"},
        {"id": "new-1", "title": "imported"},
    ]
    client = _make_client(pre_sources=pre, post_sources=post)
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))

    with patch("notebooklm_tools.core.research.time.sleep"):
        result = client.import_research_sources(
            NOTEBOOK_ID, TASK_ID, [{"url": "https://x.com", "title": "t", "result_type": 1}]
        )
    assert result == [{"id": "new-1", "title": "imported"}]


def test_research_import_code3_no_new_sources_raises():
    """code 3 + 폴링 결과 신규 source 0건 → 원본 RPCError raise."""
    pre = [{"id": "old-1", "title": "existing"}]
    post = pre  # 동일
    client = _make_client(pre_sources=pre, post_sources=post)
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))

    with (
        patch("notebooklm_tools.core.research.time.sleep"),
        pytest.raises(RPCError) as exc_info,
    ):
        client.import_research_sources(
            NOTEBOOK_ID, TASK_ID, [{"url": "https://x.com", "title": "t", "result_type": 1}]
        )
    assert exc_info.value.error_code == 3


# ---------------------------------------------------------------------------
# (16) 진짜 에러는 reconcile 미발동
# ---------------------------------------------------------------------------


def test_research_import_code7_auth_raises_immediately():
    """code 7 (auth) → reconcile 미발동, 즉시 raise."""
    client = _make_client(pre_sources=[])
    client._call_rpc = MagicMock(side_effect=_rpc_error(7))
    with pytest.raises(RPCError) as exc_info:
        client.import_research_sources(
            NOTEBOOK_ID, TASK_ID, [{"url": "https://x.com", "title": "t", "result_type": 1}]
        )
    assert exc_info.value.error_code == 7


# ---------------------------------------------------------------------------
# (17) 세션46 LBwxtb slot_0 envelope 회귀 가드
# ---------------------------------------------------------------------------


def test_session46_slot_0_envelope_preserved():
    """세션46 박제: slot_0 = [2, None, None, [1, None×9, [1]]] 변경 절대 금지."""
    client = _make_client(pre_sources=[])
    client._call_rpc = MagicMock(return_value=[[]])  # 성공 케이스 (reconcile 미진입)

    client.import_research_sources(
        NOTEBOOK_ID, TASK_ID, [{"url": "https://x.com", "title": "t", "result_type": 1}]
    )

    # _call_rpc 첫 인자 = params, params[0] = slot_0
    call_args = client._call_rpc.call_args
    params = call_args[0][1]  # positional: (rpc_id, params, path, ...)
    slot_0 = params[0]
    expected = [2, None, None, [1, None, None, None, None, None, None, None, None, None, [1]]]
    assert slot_0 == expected, f"slot_0 envelope 회귀: {slot_0}"


# ---------------------------------------------------------------------------
# (18) 세션342 가드 inline — pre_sources ≥ SOURCE_LIMIT_GUARD 시 즉시 raise
# ---------------------------------------------------------------------------


def test_session342_guard_inline_when_at_limit_raises_immediately():
    """pre snapshot이 한도 임계면 reconcile 폴링 스킵 + 원본 raise."""
    over_limit = [{"id": f"s{i}", "title": f"t{i}"} for i in range(SOURCE_LIMIT_GUARD)]
    client = _make_client(pre_sources=over_limit)
    client._call_rpc = MagicMock(side_effect=_rpc_error(3))

    with (
        patch("notebooklm_tools.core.research.time.sleep") as mock_sleep,
        pytest.raises(RPCError) as exc_info,
    ):
        client.import_research_sources(
            NOTEBOOK_ID,
            TASK_ID,
            [{"url": "https://x.com", "title": "t", "result_type": 1}],
        )

    assert exc_info.value.error_code == 3
    mock_sleep.assert_not_called()  # 가드 hit으로 polling 스킵
