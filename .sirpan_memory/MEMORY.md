# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260515-세션43·묶음D 배치교차삼단시공·`atomic` + `auto_wrap_to_md` 신설)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **묶음D 완료** (세션43 26-05-15): NLM 동기화 보강 2종 — `replace_source_file(atomic=True)` ADD-first 분실 차단 + `add_file(auto_wrap_to_md=True)` fence-wrap 임시 `.md` 업로드 + 글로벌 CLAUDE.md 박제. opt-in default False (Ghost ID 회귀 차단 trial). NLM Phase 4-A 사후 ✅ 3축. plan 묶음A/B/C/D 4/4 close
- ✅ **v6 졸업** (세션36 26-05-13): NLM동기화 정책 대전환 단기3+중기3+장기4 = 10건. `generate_py_md.py` + `fallback_to_text` + 매트릭스 정정(꼬리 `.md` = 가공 SSOT) 박제
- ✅ **세션37 source_add 진단 종결** (260514, commit `67a3eb7`): state-level 결함 NLM transient + Source-Note 라우팅 별 결함 아님 확정. `detail` 필드 8 wrappers
- ✅ v5 후속 Studio 13건 + v5 본 9건 + v4 결함 픽스 + refresh_auth fail-close
- 회귀 영구 가드: v4 1건 + v5 9건 + Q5 후속 12건 + refresh_auth 5건 + sources detail 보강 + ATOM-1·2 8건 = **35건+** Green

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep 졸업 (세션36 마감)
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260515-025300-atomic-trial-monitoring`: `source_replace_file(atomic=True)` trial 모니터링 (NLM Phase 4-A ●●● 권고). 단일 파일/저중요도 trial → Ghost ID 자극 패턴 관찰. 무재발 N건 누적 시 default 승격 검토
- `260514-105956`: source_add state-level 결함 재발 모니터링 — `detail` 필드 보험 완료. 재발 시 dedup 또는 옛 source 정리로 우회 (NLM 측 transient)
- `260513-1300-ts-codegen`: `.ts` 가공 도구 일반화 (`generate_py_md.py` 확장 또는 `generate_code_md.py`) — `generate_ts_md.py`로 부분 완료 (세션39)
- `260513-000810`: 미매핑 RPC 3종 점검 (AUrzMb / JFMDGd / s0tc2d — `s0tc2d` 노트북 rename 신규 기능 후보)
- `260512-202103`: `run_headless_auth` 자체 안정화 (백그라운드 silent fail, ThreadPoolExecutor None 반환)
- `260512-173000`: `uv tool install --force` 캐시 결함 (우회 4-step 박제 — venv rm + `--no-cache --force`)

## 최근 세션
- 세션43 (260515): 묶음D 배치교차삼단시공 — `replace_source_file(atomic=True)` ADD-first + `add_file(auto_wrap_to_md=True)` fence-wrap 임시 `.md` + 글로벌 CLAUDE.md 라인 116 박제 bullet 2개. 회귀 860 PASS (852+8 신규+1 픽스). NLM Phase 4-A ✅ 3축. plan 4/4 close
- 세션42 (260515): 묶음C 이단시공 — `session_save.py:1804` *timeline_row* `세션N` 자동 치환 부작용 픽스 (D안: `_validate_timeline_row` ATOM-A 확장). 4 케이스 dry-run OK
- 세션41 (260514): 묶음B 단교차삼단시공 — `cdp.py` `tries` 5→30 통일 + logger 가시화 + AUrzMb 박제
- 세션40 (260514): 묶음A 직접 Edit — `generate_ts_md.py` regex 보강 + uv 캐시 결함 우회 4-step 박제
- 세션37 (260514): source_add state-level 진단 + Source-Note 라우팅 별 결함 아님 확정. `detail` 필드 8 wrappers (commit `67a3eb7`)
