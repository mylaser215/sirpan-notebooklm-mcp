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

### uv 캐시 결함 우회 (재설치 후 코드 갱신 실패 시)
위 `uv cache clean && uv tool install --force` 후에도 `~/AppData/Roaming/uv/tools/notebooklm-mcp-cli/Lib/site-packages/`의 코드가 *옛 버전*인 경우 (v4 ATOM-4 발견 + 세션36 재현 입증). `--force`가 metadata만 갱신하고 file copy를 skip하는 케이스로 추정:
```bash
python ~/bin/mcp_launcher.py stop notebooklm
rm -rf ~/AppData/Roaming/uv/tools/notebooklm-mcp-cli
uv tool install --no-cache --force .       # --no-cache 명시 필수
python ~/bin/mcp_launcher.py start notebooklm
```

## 인증
- 쿠키 기반: Chrome DevTools에서 Cookie 헤더 추출 → `save_auth_tokens(cookies=...)` 또는 `nlm login`
- 만료 시: Chrome DevTools에서 새 쿠키 재추출
- 프로필: `~/.notebooklm-mcp-cli/profiles/<name>/auth.json`

## 인프라
- 포트: 9472 (HTTP 모드)
- `~/.claude.json`에 MCP 등록
- confirm 필요 도구: notebook_delete, source_delete, source_sync_drive, studio_*, note_delete
