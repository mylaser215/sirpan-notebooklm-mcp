# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260528-세션50·v7 detect_drift 결정론 매칭 전환 시공)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **세션50 완료** (260528): v7 detect_drift 결정론 매칭 — 단교차삼단시공 풀오토. NLM ●●● C안 채택. ATOM-1(`DUP_FILENAMES_AUTO_FOLDER_TAG` 자동 폴더명 박제) + ATOM-2(`_narrow_by_folder_hint` 일반화) + ATOM-3(회귀 가드 4건). 891 PASS / 0 fail. v7 허브 NLM 신규 등록 (`8763a0da-...`). 잔재 5건 청소는 사용자 수동 (NLM 메타데이터 부재)
- ✅ **세션47 완료** (260526): 도구 발견 패턴 정착 — 글로벌 `CLAUDE.md` *Discoverability* Bullet + `__시스템맵.md` §5 NLM cross-link 매트릭스 신설
- ✅ **세션46 완료** (260525): `research_import` 픽스 — NLM `LBwxtb` slot 0 envelope + deep report body 주입 + parse 신구조 2종. 회귀 7건. 검증 35→38건 import
- ✅ **세션45 완료** (260521): ATOM-2 시공 — `detect_drift` MCP tool화. 880 PASS
- ✅ **묶음D 완료** (세션43): `replace_source_file(atomic=True)` + `add_file(auto_wrap_to_md=True)` opt-in
- ✅ **v6 졸업** (세션36): NLM동기화 정책 대전환 10건
- 회귀 영구 가드: v4 1건 + v5 9건 + Q5 12건 + refresh_auth 5건 + ATOM-1·2 8건 + research_import 7건 + v7 4건 = **46건+** Green

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v7 — detect_drift 결정론 매칭 전환)]] ⚡ focus (시공 3/5 완료, 잔재 5건 청소 + 외부검증 대기)
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260525-025900-research-import-residual-skip-3`: 41→38 잔존 3건 미import 분석 (별 세션 e3bVqc raw 캡쳐부터)
- `260523-015000-media-source-expansion-plan`: NLM 멀티미디어 소스 확장 (별 세션 단서 캡쳐 후 시공)
- `260515-025300-atomic-trial-monitoring`: `source_replace_file(atomic=True)` trial (1건 누적)

## 최근 세션
- 세션50 (260528): v7 detect_drift 결정론 매칭 — 단교차삼단시공 풀오토. NLM ●●● C안. ATOM 3 시공 891 PASS. v7 허브 NLM 등록
- 세션47 (260526): 도구 발견 패턴 정착 — Discoverability + cross-link 매트릭스
- 세션46 (260525): `research_import` 픽스 — `LBwxtb` slot 0 envelope. 회귀 7건. 35→38건
- 세션45 (260521): ATOM-2 시공 — `detect_drift` MCP tool화. 880 PASS
- 세션44 (260515): 단교차삼단시공 — `scripts/generate_code_md.py` 통합. 870 PASS
