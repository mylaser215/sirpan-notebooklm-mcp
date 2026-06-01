# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260601-세션57·upstream v0.6.13 톱3 수동 포팅)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **세션57 완료** (260601): upstream v0.6.13 톱3 수동 포팅 — 배치교차삼단시공 4 commit. 보안 3종(TOCTOU `core/auth.py`·`utils/cdp.py` + redaction `core/base.py`·`core/conversation.py` + external-bind `mcp/server.py` `_env_bool` fail-close) + code 3/9 reconcile (`core/sources.py`·`core/research.py`) + 세션342 가드 융합 (`SOURCE_LIMIT_GUARD=290`) + utf-8 13곳. 회귀 +33 신설 (`test_server_bind` 19 / `test_auth_toctou` 7 / `test_base_debug_redaction` 5 / `test_source_reconciliation` 16 / `test_research_import_reconcile` 5 / 기타 5) 936→**969 PASS** Green. NLM Phase 4-A 3축 ●●● 완벽 (놓친 SSOT 0). 환경변수 신규: `NOTEBOOKLM_ALLOW_EXTERNAL_BIND` / `NOTEBOOKLM_SOURCE_LIMIT_GUARD`
- ✅ **세션56 완료** (260601): Layer 3 백그라운드 자동 갱신 옵션 A + Q4 데드락 가드 시공 — 단교차삼단시공 풀오토 (NLM 핑퐁 2회 conv `21df4678`). 글로벌 CLAUDE.md 박제 2건. `core/base.py` 데드락 가드 (`HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC=60s`). 회귀 가드 6건 신설
- 🎓 **세션52 완료** (260528): v7 V4 졸업 — `flag: focus → done-keep`, `milestone: 1기획 → 4마무리`, `due: 2026-05-28`. PAM 자동 이동 500-지식정원. 관련문서 감사 (group=sirpan개선) 깔끔
- ✅ **세션51 완료** (260528): v7 잔재 5건 청소 + 외부검증 — 이단시공 풀오토. `source_get_content` × 5 + frontmatter `name:` 매핑 → `source_rename` × 5 → drift 재검증. ambiguous **5→0**, matched 130→**135**. nlm_seed.md 2건 `_narrow_by_folder_hint` 라이브 작동 검증. MCP 서버 옛 코드 결함 우회 (uv tool 재설치)
- ✅ **세션50 완료** (260528): v7 detect_drift 결정론 매칭 시공 — 단교차삼단시공 풀오토. NLM ●●● C안 채택. ATOM-1(`DUP_FILENAMES_AUTO_FOLDER_TAG`) + ATOM-2(`_narrow_by_folder_hint`) + ATOM-3(회귀 가드 4건). 891 PASS / 0 fail. v7 허브 NLM 신규 등록 (`8763a0da-...`)
- ✅ **세션47 완료** (260526): 도구 발견 패턴 정착 — 글로벌 `CLAUDE.md` *Discoverability* Bullet + `__시스템맵.md` §5 NLM cross-link 매트릭스 신설
- ✅ **세션46 완료** (260525): `research_import` 픽스 — NLM `LBwxtb` slot 0 envelope + deep report body 주입 + parse 신구조 2종. 회귀 7건. 검증 35→38건 import
- ✅ **세션45 완료** (260521): ATOM-2 시공 — `detect_drift` MCP tool화. 880 PASS
- ✅ **묶음D 완료** (세션43): `replace_source_file(atomic=True)` + `add_file(auto_wrap_to_md=True)` opt-in
- ✅ **v6 졸업** (세션36): NLM동기화 정책 대전환 10건
- 회귀 영구 가드: v4 1건 + v5 9건 + Q5 12건 + refresh_auth 5건 + ATOM-1·2 8건 + research_import 7건 + v7 4건 + 세션56 데드락 6건 + 세션57 보안·reconcile 33건 = **85건+** Green

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v7 — detect_drift 결정론 매칭 전환)]] 💎 done-keep (260528 졸업)
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260525-025900-research-import-residual-skip-3`: 41→38 잔존 3건 미import 분석 (별 세션 e3bVqc raw 캡쳐부터)
- `260523-015000-media-source-expansion-plan`: NLM 멀티미디어 소스 확장 (별 세션 단서 캡쳐 후 시공)
- `260515-025300-atomic-trial-monitoring`: `source_replace_file(atomic=True)` trial (1건 누적)

## 최근 세션
- 세션57 (260601): upstream v0.6.13 톱3 수동 포팅 — 배치교차삼단시공 4 commit. 보안 3종+reconcile+세션342 가드 융합+utf-8. 회귀 +33 969 PASS. Phase 4-A NLM 3축 ●●●
- 세션56 (260601): Layer 3 데드락 가드 + 옵션 A 박제 — 단교차삼단시공 풀오토. NLM 핑퐁 2회 conv `21df4678`. `base.py` 가드 + CLAUDE.md 2 박제. 11+293 PASS. trial 대기
- 세션52 (260528): v7 V4 졸업 — 플젝마무리 스킬. flag/milestone/due 갱신, PAM 500 이동, 감사 깔끔
- 세션51 (260528): v7 잔재 5건 청소 + 외부검증 — 이단시공 풀오토. source_get_content+rename×5. ambiguous 5→0. uv 캐시 결함 우회
- 세션50 (260528): v7 detect_drift 결정론 매칭 시공 — 단교차삼단시공 풀오토. NLM ●●● C안. ATOM 3 시공 891 PASS. v7 허브 NLM 등록
- 세션47 (260526): 도구 발견 패턴 정착 — Discoverability + cross-link 매트릭스
