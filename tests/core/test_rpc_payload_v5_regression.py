"""v5 결함 회귀 방지 — 9개 RPC payload baseline 가드.

본 세션(260512) Chrome DevTools 라이브 캡쳐 19장으로 NLM 웹 실측 baseline 확보.
v4 결함(`_register_file_source` 4-slot → 3-slot+nested)과 동일 패턴이 다른 RPC에도 잠복.

각 테스트는 *NLM 웹 실측 baseline*을 박제 — 코드가 옛 구조로 회귀하면 fail.
v4 reference 패턴(`tests/core/test_sources.py:562`)과 동일 스타일.

NLM 도메인 통합 발견 (260512):
- `R7cb6c` = RPC_CREATE_STUDIO = (신) generate_mind_map RPC
- `V5N4be` = RPC_DELETE_STUDIO = (신) delete_mind_map RPC
- `CYK0Xb` = RPC_CREATE_NOTE = (구) save_mind_map (NLM 자동 저장 도입으로 deprecated)
"""

from unittest.mock import MagicMock

import pytest


# v4 nested 표준 옵션 — 본 세션 캡쳐로 universal 아닌 RPC별 패턴임 확인됨
V4_NESTED_OPTS = [1, None, None, None, None, None, None, None, None, None, None, [1]]
# 마인드맵·스튜디오 도메인 전용 추가 옵션
MIND_MAP_EXTRA_OPTS = [[1, 4, 2, 3, 6]]


def _make_mock_client(rpc_const_name: str, rpc_id: str):
    """공통 mock 클라이언트 — captured dict로 _call_rpc 파라미터 박제."""
    client = MagicMock()
    setattr(client, rpc_const_name, rpc_id)
    captured: dict = {}

    def fake_call_rpc(rpc_name, params, path=None, **kw):
        captured["rpc"] = rpc_name
        captured["params"] = params
        captured["path"] = path
        return []  # Empty list; downstream parsing returns empty/None

    client._call_rpc = fake_call_rpc
    return client, captured


# =============================================================================
# ATOM-1: list_notebooks (wXbhsf) — slot4 nested
# =============================================================================
def test_list_notebooks_payload_v5_regression():
    """v5 결함 회귀 — list_notebooks slot4 = v4 nested 표준.

    NLM 웹 baseline: `[null, 1, null, [2, null, null, [1, null×10, [1]]]]`
    회귀 시: slot4 = `[2]` flat → NLM 옵션(필드 풀버전 등) 누락 가능.
    """
    from notebooklm_tools.core.notebooks import NotebookMixin

    client, captured = _make_mock_client("RPC_LIST_NOTEBOOKS", "wXbhsf")
    NotebookMixin.list_notebooks(client)

    assert captured["rpc"] == "wXbhsf"
    expected = [None, 1, None, [2, None, None, V4_NESTED_OPTS]]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: slot4 nested 누락. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )


# =============================================================================
# ATOM-2: get_notebook (rLM1Ne) — 3-slot + nested
# =============================================================================
def test_get_notebook_payload_v5_regression():
    """v5 결함 회귀 — get_notebook 3-slot 구조 (5-slot flat 회귀 방지).

    NLM 웹 baseline: `[id, null, [2, null, null, null, null, null, [1]]]`
    회귀 시: `[id, null, [2], null, 0]` 5-slot flat → 필드 누락 또는 잘못된 변환.
    """
    from notebooklm_tools.core.notebooks import NotebookMixin

    client, captured = _make_mock_client("RPC_GET_NOTEBOOK", "rLM1Ne")
    NotebookMixin.get_notebook(client, "test-notebook-id")

    assert captured["rpc"] == "rLM1Ne"
    expected = ["test-notebook-id", None, [2, None, None, None, None, None, [1]]]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: get_notebook 3-slot 구조 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )
    assert captured["path"] == "/notebook/test-notebook-id"


# =============================================================================
# ATOM-3: create_notebook (CCqFvf) — 4-slot, slot4 nested
# =============================================================================
def test_create_notebook_payload_v5_regression():
    """v5 결함 회귀 — create_notebook 4-slot (slot4 nested) 구조.

    NLM 웹 baseline: `[title, null, null, [2, null, null, [1, null×10, [1]]]]`
    회귀 시: 5-slot으로 slot4·slot5 분리 → slot5 옵션이 다른 의미로 해석될 위험.
    """
    from notebooklm_tools.core.notebooks import NotebookMixin

    client, captured = _make_mock_client("RPC_CREATE_NOTEBOOK", "CCqFvf")
    NotebookMixin.create_notebook(client, "Test Title")

    assert captured["rpc"] == "CCqFvf"
    expected = ["Test Title", None, None, [2, None, None, V4_NESTED_OPTS]]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: create_notebook 4-slot+nested 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )


