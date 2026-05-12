# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260512-v4결함발견)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **register RPC payload 구조 결함 픽스 완료 (260512 후반)** — `core/sources.py:_register_file_source` 1곳 (4-slot → 3-slot+nested). Composition 패턴으로 `notebook_clone`/`source_add(file)`/**`source_replace_file`** 3 도구 자동 회복. 사용자 캡쳐 Image #154129로 5요소 살아남 컨펌. NLM동기화 본 흐름 *자연 회복* (시간 지나면서 source_replace_file 호출되며 점진 markdown화)
- parser (`get_source_fulltext` raw_markdown 라우팅): 출력 markdown 자체는 정상으로 추정 (33KB 회귀 통과 — 단 표 회귀 *없음*). 결함은 *업로드 path*에 있음
- **두 도구 사용 매트릭스**: [[NotebookLM MCP 도구 사용 매트릭스]] (백업/실험=clone, 매일 동기화=replace_file)
- fixture: `tests/fixtures/source_fulltext_2kb.json` + `source_fulltext_36kb_full.json`

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] (V3/5 — 검증·픽스·자동확산 완료. milestone:3후반. Step 4 NLM 자문 + Step 5 마무리(회귀·CLAUDE.md·졸업) 남음)

## 핵심 todo
- `260512-133710`: NLM MCP 인증 만료 빈도 이슈 조사 (별도 도메인, 본 v4와 무관 — 이번 세션 중 2회 `Authentication expired` 발생)

## 최근 세션
- 세션 (260512 후반): 검증 클론 → v4 결함 발견 → 가설 8개 시계열 추적 → H로 좁힘 → v4 허브 박제. 100% 주장 사고 회고
- 세션 (260512 전반): notebook_clone + source_replace_file 신설, parser 재작성, 33KB 회귀 통과 (당시 markdown 무결성 *과대 평가*)
- 세션5 (260415): research_status 폴링 버그 수정 + nlm-proxy 완전 제거
