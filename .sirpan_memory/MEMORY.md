# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260704 세션67)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- 회귀 영구 가드 **1013 PASS** Green (세션57 보안·reconcile 33 + 세션62 timeout·json 8 + 세션63/64 chunking·bundle·atomic 포함)
- v8 허브 거의 완료 — B②chunking·A packaging·★P0 핸드오프유실 모두 `[x]`. 잔여는 저빈도 `detect_drift` 감시뿐
- ⚠️ 상세 세션별 이력은 세션아카이브·타임라인 참조 (본 MEMORY는 포인터만)

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v8 — RPC timeout 픽스 + 번들 chunking 설계 + 핸드오프 유실 P0)]] 🆕 거의 완료 (허브 원문 SSOT: B②chunking(63, 외부검증:완료 sirpan개선 세션397)·A packaging(64)·★P0 핸드오프유실(395)·`__Claude포인터`재동기(395) 전부 `[x]` / 잔여 drift = 거짓 잔재 1(`070b566f` 볼트밖 symlink, blind 청소 금지) + 모호 1(`README.md`→7후보), 저빈도 ROI 감시)
- [[NotebookLM MCP 안정화 프로젝트 (v7 — detect_drift 결정론 매칭 전환)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260525-025900-research-import-residual-skip-3`: 41→38 잔존 3건 미import 분석 (별 세션 e3bVqc raw 캡쳐부터)
- `260523-015000-media-source-expansion-plan`: NLM 멀티미디어 소스 확장 (별 세션 단서 캡쳐 후 시공)

## 최근 세션
- 세션67 (260704): 감시 todo 2건 청소(`atomic-trial`·`option-a-trial`) + 옵션 A 자동복구 라이브 검증완료(세션63·66 2회 재현)
- 세션64 (260702): bundle 패키징 편입 + `SOURCE_ADD_TIMEOUT` env화 + atomic default 승격 — `06c0050`·`d32f18d`
- 세션63 (260702): B② 대형번들 chunking — `--max-words` 파일분할 + `sync_bundle` 1:N. 1013 PASS. `03859f9`