# =============================================================================
# ATOM-4: set_public_access (QDyure) — slot4 nested + slot1 내 [access_code, 0]
# =============================================================================
def test_set_public_access_payload_v5_regression():
    """v5 결함 회귀 — set_public_access slot4 nested + slot1 내 access_pair.

    NLM 웹 baseline: `[[[id, null, [1, 0], [0, ""]]], 1, null, [2, null, null, [1, null×10, [1]]]]`
    회귀 시: slot4 `[2]` flat 또는 slot1 내 `[access_code]` (단일 요소).
    """
    from notebooklm_tools.core.sharing import SharingMixin

    client, captured = _make_mock_client("RPC_SHARE_NOTEBOOK", "QDyure")
    client.SHARE_ACCESS_PUBLIC = 1
    client.SHARE_ACCESS_RESTRICTED = 0
    client._get_base_url = lambda: "https://notebooklm.google.com"

    SharingMixin.set_public_access(client, "test-id", is_public=True)

    assert captured["rpc"] == "QDyure"
    expected = [
        [["test-id", None, [1, 0], [0, ""]]],
        1,
        None,
        [2, None, None, V4_NESTED_OPTS],
    ]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: set_public_access slot4 nested + slot1 access_pair 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )


# =============================================================================
# ATOM-5: add_collaborator (QDyure) — slot4 nested + slot1 내 [0, 0] 추가
# =============================================================================
def test_add_collaborator_payload_v5_regression():
    """v5 결함 회귀 — add_collaborator slot4 nested + slot1 내 3번째 element [0, 0].

    NLM 웹 baseline: `[[[id, [[email, null, 3]], [0, 0], [notify_flag, msg]]], 1, null, [2, null, null, [1, null×10, [1]]]]`
    회귀 시: slot1 내 3번째가 None → notify 정책이 디폴트로 떨어짐.
    """
    from notebooklm_tools.core import constants
    from notebooklm_tools.core.sharing import SharingMixin

    client, captured = _make_mock_client("RPC_SHARE_NOTEBOOK", "QDyure")
    # constants.SHARE_ROLES.get_code("viewer") returns 3 in current codebase
    # constants.SHARE_ROLE_OWNER guard

    SharingMixin.add_collaborator(client, "test-id", "user@example.com", role="viewer", notify=True)

    assert captured["rpc"] == "QDyure"
    role_code = constants.SHARE_ROLES.get_code("viewer")
    expected = [
        [["test-id", [["user@example.com", None, role_code]], [0, 0], [0, ""]]],
        1,
        None,
        [2, None, None, V4_NESTED_OPTS],
    ]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: add_collaborator slot4 nested + slot1 [0,0] 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )


# =============================================================================
# ATOM-6: start_research_fast (Ljjv0c) — slot2 nested
# =============================================================================
def test_start_research_fast_payload_v5_regression():
    """v5 결함 회귀 — start_research_fast slot2 nested.

    NLM 웹 baseline: `[[query, 1], [2, null, null, [1, null×10, [1]]], 1, notebook_id]`
    회귀 시: slot2 = `None` → 검색 옵션 누락 (결과 품질 차이).
    """
    from notebooklm_tools.core.research import ResearchMixin

    client, captured = _make_mock_client("RPC_START_FAST_RESEARCH", "Ljjv0c")
    client.RPC_START_DEEP_RESEARCH = "QA9ei"
    client.RESEARCH_SOURCE_WEB = 1
    client.RESEARCH_SOURCE_DRIVE = 2

    ResearchMixin.start_research(
        client, "test-nb-id", "test query", source="web", mode="fast"
    )

    assert captured["rpc"] == "Ljjv0c"
    expected = [["test query", 1], [2, None, None, V4_NESTED_OPTS], 1, "test-nb-id"]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: start_research_fast slot2 nested 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )
    assert captured["path"] == "/notebook/test-nb-id"


