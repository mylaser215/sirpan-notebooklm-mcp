"""One-shot script: build tests/fixtures/source_fulltext_2kb.json.

Extracts 7 valid content blocks from ~/.claude/mcp-logs/notebooklm.log
line 11920~11955 (2026-05-06 22:12:51 hizoJc RPC raw response for
source 4455b0f4-... CLAUDE.md), captures the canonical markdown
expected output (hand-traced from paragraph_flags + bullet meta), and
dumps to tests/fixtures/source_fulltext_2kb.json for unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path

# 7 valid content blocks (raw response was truncated to 2KB by DEBUG log,
# block 8 was cut mid-bullet-meta — skipped here, still 7 blocks span all
# critical patterns: H1, H2, bullet depth 0/1/2/3, inline code, bold).
CONTENT_BLOCKS = [
    # Block 1: H1 "전역 설정"
    [0, 5, [[[0, 5, ["전역 설정"]]], [None, 4]]],
    # Block 2: H2 "응답"
    [5, 7, [[[5, 7, ["응답"]]], [None, 5]]],
    # Block 3: bullet depth=0
    [7, 49, [
        [[7, 49, ['한국어 응답. 핵심 먼저, 전문용어 괄호 설명, 불확실 시 "~할 수 있음"']]],
        [None, 1],
        None,
        [None, None, 0, {"101": "•", "102": 1, "103": 1, "104": 0}],
    ]],
    # Block 4: bullet depth=1
    [49, 117, [
        [[49, 117, ['답변 깊이: 단순→즉답 / 관점 대립→교차검증 / 복잡→원자분해 / 중요 판단→자기반박 / 복합→조합+"적용 패턴: __"']]],
        [None, 1],
        None,
        [None, None, 0, {"101": "•", "102": 1, "103": 2, "104": 1}],
    ]],
    # Block 5: bullet depth=2 with 4 inline code segments
    [117, 341, [
        [
            [117, 167, ["맥락 출처 명시: SIR-PAN 아키텍처·정책·과거 의사결정을 설명/적용할 때 문장 끝에 "]],
            [167, 187, ["(출처: [[원본노트명]], 세션N)", [None, None, None, None, None, None, None, True]]],
            [187, 207, [" 인라인 위키링크. RAG 결과 중 "]],
            [207, 216, ["[과거 히스토리]", [None, None, None, None, None, None, None, True]]],
            [216, 235, [" 표기는 과거 논의이므로 SSOT("]],
            [235, 244, ["__시스템맵.md", [None, None, None, None, None, None, None, True]]],
            [244, 281, [" 등)와 교차검증 필수. RAG Top-K가 히스토리로만 편중되면 "]],
            [281, 290, ["sirpanrag", [None, None, None, None, None, None, None, True]]],
            [290, 341, [" semantic_search로 SSOT를 명시적 추가 검색(Active Retrieval)"]],
        ],
        [None, 1],
        None,
        [None, None, 0, {"101": "•", "102": 1, "103": 3, "104": 2}],
    ]],
    # Block 6: bullet depth=3 with bold + 3 inline code segments
    [341, 488, [
        [
            [341, 349, ["마크다운 이탤릭", [True]]],
            [349, 351, [": "]],
            [351, 352, ["*", [None, None, None, None, None, None, None, True]]],
            [352, 358, ["만 사용 ("]],
            [358, 359, ["_", [None, None, None, None, None, None, None, True]]],
            [359, 410, [" 금지 — Obsidian Reading Mode에서 snake_case 식별자와 충돌). "]],
            [410, 411, ["_", [None, None, None, None, None, None, None, True]]],
            [411, 488, [" 포함 기술 식별자(파일명·변수명·함수명)는 반드시 백틱으로 감쌀 것 (상세: [[Obsidian 언더스코어 이탤릭 렌더링 버그 방어]])"]],
        ],
        [None, 1],
        None,
        [None, None, 0, {"101": "•", "102": 1, "103": 4, "104": 3}],
    ]],
    # Block 7: H2 "사용자 맥락"
    [488, 494, [[[488, 494, ["사용자 맥락"]]], [None, 5]]],
]

# Hand-traced from paragraph_flags + bullet meta + segment format flags.
# Rules: paragraph flag 4/5/6 -> # ## ###; bullet (flag 1 + meta) -> "  "*depth + "- ";
# segment flag[0]=true -> **bold**; flag[7]=true -> `inline code`; flag[0]+flag[7] -> **`bold inline`**.
# Block separator: consecutive bullets -> "\n"; otherwise -> "\n\n".
EXPECTED_MARKDOWN = (
    "# 전역 설정\n\n"
    "## 응답\n\n"
    '- 한국어 응답. 핵심 먼저, 전문용어 괄호 설명, 불확실 시 "~할 수 있음"\n'
    '  - 답변 깊이: 단순→즉답 / 관점 대립→교차검증 / 복잡→원자분해 / 중요 판단→자기반박 / 복합→조합+"적용 패턴: __"\n'
    "    - 맥락 출처 명시: SIR-PAN 아키텍처·정책·과거 의사결정을 설명/적용할 때 문장 끝에 "
    "`(출처: [[원본노트명]], 세션N)` 인라인 위키링크. RAG 결과 중 `[과거 히스토리]` 표기는 과거 논의이므로 "
    "SSOT(`__시스템맵.md` 등)와 교차검증 필수. RAG Top-K가 히스토리로만 편중되면 `sirpanrag` "
    "semantic_search로 SSOT를 명시적 추가 검색(Active Retrieval)\n"
    "      - **마크다운 이탤릭**: `*`만 사용 (`_` 금지 — Obsidian Reading Mode에서 snake_case 식별자와 충돌). "
    "`_` 포함 기술 식별자(파일명·변수명·함수명)는 반드시 백틱으로 감쌀 것 "
    "(상세: [[Obsidian 언더스코어 이탤릭 렌더링 버그 방어]])\n\n"
    "## 사용자 맥락"
)

# Micro unit test cases — each is one input + expected output covering
# a single transformation rule. Used by individual parametrize tests.
UNIT_CASES = {
    "segment_plain": {
        "input": [0, 5, ["전역 설정"]],
        "expected": "전역 설정",
    },
    "segment_bold": {
        "input": [341, 349, ["마크다운 이탤릭", [True]]],
        "expected": "**마크다운 이탤릭**",
    },
    "segment_italic_asterisk": {
        "input": [0, 10, ["italic text", [None, True]]],
        "expected": "*italic text*",
    },
    "segment_inline_code": {
        "input": [281, 290, ["sirpanrag", [None, None, None, None, None, None, None, True]]],
        "expected": "`sirpanrag`",
    },
    "segment_bold_inline_code": {
        "input": [0, 10, ["bold code", [True, None, None, None, None, None, None, True]]],
        "expected": "**`bold code`**",
    },
    "paragraph_h1": {
        "input": [0, 5, [[[0, 5, ["전역 설정"]]], [None, 4]]],
        "expected": "# 전역 설정",
    },
    "paragraph_h2": {
        "input": [5, 7, [[[5, 7, ["응답"]]], [None, 5]]],
        "expected": "## 응답",
    },
    "paragraph_h3": {
        "input": [0, 10, [[[0, 10, ["H3 heading"]]], [None, 6]]],
        "expected": "### H3 heading",
    },
    "paragraph_bullet_depth_0": {
        "input": [7, 49, [[[7, 49, ["item zero"]]], [None, 1], None, [None, None, 0, {"101": "•", "102": 1, "103": 1, "104": 0}]]],
        "expected": "- item zero",
    },
    "paragraph_bullet_depth_1": {
        "input": [49, 60, [[[49, 60, ["item one"]]], [None, 1], None, [None, None, 0, {"101": "•", "102": 1, "103": 2, "104": 1}]]],
        "expected": "  - item one",
    },
    "paragraph_bullet_depth_2": {
        "input": [60, 70, [[[60, 70, ["item two"]]], [None, 1], None, [None, None, 0, {"101": "•", "102": 1, "103": 3, "104": 2}]]],
        "expected": "    - item two",
    },
    "paragraph_numbered_bullet": {
        "input": [0, 10, [[[0, 10, ["numbered"]]], [None, 1], None, [None, None, 0, {"101": "1.", "102": 1, "103": 1, "104": 0}]]],
        "expected": "1. numbered",
    },
    "paragraph_unknown_flag_fallback": {
        "input": [0, 10, [[[0, 10, ["unknown flag text"]]], [None, 99]]],
        "expected": "unknown flag text",  # plain text + logger.warning
    },
    "table_basic_2x2": {
        "input": [0, 100, None, None, [2, 2, [[[0, 10, [["c1"]]], [10, 20, [["c2"]]]], [[20, 30, [["r1"]]], [30, 40, [["r2"]]]]]]],
        "expected": "| c1 | c2 |\n|---|---|\n| r1 | r2 |",
    },
}


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    fixtures_dir = repo_root / "tests" / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    target = fixtures_dir / "source_fulltext_2kb.json"

    fixture = {
        "description": (
            "hizoJc RPC raw response 2KB excerpt (7 content blocks) — "
            "source 4455b0f4-... (CLAUDE.md), captured 2026-05-06 22:12:51."
        ),
        "captured_from": "~/.claude/mcp-logs/notebooklm.log line 11920~11955",
        "source_id": "4455b0f4-4c75-43e3-8d9b-39da2b3cfcc8",
        "notes": (
            "Block 8 was truncated by DEBUG log's first-2000-chars limit. "
            "Block separator rule: consecutive bullets join with '\\n', "
            "otherwise '\\n\\n'. Italic uses '*' (Obsidian _-conflict avoidance)."
        ),
        "unit_cases": UNIT_CASES,
        "integration_content_blocks": CONTENT_BLOCKS,
        "integration_expected_markdown": EXPECTED_MARKDOWN,
    }

    with target.open("w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)

    size = target.stat().st_size
    print(f"OK: wrote {target} ({size} bytes, {len(CONTENT_BLOCKS)} blocks, {len(UNIT_CASES)} unit cases)")


if __name__ == "__main__":
    main()
