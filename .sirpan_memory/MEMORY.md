# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260415-2251)
- **NotebookLM MCP 서버** — Python/uv/FastMCP, 포트 9472 (직접 연결, 프록시 제거됨)
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- research_status 폴링 버그 수정 + 커밋 8963873 + 푸쉬 완료
- nlm-proxy(9474) 완전 제거: launcher, hook, 시스템맵 반영

## 허브 추적
(없음)

## 최근 세션
- 세션5 (260415): research_status 폴링 버그 수정 + nlm-proxy 완전 제거 + 문서 반영
- 세션4 (260415): research_status 폴링 버그 수정 — max_wait 기본값→0, 클램프 60초