# =============================================================================
# ATOM-7: generate_mind_map (R7cb6c) — RPC ID 변경 + 9-slot 재설계
# =============================================================================
def test_generate_mind_map_payload_v5_regression():
    """v5 결함 회귀 — generate_mind_map RPC ID 갱신 + 9-slot 구조.

    이전 결함: RPC `yyryJe` (stale, NLM에서 변경됨) + params 6-slot 단순 구조.
    NLM 웹 baseline: RPC `R7cb6c` + 9-slot params.
    회귀 시: 마인드맵 생성 실패 또는 NLM 자동 저장 누락 + sources 라우팅 오류.

    NLM 도메인 통합 발견: R7cb6c = RPC_CREATE_STUDIO (마인드맵 ⊂ studio).
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_mock_client("RPC_GENERATE_MIND_MAP", "R7cb6c")
    client._get_all_source_ids = lambda nb_id: ["src-1", "src-2"]

    StudioMixin.generate_mind_map(client, "test-nb-id", source_ids=["src-1", "src-2"])

    assert captured["rpc"] == "R7cb6c", (
        f"v5 결함 회귀: generate_mind_map RPC ID. 기대 'R7cb6c', got {captured['rpc']!r}"
    )
    expected = [
        [2, None, None, V4_NESTED_OPTS, MIND_MAP_EXTRA_OPTS],
        "test-nb-id",
        [None, None, 4, [[["src-1"], ["src-2"]]]],
        None,
        None,
        None,
        None,
        None,
        [None, [4]],
    ]
    assert captured["params"] == expected, (
        f"v5 결함 회귀: generate_mind_map 9-slot 구조 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )


# =============================================================================
# ATOM-8: delete_mind_map UUID (V5N4be) — RPC ID 변경 + 2-slot 재설계
# =============================================================================
def test_delete_mind_map_uuid_payload_v5_regression():
    """v5 결함 회귀 — delete_mind_map UUID-based RPC ID 갱신 + 2-slot 구조.

    이전 결함: RPC `AH0mwd` (stale) + 4-slot `[notebook_id, None, [mm_id], [2]]`.
    NLM 웹 baseline: RPC `V5N4be` + 2-slot `[옵션_nested, mm_uuid]`.
    회귀 시: 마인드맵 삭제 실패 (NLM에 유령 데이터 잔존).

    NLM 도메인 통합 발견: V5N4be = RPC_DELETE_STUDIO.
    TS-based cleanup (cFji9, line 552)는 검증 통과로 유지.
    """
    from notebooklm_tools.core.studio import StudioMixin

    captured: dict = {}
    captured_calls = []

    def fake_call_rpc(rpc_name, params, path=None, **kw):
        captured_calls.append({"rpc": rpc_name, "params": params, "path": path})
        # _get_mind_map_timestamp loop expects list result
        return []

    client = MagicMock()
    client.RPC_DELETE_MIND_MAP = "V5N4be"
    client.RPC_LIST_MIND_MAPS = "cFji9"
    client._call_rpc = fake_call_rpc
    client.list_mind_maps = lambda nb_id: []  # no timestamp lookup

    StudioMixin.delete_mind_map(client, "test-nb-id", "mm-uuid-123")

    # delete_mind_map은 timestamp 조회용 LIST 선행 호출 + UUID-based DELETE 후속.
    # V5N4be 호출만 picking (RPC ID로 search — 호출 순서에 종속되지 않음).
    uuid_calls = [c for c in captured_calls if c["rpc"] == "V5N4be"]
    assert len(uuid_calls) == 1, (
        f"v5 결함 회귀: delete_mind_map V5N4be UUID call 1회 정확 실행 기대. "
        f"전체 호출: {[c['rpc'] for c in captured_calls]}"
    )
    uuid_call = uuid_calls[0]
    expected_uuid_params = [
        [2, None, None, V4_NESTED_OPTS, MIND_MAP_EXTRA_OPTS],
        "mm-uuid-123",
    ]
    assert uuid_call["params"] == expected_uuid_params, (
        f"v5 결함 회귀: delete_mind_map UUID 2-slot 구조 회귀. "
        f"기대 {expected_uuid_params!r}, got {uuid_call['params']!r}"
    )
    assert uuid_call["path"] == "/notebook/test-nb-id"


# =============================================================================
# ATOM-9: save_mind_map deprecated (DeprecationWarning + None return)
# =============================================================================
def test_save_mind_map_v5_deprecated():
    """v5 결함 회귀 — save_mind_map DeprecationWarning + 안전 폴백 dict.

    이전 동작: NLM CYK0Xb 호출 → mind_map_id 응답.
    NLM 새 UI: generate_mind_map 시 자동 저장 → save_mind_map 호출 자체 트리거 안 됨.
    픽스 후 (Phase 4-A NLM 권고 반영): DeprecationWarning + 빈 dict 폴백 반환 (호출자
    `res["mind_map_id"]` 직접 접근 시 TypeError 방지).
    회귀 시: 실제 NLM 호출 시도 또는 None 반환 → 호출자 크래시.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client = MagicMock()
    # _call_rpc should NOT be called — if it is, that's a regression
    call_count = {"n": 0}

    def fake_call_rpc(*args, **kw):
        call_count["n"] += 1
        return None

    client._call_rpc = fake_call_rpc

    with pytest.warns(DeprecationWarning, match="save_mind_map is deprecated"):
        result = StudioMixin.save_mind_map(
            client, "test-nb-id", '{"mind_map": "json"}', source_ids=["src-1"], title="Test"
        )

    assert isinstance(result, dict), (
        f"v5 결함 회귀: save_mind_map은 폴백 dict 반환해야 함 (None 회귀 방지). got {result!r}"
    )
    assert result.get("status") == "deprecated", (
        f"v5 결함 회귀: 폴백 dict에 status='deprecated' 명시 누락. got {result!r}"
    )
    assert result.get("mind_map_id") is None
    assert call_count["n"] == 0, (
        f"v5 결함 회귀: save_mind_map이 실제 RPC 호출 시도 — deprecated 미적용. "
        f"호출 횟수 {call_count['n']}"
    )
