# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260513-v5후속·Studio도메인 13건 픽스)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **v5 후속 — Studio 도메인 13건 픽스** (260513, 단교차삼단시공): R7cb6c 8 create + Q5 4 (poll/rename/delete/slide_revise) + v5 ATOM-8 baseline 정정(12→11). `_studio_slot1()` + `_delete_studio_slot1()` 헬퍼 분리 박제
- ✅ **RPC 분류 패턴 확정** (라이브 캡쳐 14건 검증): create/poll/list/get/share/research = 12-elem nested, modify/delete = 11-elem nested. NLM 백엔드 RPC 그룹별 schema 분기
- ✅ **v5 ATOM-1~6 라이브 검증** (260513): 5 RPC 12-elem 박제 안전 (결함 0)
- ✅ **v5 본 9건 픽스 완료** (260512): mind_map RPC ID 변경 + 통합 정렬
- ✅ **v4 결함 픽스 완료** (commit `c5b2928`): `core/sources.py:_register_file_source` payload 3-slot+nested
- ✅ **refresh_auth fail-close 픽스**: RTS+headless 실패 시 명시적 `status:error`
- 회귀 영구 가드: v4 1건 + v5 9건 + Q5 후속 12건 (ATOM-10~21, ATOM-8 정정) + refresh_auth 5건 = **27건** (`tests/core/test_rpc_payload_v5_regression.py` 21 + `tests/test_refresh_auth_fail_close.py` 5 + sources 1)

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 🎯 focus (1기획, 260513 신설)
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep 졸업
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep 졸업

## 핵심 todo
- `260513-011600`: v6 NLM동기화 정책 대전환 — 허브 진입 시 단기 ① 글로벌 CLAUDE.md 박제 (focus, 담세션 진입 시 첫 단계)
- `260512-202103`: `run_headless_auth` 자체 안정화 (백그라운드 silent fail 미해결)
- `260512-173000`: uv tool install --force 캐시 결함 (단독 실패 → `rm -rf venv + --no-cache --force` 우회)
- `260513-000810`: 미매핑 RPC 3종 점검 (AUrzMb / JFMDGd / s0tc2d — 캡쳐 부수 발견, 매핑 여부 점검)

## 최근 세션
- 세션 (260513 v5후속): Studio 도메인 13건 픽스 (8 create + Q5 4) + ATOM-8 정정(12→11) + ATOM-1~6 라이브 검증. RPC 분류 패턴 확정. 회귀 26 Green. NLM 자문 Q1~5 단발(GO/GO/(b)/+len isinstance/scope분리)
- 세션 (260512 후반2): refresh_auth fail-close + v5 9건 도메인 정렬. NLM 도메인 통합 발견(Mind Map ⊂ Studio). 회귀 14건 Green
- 세션 (260512 후반): v4 결함 발견 → 픽스 → 졸업
- 세션 (260512 전반): notebook_clone + source_replace_file 신설, parser 재작성
