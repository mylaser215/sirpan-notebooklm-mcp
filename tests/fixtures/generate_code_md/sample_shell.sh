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
