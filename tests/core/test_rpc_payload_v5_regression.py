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


# v4 nested 표준 옵션 (12-요소) — R7cb6c CREATE_STUDIO/gArtLc POLL_STUDIO 공유
V4_NESTED_OPTS = [1, None, None, None, None, None, None, None, None, None, None, [1]]
# V5N4be DELETE_STUDIO nested (11-요소) — 260512 라이브 캡쳐 확정 (일반·마인드맵 전수 일치)
# R7cb6c와 1-요소 차이 — RPC별 schema 차이 박제.
V5N4be_NESTED_OPTS = [1, None, None, None, None, None, None, None, None, None, [1]]
# 마인드맵·스튜디오 도메인 전용 추가 옵션
MIND_MAP_EXTRA_OPTS = [[1, 4, 2, 3, 6]]
# v5 후속(260512): Studio 도메인 8개 도구 공통 slot1 baseline (라이브 캡쳐 8건 전수 일치)
STUDIO_SLOT1 = [2, None, None, V4_NESTED_OPTS, [[1, 4, 2, 3, 6]]]
# V5N4be DELETE_STUDIO slot0 (260512 라이브 캡쳐 마인드맵·일반 전수 일치)
DELETE_STUDIO_SLOT0 = [2, None, None, V5N4be_NESTED_OPTS, [[1, 4, 2, 3, 6]]]


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
    # 260512 정정: V5N4be nested = 11-요소 (라이브 캡쳐 마인드맵·일반 전수 일치).
    # 초기 v5 박제 12-요소(V4_NESTED_OPTS)는 라이브 검증 없이 채택한 잘못된 baseline.
    expected_uuid_params = [DELETE_STUDIO_SLOT0, "mm-uuid-123"]
    assert uuid_call["params"] == expected_uuid_params, (
        f"v5 결함 회귀: delete_mind_map UUID 2-slot 구조 회귀. "
        f"기대 {expected_uuid_params!r}, got {uuid_call['params']!r}"
    )
    assert uuid_call["path"] == "/notebook/test-nb-id"
    # Q4 보강: nested 11-요소 (R7cb6c 12-요소와 RPC별 차이 박제)
    assert len(uuid_call["params"][0][3]) == 11


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


# =============================================================================
# v5 후속 (260512): Studio 도메인 8개 도구 — R7cb6c 공유 RPC payload 박제
#
# 라이브 캡쳐 8건 (audio/video/report/slide/flashcards/quiz/infographic/datatable)
# urllib+json.loads 디코드 → NLM 자문 GO (Q1~Q5 모두 명확) → 본 회귀 가드 박제.
#
# 핵심 발견: slot1 `[[1,4,2,3,6]]` 옵션이 마인드맵 전용이 아니라 *모든* Studio
# 호출에 공통 적용. Q4 NLM 권고 따라 길이/타입 엄격 검증 추가.
# =============================================================================

from notebooklm_tools.core import constants as _constants


def _make_studio_mock_client():
    """8개 Studio 도구 공통 mock — RPC_CREATE_STUDIO=R7cb6c + STUDIO_TYPE_* 일괄 설정."""
    client = MagicMock()
    client.RPC_CREATE_STUDIO = "R7cb6c"
    client.STUDIO_TYPE_AUDIO = _constants.STUDIO_TYPE_AUDIO
    client.STUDIO_TYPE_VIDEO = _constants.STUDIO_TYPE_VIDEO
    client.STUDIO_TYPE_REPORT = _constants.STUDIO_TYPE_REPORT
    client.STUDIO_TYPE_FLASHCARDS = _constants.STUDIO_TYPE_FLASHCARDS
    client.STUDIO_TYPE_INFOGRAPHIC = _constants.STUDIO_TYPE_INFOGRAPHIC
    client.STUDIO_TYPE_SLIDE_DECK = _constants.STUDIO_TYPE_SLIDE_DECK
    client.STUDIO_TYPE_DATA_TABLE = _constants.STUDIO_TYPE_DATA_TABLE
    captured: dict = {}

    def fake_call_rpc(rpc_name, params, path=None, **kw):
        captured["rpc"] = rpc_name
        captured["params"] = params
        captured["path"] = path
        return []

    client._call_rpc = fake_call_rpc
    return client, captured


