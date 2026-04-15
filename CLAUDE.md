# NotebookLM MCP Server & CLI

NotebookLM 프로그래밍 접근을 위한 MCP 서버 + CLI.

## 기술 스택
- Python >=3.11 / uv
- FastMCP (MCP 서버) + CLI (`nlm`)

## 구조
- `src/notebooklm_tools/services/` — 비즈니스 로직 (모든 도메인)
- `src/notebooklm_tools/mcp/` — MCP 도구 (services 래퍼)
- `src/notebooklm_tools/cli/` — CLI 명령 (services 래퍼)
- `src/notebooklm_tools/core/` — 저수준 API 클라이언트

## 빌드 & 실행
```bash
uv tool install .                          # 설치
uv cache clean && uv tool install --force . # 코드 변경 후 재설치
notebooklm-mcp                             # MCP 서버 (stdio)
notebooklm-mcp --transport http --port 9472 # HTTP 모드
uv run pytest                               # 테스트
```

## 인증
- 쿠키 기반: Chrome DevTools에서 Cookie 헤더 추출 → `save_auth_tokens(cookies=...)` 또는 `nlm login`
- 만료 시: Chrome DevTools에서 새 쿠키 재추출
- 프로필: `~/.notebooklm-mcp-cli/profiles/<name>/auth.json`

## 인프라
- 포트: 9472 (HTTP 모드)
- `~/.claude.json`에 MCP 등록
- confirm 필요 도구: notebook_delete, source_delete, source_sync_drive, studio_*, note_delete
