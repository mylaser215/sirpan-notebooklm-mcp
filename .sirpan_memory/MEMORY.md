# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260704·B② chunking 라이브 검증 완료 + MEMORY 대현행화)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ⚠️ **이번 세션 (260704)**: **B²/B³은 sirpan개선 세션397에 이미 외부검증 완료**(v8 허브 line40·42 SSOT) — 내가 근거삼은 감시 todo(`260702-*`)가 세션397 미반영 stale이라 **B² 라이브 파일럿을 중복 수행**(무해·완전청소·부작용0, part분할 명시검증만 소소한 추가값). 4동작 실측(part분할 `parts:2` / Full-Sync ADD-first / stale삭제 `2 stale removed` / churn skip)은 세션397 검증의 독립 재현. **교훈**: 도구분기 B² 때 허브 SSOT 미확인, A의 stale-신뢰 오류 재발 → [[feedback_state_verify]]. **부수 성과**: A(세션64)·B³(세션397) 이미 완료 규명(내 오독+NLM 데이터오염 환각 실행전 차단) + 핸드오프 큐 3건 제거 + NLM 인증 옵션A 라이브 발동. ⚠️ registry 실경로 `000-시스템/030-Configs/시스템환경/` / churn skip은 번들 파일 1개라도 앵커후 변경 시 sync
- ✅ **세션64 완료** (260702): **A packaging 근본수정** — `generate_bundle_md.py` git mv(repo root `scripts/`→`src/notebooklm_tools/scripts/`) + `_BUNDLE_TOOL_SCRIPT` `parents[3]`→`parents[1]` → *editable 의존 제거·정상 wheel화* (`06c0050`). ⚠️ "editable로 전환"이 **아님** — 정반대(editable 의존을 없앰). + `SOURCE_ADD_TIMEOUT` env화 + **atomic default 승격**(delete-first→add-first, ADD 실패 시 원본 보존 → 데이터 유실 차단, `d32f18d`) + 세션409(sirpan개선) `4e21442`(v10 git churn skip + max_words 100k)
- ✅ **세션63 완료** (260702): B② 대형번들 chunking — `generate_bundle_md --max-words` 파일분할 + `sync_bundle` 1:N Full-Sync (NLM ●●● conv `803fdca1`). 회귀 **1013 PASS**. commit `03859f9`
- ✅ **세션62 완료** (260630): NLM RPC read timeout 30→180s 픽스(172소스 노트북 정상화 — git 회귀 아닌 데이터측 페이로드 비대 + 고정 `timeout=30.0`) + `generate_code_md` `.json` 구조추출 지원(B①). 회귀 +8 (timeout `test_read_timeout` 4 / json 4) 969→**1003 PASS**. B②(chunking, NLM ●●● 설계 확정 conv `803fdca1` — 파일분할+sync_bundle 1:N)·A(packaging editable 우회 근본수정) 100% 핸드오프 박제. env 신규 `NOTEBOOKLM_READ_TIMEOUT`. commit `0998af2`·`55f386d`·`e838916`
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
- 회귀 영구 가드: … + 세션57 보안·reconcile 33건 + 세션62 timeout·json 8건 + 세션63/64 chunking·bundle·atomic = **1013 PASS** Green

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v8 — RPC timeout 픽스 + 번들 chunking 설계 + 핸드오프 유실 P0)]] 🆕 거의 완료 (허브 원문 SSOT: `[x]` B②chunking(63, 라이브 외부검증:완료 sirpan개선 세션397)·`[x]` A packaging(64, editable의존 제거→wheel정상화)·`[x]` ★P0 핸드오프유실(395)·`[x]` `__Claude포인터`재동기(395)·`[x]` 세션번호(현행유지) / **B③ 실체 변화**: non-md 13건은 **소멸**(260704 detect_drift 실측 = `matched_non_markdown:0`, timeout 없이 관통). 현 drift = 잔재 1(`070b566f` sirpan-sidebar_main.ts.md, 볼트밖 `260407_sirpan-agent/` symlink 미연결 → **거짓 잔재, blind 청소 금지**, 감시 todo `260702-detect-drift-outside-vault-false-stale`) + 모호 1(`README.md`→7후보). 파생 매핑개선은 저빈도 ROI로 감시 유지)
- [[NotebookLM MCP 안정화 프로젝트 (v7 — detect_drift 결정론 매칭 전환)]] 💎 done-keep (260528 졸업)
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260525-025900-research-import-residual-skip-3`: 41→38 잔존 3건 미import 분석 (별 세션 e3bVqc raw 캡쳐부터)
- `260523-015000-media-source-expansion-plan`: NLM 멀티미디어 소스 확장 (별 세션 단서 캡쳐 후 시공)
- ~~`260515-025300-atomic-trial-monitoring`~~: **해소** — 세션64에 atomic default 승격(`d32f18d`), trial 모니터링 불요

## 최근 세션
- 세션64 (260702): bundle 패키징 편입 + SOURCE_ADD_TIMEOUT env화 + atomic default 승격 — commit `06c0050`·`d32f18d`. 세션409 `4e21442`(v10 git churn skip) 동반
- 세션63 (260702): B② 대형번들 chunking — `--max-words` 파일분할 + `sync_bundle` 1:N. 1013 PASS. commit `03859f9`
- 세션62 (260630): NLM RPC read timeout 30→180s + generate_code_md `.json` 지원. 1003 PASS. commit `0998af2`·`55f386d`·`e838916`
- 세션57 (260601): upstream v0.6.13 톱3 수동 포팅 — 보안 3종+reconcile+세션342 가드 융합. 969 PASS. Phase 4-A NLM 3축 ●●●
- 세션56 (260601): Layer 3 데드락 가드 + 옵션 A 박제 — 단교차삼단시공 풀오토. `base.py` 가드 + CLAUDE.md 2 박제
- 세션52 (260528): v7 V4 졸업 — flag/milestone/due 갱신, PAM 500 이동