# =============================================================================
# ATOM-10: create_audio_overview (R7cb6c, type=1) — default → inner 4-요소 압축
# =============================================================================
def test_create_audio_overview_payload_v5_regression():
    """v5 후속 회귀 — audio overview slot1 nested + default inner 4-요소.

    NLM 웹 baseline (default 호출): slot1 = STUDIO_SLOT1, type=1, content[6] =
    `[None, [None, None, None, sources_simple]]` (inner 4-요소, length/lang/format 자리 제거).
    회귀 시: slot1 flat `[2]` 또는 inner에 default 값 명시 송신 → NLM 서버 처리 분기 위험.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_audio_overview(client, "test-nb", source_ids=["src-1", "src-2"])

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1, (
        f"v5 후속 회귀: audio slot1 nested+extra 누락. got {captured['params'][0]!r}"
    )
    assert captured["params"][2][2] == 1, (
        f"v5 후속 회귀: audio type 코드 불일치 (기대 1). got {captured['params'][2][2]!r}"
    )
    audio_options = captured["params"][2][6]
    assert audio_options == [None, [None, None, None, [["src-1"], ["src-2"]]]], (
        f"v5 후속 회귀: audio default inner 4-요소 압축 누락. got {audio_options!r}"
    )


# =============================================================================
# ATOM-11: create_video_overview (R7cb6c, type=3) — slot1 + slot8 video_options
# =============================================================================
def test_create_video_overview_payload_v5_regression():
    """v5 후속 회귀 — video overview slot1 nested + slot8 video_options 구조.

    NLM 웹 baseline: slot1 = STUDIO_SLOT1, type=3, content[8] =
    `[None, None, [sources_simple, lang, focus, None, format, vstyle]]`.
    회귀 시: slot1 flat 또는 inner 슬롯 위치 변경.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_video_overview(
        client, "test-nb", source_ids=["src-1"],
        language="ko", focus_prompt="prompt", format_code=1, visual_style_code=9,
    )

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 3, (
        f"v5 후속 회귀: video type 코드 불일치 (기대 3). got {captured['params'][2][2]!r}"
    )
    video_options = captured["params"][2][8]
    assert video_options == [None, None, [[["src-1"]], "ko", "prompt", None, 1, 9]], (
        f"v5 후속 회귀: video slot8 inner 구조 회귀. got {video_options!r}"
    )


# =============================================================================
# ATOM-12: create_report (R7cb6c, type=2) — B급 픽스: inner 7-요소, 마지막 int
# =============================================================================
def test_create_report_payload_v5_regression():
    """v5 후속 회귀 — report inner 7-요소 (B급) + 마지막 요소 int(1) 타입 엄격 검증.

    NLM 웹 baseline: inner `[title, desc, None, sources, lang, prompt, 1]` (7-요소).
    회귀 결함: 우리 코드 inner 8-요소 `[..., prompt, None, True]` → 슬롯 1칸 밀림 +
    Protobuf `bool true` vs `int 1` 타입 차이로 silent degradation 위험 (v4 사례).
    NLM 자문 Q2: 정수 1 명시 권고. Q4: len()+isinstance() 엄격 검증 권고.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_report(
        client, "test-nb", source_ids=["src-1"], report_format="Briefing Doc", language="en",
    )

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 2
    report_options = captured["params"][2][7]
    inner = report_options[1]
    # Q4 보강: 길이 엄격 검증 (8-요소 회귀 차단)
    assert len(inner) == 7, (
        f"v5 후속 회귀: report inner 7-요소여야 함 (B급 결함 회귀). 길이={len(inner)} got {inner!r}"
    )
    # Q4 보강: 마지막 요소 int 타입 (bool True 회귀 차단)
    assert isinstance(inner[6], int) and not isinstance(inner[6], bool), (
        f"v5 후속 회귀: report inner[6]은 int 1이어야 함 (bool True 회귀 차단). got {inner[6]!r} ({type(inner[6]).__name__})"
    )
    assert inner[6] == 1


# =============================================================================
# ATOM-13: create_slide_deck (R7cb6c, type=8) — default → inner 빈 배열
# =============================================================================
def test_create_slide_deck_payload_v5_regression():
    """v5 후속 회귀 — slide deck slot1 nested + default inner 빈 배열.

    NLM 웹 baseline (default 호출): content[16] = `[[]]` (옵션 inner 빈).
    회귀 시: default라도 `[[None, "en", 1, 3]]` 명시 송신 → 잠복 결함 위험.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_slide_deck(client, "test-nb", source_ids=["src-1"])

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 8
    assert captured["params"][2][16] == [[]], (
        f"v5 후속 회귀: slide default inner 빈 배열 누락. got {captured['params'][2][16]!r}"
    )


