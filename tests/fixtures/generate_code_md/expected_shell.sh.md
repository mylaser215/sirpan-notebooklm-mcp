---
source_path: sample_shell.sh
generated_at: 2026-09-04T19:47
original_sha256: c56091d6033beabb590b039d4bf7a4b77f5b750af8296ffcb51cd273897d3219
generator: scripts/generate_code_md.py
---

## 아키텍처 요약

(TODO: 사용자 정성 작성 — 본 모듈의 책임 / 핵심 설계 패턴 / 의존 관계를 3-5단락으로 요약. 재생성 시 본 섹션은 *그대로 보존됨* — 멱등성)

## 코드 구조

### `RUN_ID` (line 6, *variable*)

```bash
RUN_ID="demo-001"
```

### `MAX_ROUNDS` (line 7, *variable*)

```bash
readonly MAX_ROUNDS=3
```

### `CHAIN_CLAUDE_BIN` (line 8, *variable*)

```bash
export CHAIN_CLAUDE_BIN="${CHAIN_CLAUDE_BIN:-claude}"
```

### `QUEUE` (line 9, *variable*)

```bash
declare -a QUEUE=()
```

### `announce` (line 11, *function*)

```bash
function announce {
```

### `tally` (line 15, *function*)

```bash
function tally() {
```

### `run_round` (line 19, *function*)

```bash
run_round() {
```

### `main` (line 25, *function*)

```bash
main() {
```

## 원본 코드

```bash
#!/usr/bin/env bash
# Fixture for the .sh parser (세션554). Covers every SH_SYMBOL_PATTERNS branch:
# both `function` forms, the bare `name()` form, and modifier-prefixed vars.
set -euo pipefail

RUN_ID="demo-001"
readonly MAX_ROUNDS=3
export CHAIN_CLAUDE_BIN="${CHAIN_CLAUDE_BIN:-claude}"
declare -a QUEUE=()

function announce {
  echo "[chain] $1"
}

function tally() {
  echo "$(( $1 + $2 ))"
}

run_round() {
  local round="$1"
  announce "round ${round}/${MAX_ROUNDS}"
  return 0
}

main() {
  for round in $(seq 1 "${MAX_ROUNDS}"); do
    run_round "${round}"
  done
}

main "$@"
```
