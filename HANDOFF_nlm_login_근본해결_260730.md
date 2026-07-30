# 핸드오프 — NLM 로그인/토큰 자동갱신 근본 해결

> 출처: TubeStation 세션41 (2026-07-30). 작성 세션에서 NLM 인증이 3중으로 실패해 자문·동기화가 막힘 → 반응형 자동복구(옵션 A/Layer 3)가 아니라 **근본 원인 규명·수정**을 별세션에 위임.
> 이 문서는 *실측 증거 + SSOT 포인터 + 질문*만 담는다 (해결책 미기재 — 가설/해결책 분리 원칙). 픽스는 이 세션에서 코드 확인 후.

## 0. 목표 (What / Why)
`nlm login` 및 토큰 자동 갱신이 반복 실패 → 세션 중 NotebookLM MCP 도구(`chat_configure`, `notebook_query_*`, `source_replace_file` 등)가 자주 `Authentication expired`로 죽는다. 3-Layer 자동복구가 *전부* 실패하는 상태를 관측했으므로, 임시 복구가 아니라 **왜 RTS가 만료되고 headless가 토큰을 못 만드는지** 근본 규명이 목표.

## 1. 이번 세션 실측 증거 (응답 문자열 그대로 — 재타이핑 아닌 복사)
1. `chat_configure(notebook_id=ee184826…, response_length="longer")` 1차 →
   `{"status":"error","error":"Failed to configure chat: Authentication recovery in progress (headless auth). Please retry in 15-20 seconds."}`
2. 약 15초 후 재시도 →
   `{"status":"error","error":"Failed to configure chat: Authentication expired. Run 'nlm login' in your terminal to re-authenticate."}`
3. `refresh_auth()` →
   `{"status":"error","error":"RTS token expired and headless auth failed. Run '! nlm login' manually.","hint":"Foreground nlm login (5-10s) is the reliable recovery path. Headless failure: headless auth returned no tokens"}`
4. Bash `timeout 90s nlm login` → stdout `Terminated`, exit `143` (90초 내 미완료).

## 2. 증상 3중 실패 요약
- **(A) RTS(refresh token store) 만료** — refresh_auth가 디스크 reload 실패.
- **(B) headless auth가 토큰 0개 반환** — "headless auth returned no tokens".
- **(C) foreground `nlm login`이 90s timeout** — 비대화(NonInteractive) Bash에서 완료 못 함 (대화형 Google 동의 대기 추정).
→ 3-Layer(reload → headless → background) 자동복구 경로가 순차로 전부 무너짐.

## 3. 환경
- OS: Windows 10, 셸: Git Bash + PowerShell (NonInteractive 하네스).
- 사용자 기본 브라우저: **Brave**. 관측 시점 **Chrome 미실행**. claude-in-chrome이 붙는 브라우저도 실은 Brave(TubeStation 세션41 발견).
- hint의 "foreground 5-10s reliable"이 실패 = `nlm login`이 여는 Chrome/브라우저 프로필의 **저장 세션이 만료**됐거나, headless가 그 프로필을 못 쓰는 정황.

## 4. 확인할 SSOT (CLAUDE.md 근거 — 반드시 코드로 재확인, 추측 금지)
- `core/base.py:_try_reload_or_headless_auth` — 3-Layer auth (reload→headless→background) 진입점.
- `errors.py` / `exceptions.py` — auth 예외 매핑 (**auth/refresh/token 도메인 자문 전 동봉 강제** — CLAUDE.md).
- RTS(refresh token store) — 정의·저장 위치·만료 조건 (`grep -ri "RTS\|refresh_token\|token_store"`).
- `refresh_auth` / `save_auth_tokens` / `nlm login` CLI 진입점 — `base.py`·`client.py` 호출 흐름 (자문 전 grep으로 호출 흐름 사전 확인).
- `HEADLESS_AUTH_DEADLOCK_TIMEOUT_SEC` (=60s 안전망) — headless 데드락 가드.
- Layer 3 `auth_recovery_in_progress` 상태 + `~/.claude/mcp-pids/nlm_renew.lock` (`mcp_http_ensure.py:_trigger_nlm_renew` L323 부근).
- SessionStart 백그라운드 hook `_trigger_nlm_renew` (선제 갱신 경로).
- `nlm login`이 사용하는 브라우저/프로필 지정 로직 (Chrome vs Brave 프로필 경로).

## 5. 근본 원인 후보 질문
1. **RTS가 왜 만료됐나** — refresh token 수명 만료? Google 측 revoke(보안)? 저장 파일 손상·삭제·경로 이동?
2. **headless가 왜 토큰 0개** — 브라우저 프로필 세션 만료? 프로필 경로 오지정? Brave 기본화로 Chrome 프로필 미갱신?
3. **foreground `nlm login`이 왜 timeout** — 대화형 동의 화면 대기? NonInteractive 환경에서 브라우저 창이 안 뜨거나 자동 진행 불가?
4. 근본 방향(예시 질문): refresh token 선제 갱신 주기 강화 / 프로필 경로 명시·검증 / 만료 사전 감지 후 사용자 1회 유도 UX / RTS 저장 무결성.

## 6. 하지 말 것 (환각·삽질 방어)
- 반응형 복구(옵션 A / Layer 3)는 이미 구현·존재 — *재구현 아님*. 목표는 원인 규명.
- 코드 미확인 상태의 추측·"당연히 이럴 것" 금지. auth 도메인은 `errors.py` + 진입점 grep 동봉 강제.
- **이 문제는 NLM 자체가 죽어 있어 NLM 자문 불가** → 교차검증은 **신드리 실측 감수**(`Agent subagent_type=sindri model=fable`) 또는 로컬 코드 Read로.
- 대화형 `nlm login`이 정말 필요하면 사용자에게 `! nlm login` 유도 (프롬프트 `!` 접두어 in-session).

## 7. 재현 절차
1. NLM 도구 호출(`refresh_auth` 또는 `chat_configure`) → auth error 확인.
2. `refresh_auth()` → `RTS token expired and headless auth failed` 재현.
3. `timeout 90s nlm login`(Bash) → 완료 vs timeout 관측 + stderr/stdout 로그 확보.
4. `nlm login` 로그 상세(verbose)·브라우저 실행 여부·프로필 경로 확인.

## 8. 관련 ADR / 노트 / 자문
- conv `21df4678` — auth ADR Q1-4 ●●● (`_try_reload_or_headless_auth` 3-Layer + 데드락 가드 Q4).
- conv `803fdca1` — fail-close fix (refresh_auth가 stale 토큰을 거짓 success로 반환 안 함).
- 허브: [[NotebookLM MCP 안정화 프로젝트 (v3)]]
- NLM 노트북(자문용): `f21a7e48-8113-4721-8ff4-3d358c737349` (sirpan-notebooklm-mcp 코어 자문) — 단, NLM 죽어있으면 접근 불가.
- CLAUDE.md 전역 §NLM동기화 인증 복구(옵션 A) / Layer 3 백그라운드 자동 갱신 절.

## 9. 시공 후 정리
- 픽스 확정·검증되면 이 파일 삭제(`HANDOFF_nlm_login_근본해결_260730.md`) + todo `sirpan-notebooklm-mcp` 채널의 대응 항목 청산.