# =============================================================================
# ATOM-14: create_flashcards (R7cb6c, type=4) — slot9 inner 7-요소
# =============================================================================
def test_create_flashcards_payload_v5_regression():
    """v5 후속 회귀 — flashcards slot1 nested + slot9 inner 7-요소 박제.

    NLM 웹 baseline: content[9] = `[None, [1, None, None, None, None, None, [2, 2]]]`.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_flashcards(client, "test-nb", source_ids=["src-1"])

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 4
    flashcard_options = captured["params"][2][9]
    inner = flashcard_options[1]
    assert len(inner) == 7
    assert inner[0] == 1 and inner[6] == [2, 2], (
        f"v5 후속 회귀: flashcards inner 구조 회귀. got {inner!r}"
    )


# =============================================================================
# ATOM-15: create_quiz (R7cb6c, type=4) — slot9 inner 8-요소 (quiz는 1요소 더 길음)
# =============================================================================
def test_create_quiz_payload_v5_regression():
    """v5 후속 회귀 — quiz slot1 nested + slot9 inner 8-요소 박제.

    NLM 웹 baseline: content[9] = `[None, [2, None, None, None, None, None, None, [2, 2]]]`.
    flashcards(7-요소)와 type 코드(4) 공유하지만 inner 8-요소 차이로 구분.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_quiz(client, "test-nb", source_ids=["src-1"])

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 4
    quiz_options = captured["params"][2][9]
    inner = quiz_options[1]
    assert len(inner) == 8
    assert inner[0] == 2 and inner[7] == [2, 2], (
        f"v5 후속 회귀: quiz inner 구조 회귀. got {inner!r}"
    )


# =============================================================================
# ATOM-16: create_infographic (R7cb6c, type=7) — default → inner 5-요소
# =============================================================================
def test_create_infographic_payload_v5_regression():
    """v5 후속 회귀 — infographic slot1 nested + default inner 5-요소.

    NLM 웹 baseline (default 호출): content[14] = `[[None, None, None, 1, 2]]`
    (lang/vstyle 자리 제거된 5-요소).
    회귀 시: 6-요소 `[None, "en", None, 1, 2, 1]` 명시 송신 → 잠복 결함 위험.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_infographic(client, "test-nb", source_ids=["src-1"])

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 7
    infographic_options = captured["params"][2][14]
    inner = infographic_options[0]
    assert len(inner) == 5, (
        f"v5 후속 회귀: infographic default inner 5-요소여야 함. 길이={len(inner)} got {inner!r}"
    )
    assert inner == [None, None, None, 1, 2]


# =============================================================================
# ATOM-17: create_data_table (R7cb6c, type=9) — default → inner 빈 배열
# =============================================================================
def test_create_data_table_payload_v5_regression():
    """v5 후속 회귀 — datatable slot1 nested + default inner 빈 배열.

    NLM 웹 baseline (default 호출): content[18] = `[None, []]`.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_studio_mock_client()
    StudioMixin.create_data_table(client, "test-nb", source_ids=["src-1"])

    assert captured["rpc"] == "R7cb6c"
    assert captured["params"][0] == STUDIO_SLOT1
    assert captured["params"][2][2] == 9
    assert captured["params"][2][18] == [None, []], (
        f"v5 후속 회귀: datatable default inner 빈 배열 누락. got {captured['params'][2][18]!r}"
    )


