# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260720 세션72)
- **NotebookLM MCP v0.5.23** — Python/uv/FastMCP, 포트 9472, editable(-e) 설치(세션72 — 소스 수정 시 재설치 불필요)
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- 회귀 영구 가드 **1043 PASS** Green (세션70 fchmod +, 세션71 좀비청소 +8, 세션72 RTS선제갱신 +6 포함)
- v8 허브 2종 모두 💎 done-keep 졸업 (전 항목 `[x]`, detect_drift 159소스 0잔재·0모호 클린) — 260720 재확인
- **인증 3계층 안정화(세션70~72)**: fchmod 0o600 + 좀비Chrome청소(`_cleanup_zombie_chrome`) + RTS 선제갱신(`_maybe_proactive_rts_refresh`). 활성 트래픽 순단방지 검증완료(11:49 proactive 라이브). cold(장기idle) 복구 `nlm login` hang 1건 감시중(`260720-153726`)
- ⚠️ 상세 세션별 이력은 세션아카이브·타임라인 참조 (본 MEMORY는 포인터만)

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v8 — RPC timeout 픽스 + 번들 chunking 설계 + 핸드오프 유실 P0)]] 💎 done-keep (B②·A·B③·★P0·`__Claude포인터`·add-timeout 전부 `[x]` / B③ `070b566f` 볼트밖 거짓잔재 세션68 해소(`174b447` EXTERNAL_FILE_MAP raw 재조회) / detect_drift 159소스 **0잔재·0모호 클린** 260720 재확인)
- [[NotebookLM MCP 안정화 프로젝트 (v8 — upstream v0.6.14 톱3 수동 포팅)]] 💎 done-keep (OOM·fail-loud·login-crash 3 ATOM, 995 PASS)
- [[NotebookLM MCP 안정화 프로젝트 (v7 — detect_drift 결정론 매칭 전환)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260525-025900-research-import-residual-skip-3`: 41→38 잔존 3건 미import 분석 (별 세션 e3bVqc raw 캡쳐부터)
- `260523-015000-media-source-expansion-plan`: NLM 멀티미디어 소스 확장 (별 세션 단서 캡쳐 후 시공)

## 최근 세션
- 세션72 (260720): RTS 선제갱신 `_maybe_proactive_rts_refresh`(활성 핫패스 RTS 선신선화) + editable(-e) 빌드 전환 — 1043 PASS. `6aed973`·`24a38f1`
- 세션71 (260719): Windows 좀비 Chrome 청소 `_cleanup_zombie_chrome`(`nlm login --clear` 반복 근본치료, SingletonLock은 POSIX전용) — 1037 PASS. `0ce10b2`
- 세션70 (260715): fchmod로 자격증명 0o600 복원(upstream f2fb921 write-then-chmod 회귀) — 1029 PASS. `448700d`
- 세션69 (260714): generate_code_md.py Kotlin(.kt) 파서 추가 — `cb85fda`
- 세션68 (260706): detect_drift 볼트밖 소스 missing 오탐 픽스(B③ `070b566f` 해소, EXTERNAL_FILE_MAP raw 재조회) — `174b447` / (크로스 세션418) source_replace_file `source_id` optional 자동매칭(UUID 전사오류 근본방어) — `02bc2fa`
