# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260526-세션47·도구 발견 패턴 정착·Discoverability + cross-link 매트릭스)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **세션47 완료** (260526): 도구 발견 패턴 정착 — 글로벌 `CLAUDE.md` *Discoverability* Bullet + `__시스템맵.md` §5 NLM cross-link 매트릭스 신설. NLM 자문 conv `803fdca1` 2회 ●●● + 동기화 7건 success. todo `260523-011412` 완료
- ✅ **세션46 완료** (260525): `research_import` 픽스 — NLM 백엔드 schema 변경 대응. `LBwxtb` 슬롯 0 envelope `[2, null, null, [1, null×9, [1]]]` inject + deep report `body` 주입 + `_parse_research_sources` 신구조 분기 2종 (`src[1]=[title,body]` deep / `src[2]=[url,title]` web). 실측 검증 2회: 35건+38건 import 성공 (이전 0건 silent drop). 회귀 7건 신규 (`TestNewNLMSourceShape`) + 실측 fixture 박제
- ✅ **세션45 완료** (260521): ATOM-2 시공 — `detect_drift` MCP tool화 (이단시공). 880 PASS + 라이브 검증 + 글로벌 CLAUDE.md ⑥단계 교체
- ✅ **묶음D 완료** (세션43 26-05-15): NLM 동기화 보강 2종 — `replace_source_file(atomic=True)` + `add_file(auto_wrap_to_md=True)` + 글로벌 CLAUDE.md 박제. opt-in default False (Ghost ID 회귀 차단 trial)
- ✅ **v6 졸업** (세션36 26-05-13): NLM동기화 정책 대전환 10건. `generate_py_md.py` + `fallback_to_text` + 매트릭스 정정 박제
- ✅ v5 후속 Studio 13건 + v5 본 9건 + v4 결함 픽스 + refresh_auth fail-close
- 회귀 영구 가드: v4 1건 + v5 9건 + Q5 12건 + refresh_auth 5건 + sources detail + ATOM-1·2 8건 + research_import 7건 = **42건+** Green

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep 졸업 (세션36 마감)
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260525-025900-research-import-residual-skip-3`: 41→38 잔존 3건 미import 분석 (세션46 검증). url 빈 source skip 로직 정정 또는 신규 src 구조 분기. 별 세션에서 e3bVqc raw 캡쳐부터
- `260523-015000-media-source-expansion-plan`: NLM 멀티미디어 소스 확장 (유튜브/이미지/오디오/비디오). 파일 다이얼로그 확장자 ~40종 실측 + 4종 UI 분류. 별 세션 단서 캡쳐 후 시공
- `260515-025300-atomic-trial-monitoring`: `source_replace_file(atomic=True)` trial (1건 누적, N건 후 default 승격)

## 최근 세션
- 세션47 (260526): 도구 발견 패턴 정착 — 글로벌 `CLAUDE.md` *Discoverability* Bullet + `__시스템맵.md` §5 NLM cross-link 매트릭스 신설. NLM 자문 conv `803fdca1` 2회 ●●● + 동기화 7건 success. todo `260523-011412` 완료
- 세션46 (260525): `research_import` 픽스 — NLM `LBwxtb` slot 0 envelope + deep report body 주입 + parse 신구조 2종. 회귀 7건. 검증 2회 (35→38건 import). c:\2.txt 사용자 실측 캡쳐 기반. CHANGELOG `[Unreleased]` 항목 추가
- 세션45 (260521): ATOM-2 시공 — `detect_drift` MCP tool화 (이단시공). 880 PASS + 라이브 검증 + 글로벌 CLAUDE.md ⑥단계 교체
- 세션44 (260515): 단교차삼단시공 + 0단 — `scripts/generate_*_md.py` 2 도구 통합 (NLM ●●● B안, 870 회귀 PASS) + 부산물 2건 (`AUrzMb` RPC 매핑 + 🔭 감시 todo 규약 신설)
- 세션43 (260515): 묶음D 배치교차삼단시공 — `atomic=True` + `auto_wrap_to_md=True` + 글로벌 CLAUDE.md 박제. 회귀 860 PASS
