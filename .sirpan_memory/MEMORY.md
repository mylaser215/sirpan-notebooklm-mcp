# NotebookLM MCP Project Memory

## 볼트 문서 경로
- 세션아카이브: `000-시스템/070-세션로그/notebooklm-mcp_세션아카이브.md`
- 타임라인: `000-시스템/070-세션로그/notebooklm-mcp_작업타임라인.md`

## 현재 상태 (260514-세션37·v6 졸업·source_add 진단 종결)
- **NotebookLM MCP v0.5.23+** — Python/uv/FastMCP, 포트 9472
- GitHub: mylaser215/sirpan-notebooklm-mcp (fork from jacob-bd/notebooklm-mcp-cli)
- ✅ **v6 졸업** (세션36 26-05-13): NLM동기화 정책 대전환 단기3+중기3+장기4 = 10건 완료. 86→85 sources / 6건 정정안 적용 / JIT 14건 후속 식별 (별 세션) / Drift 5건 보존. `generate_py_md.py` + `fallback_to_text` 옵션 + 매트릭스 정정(꼬리 `.md` = 가공 SSOT) 박제. Developer-centric Bias 회고
- ✅ **세션37 source_add 진단 종결** (260514, commit `67a3eb7` + 16:21 후속 B-축소 실측): state-level 결함(가설 d, NLM 측 transient — fresh MCP+notebook 미재현) + Source-Note 라우팅은 별 결함 아님 확정 (v3 §10 `list_notes` 단일 권위 픽스가 이미 커버). `detail` 필드 8 wrappers — 재발 시 진단 보험
- ✅ v5 후속 — Studio 도메인 13건 픽스 (260513): R7cb6c 8 create + Q5 4. RPC 분류 패턴 확정 (create/poll/list/get/share/research=12-elem, modify/delete=11-elem)
- ✅ v5 본 9건 픽스 (260512): mind_map RPC ID + 도메인 통합 정렬
- ✅ v4 결함 픽스 (`c5b2928`): `_register_file_source` payload 3-slot+nested
- ✅ refresh_auth fail-close: RTS+headless 실패 시 명시적 `status:error`
- 회귀 영구 가드: v4 1건 + v5 9건 + Q5 후속 12건 + refresh_auth 5건 + sources detail 보강 = **27건+** Green

## 허브 추적
- [[NotebookLM MCP 안정화 프로젝트 (v6 — 동기화 정책 대전환·파일 종류별 분기·md 래핑 도구화)]] 💎 done-keep 졸업 (세션36 마감)
- [[NotebookLM MCP 안정화 프로젝트 (v5 — RPC payload 도메인 통합 정렬)]] 💎 done-keep
- [[NotebookLM MCP 안정화 프로젝트 (v4 — clone_add_file register RPC payload 구조 결함)]] 💎 done-keep

## 핵심 todo
- `260514-105956`: source_add state-level 결함 재발 모니터링 — `detail` 필드 보험 완료. 재발 시 dedup 또는 옛 source 정리로 우회 (NLM 측 transient, AI 직접 픽스 불가 도메인)
- `260513-1300-ts-codegen`: `.ts` 가공 도구 일반화 (`generate_py_md.py` 확장 또는 `generate_code_md.py`)
- `260513-015501`: NLM 동기화 보강 2종 후속 검토 (sirpan개선 세션330 크로스편집) — ① `source_replace_file` 원자 트랜잭션화 ② `.py` source_add 자동 `.md` 래핑
- `260513-000810`: 미매핑 RPC 3종 점검 (AUrzMb / JFMDGd / s0tc2d — `s0tc2d` 노트북 rename 신규 기능 후보)
- `260512-202103`: `run_headless_auth` 자체 안정화 (백그라운드 silent fail, ThreadPoolExecutor None 반환)
- `260512-173000`: `uv tool install --force` 캐시 결함 (우회 4-step 박제 — venv rm + `--no-cache --force`)

## 최근 세션
- 세션37 (260514): source_add state-level 진단 + 16:21 후속 B-축소 실측으로 Source-Note 라우팅 별 결함 아님 확정 (v3 §10 픽스 커버). `detail` 필드 8 wrappers 보강 (commit `67a3eb7`)
- 세션36 (260513): v6 장기 4/4 완료 — notebook_clone 신뢰성 검증 (86 sources 6분42초) + ROI 분류 + 1건 정리 + 매트릭스 정정 (꼬리 `.md`=가공 SSOT 회귀). Developer-centric Bias 회고 박제
- 세션35 (260513): v6 단기 3/3 + 중기 3/3 — `generate_py_md.py` 도구화 + `fallback_to_text` 옵션 + 매트릭스 박제. NLM 자문 conv `803fdca1` Q1~Q4 결정
- 세션34 (260513 v5후속): Studio 도메인 13건 픽스 (R7cb6c 8 create + Q5 4: poll/rename/delete/slide_revise). RPC 분류 패턴 확정
