# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260512-v4·v5졸업+refresh_auth fail-close)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **v5 RPC payload 도메인 통합 정렬 완료**: 9 RPC NLM 웹 baseline 일치 (list_notebooks/get_notebook/create_notebook/set_public_access/add_collaborator/start_research_fast slot4·slot2 v4 nested + generate_mind_map `yyryJe→R7cb6c` 9-slot 재설계 + delete_mind_map `AH0mwd→V5N4be` 2-slot + save_mind_map deprecated). 회귀 9건 Green. Phase 4-A NLM CONDITIONAL-GO → 우려 2건 반영
- ✅ **v4 결함 픽스 완료** (commit `c5b2928`): `core/sources.py:_register_file_source` payload 3-slot+nested
- ✅ **refresh_auth fail-close 픽스** (단교차삼단시공): RTS 만료+headless 실패 시 stale disk reload fallback 삭제, 명시적 `status:error` + hint. 글로벌 CLAUDE.md NLM동기화/세션마감 절 인증 복구 절차 갱신
- ✅ **NLM 도메인 통합 발견** (v5 부수 산물): Mind Map ⊂ Studio (R7cb6c=CREATE_STUDIO, V5N4be=DELETE_STUDIO). Mind Map RPCs == Notes RPCs (CYK0Xb/cFji9/AH0mwd 공유)
- ✅ **`services/sync_helpers.py` 신설**: drift 감지 영구 라이브러리
- 회귀 테스트 영구 가드: v4 1건 + v5 9건(`tests/core/test_rpc_payload_v5_regression.py`) + refresh_auth 5건(`tests/test_refresh_auth_fail_close.py`)

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep 졸업 (단일 세션 완수)
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep 졸업

## 핵심 todo
- `260512-215203`: Audio/Video Overview RPC payload 캡쳐 비교 (v5 도메인 통합 후속 — `R7cb6c` 공유 RPC가 audio/video/report/flashcards/quiz/slide_deck/infographic/data_table 옵션 차이 가능)
- `260512-202103`: `run_headless_auth` 자체 안정화 (백그라운드 silent fail 미해결, 사용자 nlm login 강제 빈도)
- `260512-173000`: uv tool install --force 캐시 결함 (단독 실패 → `rm -rf venv + --no-cache --force` 우회 표준화)

## 최근 세션
- 세션 (260512 후반2): refresh_auth fail-close 픽스 + v5 RPC payload 도메인 정렬 9건. 라이브 캡쳐 19장 baseline → 9 결함 + 3 정상 매핑 → 단교차+배치교차삼단시공. NLM 도메인 통합 발견(Mind Map ⊂ Studio). 회귀 14건 Green. Phase 4-A CONDITIONAL-GO 우려 2건 즉시 반영
- 세션 (260512 후반): v4 결함 발견 → 픽스 → 졸업. 추측 사고 3회 누적 회고 박제
- 세션 (260512 전반): notebook_clone + source_replace_file 신설, parser 재작성
