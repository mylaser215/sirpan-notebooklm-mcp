# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260512-parser완수)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- **신설 도구 2종 (260512)** — 모두 해제, 본 흐름 사용 가능:
  - `source_replace_file(notebook_id, source_id, file_path, confirm=True)` ✅ NLM동기화 본 흐름. 디스크 직접 읽기 (Claude 토큰 0, 본 흐름 90%↓)
  - `notebook_clone(notebook_id, new_title, exclude_types=None)` ✅ markdown 무결성 보존 (raw_markdown=True 라우팅). 가드 코드 제거 완료
- **`get_source_fulltext`** parser 재작성 완료 — `raw_markdown: bool = False` 기본값 + 6개 모듈 헬퍼(_parse_segment/_parse_paragraph/_parse_table/_parse_content_block/_render_markdown_from_blocks/_unwrap_content_blocks). Graceful Degradation (`dict.get`/try-except + `mcp_logger.warning`)
- 글로벌 CLAUDE.md NLM동기화 절: 본 흐름 복원 (source_replace_file 단일 라우팅)
- fixture: `tests/fixtures/source_fulltext_2kb.json` (7 blocks + 14 unit cases) + `source_fulltext_36kb_full.json` (155 blocks, 9436 chars markdown)
- 33KB 회귀 실측: 47 H1/46 H2/28 H3/104 bullets, parser crash 0

## 핵심 todo
- `260512-053000`: `get_source_fulltext` 응답 트리 parser 재작성 → notebook_clone 100% 무결성 달성 (high)
  - hizoJc 응답에 paragraph/segment/table 메타 100% 보존됨 (Track A 캡처로 확정)
  - 변환 규칙·구현 단계 todo에 상세 박제

## 허브 추적
(없음 — 다음 세션에서 hub_tracking 등록 후 진행 권장)

## 최근 세션
- 세션 (260512): notebook_clone + source_replace_file 신설, NLM동기화 명세 통합, Track A로 100% 처방 확정
- 세션5 (260415): research_status 폴링 버그 수정 + nlm-proxy 완전 제거
</content>
</invoke>