# =============================================================================
# ATOM-18: poll_studio_status (gArtLc) — slot1 Studio 도메인 공통 패턴 박제
# =============================================================================
def test_poll_studio_status_payload_v5_regression():
    """v5 후속 회귀 — poll_studio_status slot1 nested+extra (Studio 도메인 공통).

    NLM 웹 baseline (260512 라이브 캡쳐): `[STUDIO_SLOT1, notebook_id, filter_query]`.
    핵심 도메인 발견: slot1 `[[1,4,2,3,6]]` 옵션이 R7cb6c 전용이 아니라 *Studio
    도메인 전체* 공통 패턴 (gArtLc poll, R7cb6c create, V5N4be delete 등 모두 동일).
    회귀 시: slot1 flat `[2]` → NLM 옵션(필드 풀버전 등) 누락 가능.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_mock_client("RPC_POLL_STUDIO", "gArtLc")
    StudioMixin.poll_studio_status(client, "test-nb")

    assert captured["rpc"] == "gArtLc"
    expected = [
        STUDIO_SLOT1,
        "test-nb",
        'NOT artifact.status = "ARTIFACT_STATUS_SUGGESTED"',
    ]
    assert captured["params"] == expected, (
        f"v5 후속 회귀: poll_studio_status slot1 Studio 도메인 공통 패턴 누락. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )
    assert captured["path"] == "/notebook/test-nb"


# =============================================================================
# ATOM-19: rename_studio_artifact (rc3d8d) — 5-slot 구조 + RPC별 변형 slot3
# =============================================================================
def test_rename_studio_artifact_payload_v5_regression():
    """v5 후속 회귀 — rename_studio_artifact 5-slot 구조 + RPC별 변형 옵션.

    NLM 웹 baseline (260512 라이브 캡쳐): 5-slot 구조.
        slot0: [artifact_id, new_title]
        slot1: [["title"]]
        slot2: None
        slot3: [2, None×10, [1]]  (12-요소, 첫 요소 2 — V4_NESTED [1, None×10, [1]] 변형)
        slot4: [[1, 4, 2, 3, 6]]   (Studio 도메인 extra opts 공통)
    회귀 시 (2-slot `[[id, title], [["title"]]]` 회귀): NLM 옵션·도메인 식별 누락.
    핵심: slot3 첫 요소 1(V4) vs 2(rc3d8d) — RPC별 패턴 차이 박제.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_mock_client("RPC_RENAME_ARTIFACT", "rc3d8d")
    StudioMixin.rename_studio_artifact(client, "test-artifact-id", "새 제목")

    assert captured["rpc"] == "rc3d8d"
    expected = [
        ["test-artifact-id", "새 제목"],
        [["title"]],
        None,
        [2, None, None, None, None, None, None, None, None, None, None, [1]],
        [[1, 4, 2, 3, 6]],
    ]
    assert captured["params"] == expected, (
        f"v5 후속 회귀: rename_studio_artifact 5-slot 구조 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )
    # Q4 보강: slot3 첫 요소 정수 2 (V4_NESTED 첫 요소 1과 차이 박제)
    assert captured["params"][3][0] == 2, (
        f"v5 후속 회귀: rename slot3 첫 요소는 2여야 함 (RPC별 변형 패턴). got {captured['params'][3][0]!r}"
    )
    assert len(captured["params"][3]) == 12


# =============================================================================
# ATOM-20: delete_studio_artifact (V5N4be 일반 path) — 2-slot + nested 11-요소
# =============================================================================
def test_delete_studio_artifact_payload_v5_regression():
    """v5 후속 회귀 — delete_studio_artifact V5N4be 2-slot + nested 11-요소 박제.

    NLM 웹 baseline (260512 라이브 캡쳐 일반 artifact): `[slot0, artifact_id]`.
        slot0 = [2, None, None, [1, None×9, [1]], [[1, 4, 2, 3, 6]]]
                                ↑ 11-요소 (R7cb6c V4_NESTED 12-요소와 1-요소 차이)
    회귀 시: `[[2], artifact_id]` flat → NLM 옵션 누락.

    ⚠ 부수 발견: v5 ATOM-8 (delete_mind_map UUID)는 12-요소 V4_NESTED_OPTS 박제 →
    V5N4be 동일 RPC 공유 → 마인드맵 라이브 캡쳐 검증 시 정정 필요 (별도 todo).
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_mock_client("RPC_DELETE_STUDIO", "V5N4be")

    StudioMixin.delete_studio_artifact(client, "test-art-id")

    assert captured["rpc"] == "V5N4be"
    expected = [DELETE_STUDIO_SLOT0, "test-art-id"]
    assert captured["params"] == expected, (
        f"v5 후속 회귀: delete_studio_artifact 2-slot + nested 11-요소 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )
    # Q4 보강: nested 옵션 11-요소 (R7cb6c 12-요소와 차이 박제)
    assert len(captured["params"][0][3]) == 11, (
        f"v5 후속 회귀: V5N4be nested 11-요소여야 함 (R7cb6c 12-요소와 차이). "
        f"길이={len(captured['params'][0][3])}"
    )


# =============================================================================
# ATOM-21: revise_slide_deck (KmcKPe) — 3-slot + DELETE_STUDIO_SLOT0 (11-요소)
# =============================================================================
def test_revise_slide_deck_payload_v5_regression():
    """v5 후속 회귀 — revise_slide_deck slot0 = V5N4be DELETE와 동일 11-요소 nested.

    NLM 웹 baseline (260513 라이브 캡쳐):
        [DELETE_STUDIO_SLOT0, artifact_id, [instruction_pairs]]
    KmcKPe REVISE와 V5N4be DELETE가 동일 slot0 패턴 공유 (modify/delete RPC = 11-요소).
    회귀 시: slot0 = `[2]` flat → NLM 옵션 누락.
    """
    from notebooklm_tools.core.studio import StudioMixin

    client, captured = _make_mock_client("RPC_REVISE_SLIDE_DECK", "KmcKPe")
    StudioMixin.revise_slide_deck(
        client, "test-art-id", [(0, "슬라이드 0 수정 지시"), (2, "슬라이드 2 수정 지시")]
    )

    assert captured["rpc"] == "KmcKPe"
    expected = [
        DELETE_STUDIO_SLOT0,
        "test-art-id",
        [[[0, "슬라이드 0 수정 지시"], [2, "슬라이드 2 수정 지시"]]],
    ]
    assert captured["params"] == expected, (
        f"v5 후속 회귀: revise_slide_deck 3-slot 구조 회귀. "
        f"기대 {expected!r}, got {captured['params']!r}"
    )
    # Q4 보강: nested 11-요소 (modify/delete RPC 공통 패턴 박제)
    assert len(captured["params"][0][3]) == 11
