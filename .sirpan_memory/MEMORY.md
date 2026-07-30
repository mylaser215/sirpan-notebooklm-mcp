# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260731 세션77)
- **NotebookLM MCP v0.5.23** — Python/uv/FastMCP, 포트 9472, editable(-e) 설치(세션72 — 소스 수정 시 재설치 불필요)
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- 회귀 영구 가드 **1059 PASS** Green (세션77 도메인 리브랜딩 회귀가드 +3)
- v8 허브 2종 모두 💎 done-keep 졸업 (전 항목 `[x]`, detect_drift 159소스 0잔재·0모호 클린)
- **도메인 리브랜딩 근본해결(세션77)**: NLM personal 도메인 `notebooklm.google.com`→`notebook.google.com`(Gemini Notebook) 서버 리다이렉트 → `is_logged_in`/`_ALLOWED_BASE_HOSTS` 하드코딩이 옛 도메인만 인정 → nlm login/headless auth 전멸(Login timeout). `cdp.py:_is_notebooklm_url`+`config.py:_ALLOWED_BASE_HOSTS` 2줄 추가로 해결(base.py API URL 불변 — 옛 도메인 API 여전히 작동, 실측). **라이브 브라우저 URL 실측이 근인 포착 — 신드리 "세션사망" 오진 정정**(스냅샷만 봐서 놓침)
- **인증 안정화(세션70~75)**: fchmod 0o600 + 좀비Chrome청소(`_cleanup_zombie_chrome`) + RTS 선제갱신(`_maybe_proactive_rts_refresh`) + about:blank 네비 레이스 픽스(세션74) + **headless single-flight**(세션75). cold(장기idle) `nlm login` hang 감시(`260720-153726`) — 신드리 ●●● ⓑ유지+감별프로토콜(도메인픽스 해소 개연성 상당하나 260720 리다이렉트 활성여부가 외부상태라 미확정)
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
- 세션77 (260731): **NLM 로그인 근본해결 — 도메인 리브랜딩**(TubeStation 세션41 크로스 핸드오프). 3중 인증실패 근인 = `notebooklm.google.com`→`notebook.google.com` 서버 리다이렉트를 `is_logged_in` 하드코딩이 못 읽음(라이브 브라우저 URL 실측으로 포착, 신드리 "세션사망" 오진 정정). `cdp.py`+`config.py` 2줄+회귀가드3+문서3곳. nlm login 즉시성공(745쿠키)·notebook_list 29개·1059 PASS. HANDOFF 삭제+todo청산. cold-hang 감시 신드리 ●●● ⓑ유지+감별프로토콜
- 세션76 (260728): todo3 conversation cache stats 관측 인프라 시공(이단시공) — `conversation_cache_stats` MCP tool + `cache_created_at`/`cache_age_seconds`(신드리: reset_client가 refresh_auth tool·프로필전환 시만 캐시drop, 캐시나이가 uptime보다 진짜 튜닝신호). 3자자문으로 todo2 핸드오프·todo4 재현선행 판정 + 신드리 사후개선 3건. 1056 PASS. 실tool 관측은 서버 재기동+`/exit` 재접속 후
- 세션75 (260727): refresh_auth 이중 headless Chrome 레이스 근본치료 — `cdp.py` 모듈 single-flight(`run_headless_auth`→`_run_headless_auth_impl` rename + wrapper, 결과공유·좀비가드90s). NLM 원안(클래스변수승격) 신드리 실측 반박(섀도잉 no-op)으로 기각→모듈락 합의. SOURCE_LIMIT_GUARD 감시 todo 청산. 1052 PASS (작업dir 미커밋)
- 세션74 (260721): headless 자동재인증 about:blank 네비 레이스 근본치료 — `c22776b`
- 세션72 (260720): RTS 선제갱신 `_maybe_proactive_rts_refresh` + editable(-e) 빌드 전환 — 1043 PASS. `6aed973`·`24a38f1`
- 세션71 (260719): Windows 좀비 Chrome 청소 `_cleanup_zombie_chrome`(`nlm login --clear` 반복 근본치료, SingletonLock은 POSIX전용) — 1037 PASS. `0ce10b2`
