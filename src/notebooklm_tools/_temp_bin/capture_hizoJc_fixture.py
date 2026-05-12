"""1회성 진단 — hizoJc RPC full raw response 캡처 + parser crash test.

Batch 1 마무리 회귀 검증 (plan zazzy-riding-newt §Batch 2 진입 전 #4):
- NLM source 09b5b979-... ([1] 시드 본문) full raw response 캡처 (~33KB)
- tests/fixtures/source_fulltext_36kb_full.json 박제
- _render_markdown_from_blocks(content_blocks) 호출 → 크래시 0 검증
- 2KB fixture에 없는 패턴 발견 시 보고 (H4+, depth 3+, table 중첩)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from notebooklm_tools.core.auth import load_cached_tokens
from notebooklm_tools.core.client import NotebookLMClient
from notebooklm_tools.core.sources import (
    _render_markdown_from_blocks,
    _unwrap_content_blocks,
)

NOTEBOOK_ID = "b2347c99-ca44-4e34-9f3d-1ea1424214b8"  # DSN 1호 클론 "MCP 문서 라우팅 결론 도출"
SOURCE_ID = "09b5b979-4f82-441f-ba52-8779267e1666"  # "[1] 시드 본문 — 260511_mcp문서라우팅고민_시드.md"


def _scan_patterns(blocks: list[Any]) -> dict[str, Any]:
    """Scan content blocks for patterns absent in the 2KB fixture."""
    findings: dict[str, Any] = {
        "total_blocks": 0,
        "paragraph_flags_seen": set(),
        "bullet_depths_seen": set(),
        "bullet_markers_seen": set(),
        "has_table": False,
        "has_h4_plus": False,
        "has_depth_3_plus": False,
        "h4_plus_examples": [],
        "depth_3_plus_examples": [],
        "table_examples": [],
    }
    for b in blocks:
        findings["total_blocks"] += 1
        if not isinstance(b, list):
            continue
        # Table heuristic
        if len(b) >= 5 and b[2] is None and b[3] is None and isinstance(b[4], list):
            findings["has_table"] = True
            if len(findings["table_examples"]) < 3:
                findings["table_examples"].append(repr(b[4])[:200])
            continue
        # Paragraph
        if len(b) >= 3 and isinstance(b[2], list) and len(b[2]) >= 2:
            paragraph_data = b[2]
            flags = paragraph_data[1] if isinstance(paragraph_data[1], list) else []
            kind = flags[1] if len(flags) > 1 else None
            if isinstance(kind, int):
                findings["paragraph_flags_seen"].add(kind)
                if kind >= 7:
                    findings["has_h4_plus"] = True
                    if len(findings["h4_plus_examples"]) < 3:
                        findings["h4_plus_examples"].append((kind, repr(b)[:200]))
            # Bullet meta
            if len(paragraph_data) > 3 and isinstance(paragraph_data[3], list):
                wrapper = paragraph_data[3]
                if len(wrapper) > 3 and isinstance(wrapper[3], dict):
                    meta = wrapper[3]
                    marker = meta.get("101")
                    depth = meta.get("104")
                    if isinstance(marker, str):
                        findings["bullet_markers_seen"].add(marker)
                    if isinstance(depth, int):
                        findings["bullet_depths_seen"].add(depth)
                        if depth >= 3:
                            findings["has_depth_3_plus"] = True
                            if len(findings["depth_3_plus_examples"]) < 3:
                                findings["depth_3_plus_examples"].append((depth, repr(b)[:200]))
    # Convert sets to sorted lists for JSON-friendly output
    findings["paragraph_flags_seen"] = sorted(findings["paragraph_flags_seen"])
    findings["bullet_depths_seen"] = sorted(findings["bullet_depths_seen"])
    findings["bullet_markers_seen"] = sorted(findings["bullet_markers_seen"])
    return findings


def main() -> int:
    tokens = load_cached_tokens()
    if not tokens:
        print("ERROR: No cached tokens. Run `nlm login` first.", file=sys.stderr)
        return 1

    client = NotebookLMClient(cookies=tokens.cookies)

    print("=" * 60)
    print(f"[1] hizoJc RPC raw response capture")
    print(f"    notebook: {NOTEBOOK_ID}")
    print(f"    source:   {SOURCE_ID}")
    print("=" * 60)
    params = [[SOURCE_ID], [2], [2]]
    t0 = time.time()
    result = client._call_rpc(client.RPC_GET_SOURCE, params, "/")
    elapsed = time.time() - t0
    raw_json = json.dumps(result, ensure_ascii=False, default=str)
    print(f"OK: RPC roundtrip {elapsed:.2f}s, raw response {len(raw_json)} chars")

    # Content blocks extraction (mirrors get_source_fulltext line 1155-1158)
    content_blocks: list[Any] = []
    if len(result) > 3 and isinstance(result[3], list):
        wrapper = result[3]
        if len(wrapper) > 0 and isinstance(wrapper[0], list):
            content_blocks = wrapper[0]
    print(f"content_blocks count: {len(content_blocks)}")

    print()
    print("=" * 60)
    print("[2] Pattern scan (2KB fixture에 없는 패턴 탐지)")
    print("=" * 60)
    # Unwrap nested wrapper to reach the real blocks array (same logic as parser)
    real_blocks = _unwrap_content_blocks(content_blocks)
    print(f"  (unwrap: {len(content_blocks)} wrapper -> {len(real_blocks)} real blocks)")
    findings = _scan_patterns(real_blocks)
    print(f"  total blocks         : {findings['total_blocks']}")
    print(f"  paragraph flags seen : {findings['paragraph_flags_seen']}")
    print(f"  bullet depths seen   : {findings['bullet_depths_seen']}")
    print(f"  bullet markers seen  : {findings['bullet_markers_seen']}")
    print(f"  has H4+              : {findings['has_h4_plus']}")
    print(f"  has depth 3+         : {findings['has_depth_3_plus']}")
    print(f"  has table            : {findings['has_table']}")
    if findings["h4_plus_examples"]:
        print("  H4+ examples:")
        for kind, snippet in findings["h4_plus_examples"]:
            print(f"    kind={kind}: {snippet}")
    if findings["depth_3_plus_examples"]:
        print("  depth 3+ examples:")
        for depth, snippet in findings["depth_3_plus_examples"]:
            print(f"    depth={depth}: {snippet}")
    if findings["table_examples"]:
        print("  table examples:")
        for snippet in findings["table_examples"]:
            print(f"    {snippet}")

    print()
    print("=" * 60)
    print("[3] _render_markdown_from_blocks crash test (full 33KB payload)")
    print("=" * 60)
    parser_status = "ok"
    parser_error: str | None = None
    rendered: str = ""
    try:
        rendered = _render_markdown_from_blocks(content_blocks)
        print(f"OK: rendered markdown {len(rendered)} chars, "
              f"{rendered.count(chr(10))} newlines, "
              f"{rendered.count('# ')} h1, "
              f"{rendered.count('## ')} h2, "
              f"{rendered.count('### ')} h3, "
              f"{rendered.count('- ')} bullets")
        print("\n--- first 500 chars ---")
        print(rendered[:500])
        print("\n--- last 500 chars ---")
        print(rendered[-500:])
    except Exception as e:
        parser_status = "crash"
        parser_error = f"{type(e).__name__}: {e}"
        print(f"PARSER CRASH: {parser_error}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 60)
    print("[4] Fixture 박제 → tests/fixtures/source_fulltext_36kb_full.json")
    print("=" * 60)
    repo_root = Path(__file__).resolve().parents[3]
    fixtures_dir = repo_root / "tests" / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)
    target = fixtures_dir / "source_fulltext_36kb_full.json"

    fixture = {
        "description": (
            "hizoJc RPC full raw response — source 09b5b979 "
            "([1] 시드 본문 — 260511_mcp문서라우팅고민_시드.md), "
            "captured live via _call_rpc."
        ),
        "captured_at_unix": int(time.time()),
        "notebook_id": NOTEBOOK_ID,
        "source_id": SOURCE_ID,
        "raw_response_length": len(raw_json),
        "content_blocks_count": len(content_blocks),
        "pattern_scan": findings,
        "parser_status": parser_status,
        "parser_error": parser_error,
        "rendered_markdown_length": len(rendered),
        "rendered_markdown_preview_first_500": rendered[:500],
        "rendered_markdown_preview_last_500": rendered[-500:],
        "content_blocks": content_blocks,
    }
    with target.open("w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=2)
    size = target.stat().st_size
    print(f"OK: wrote {target} ({size} bytes)")

    print()
    print("=" * 60)
    print(f"[5] Verdict")
    print("=" * 60)
    print(f"  parser status        : {parser_status}")
    if findings["has_h4_plus"]:
        print(f"  ⚠ H4+ 패턴 발견 (fixture 2KB에 없음) — _parse_paragraph 매핑 검증 필요")
    if findings["has_depth_3_plus"]:
        print(f"  ⚠ bullet depth 3+ 패턴 발견 — '  ' * depth 동적 식 검증 OK?")
    if findings["has_table"]:
        print(f"  ⚠ table 발견 (fixture에 없음) — _parse_table 실측 검증 필요")
    if parser_status == "ok" and not (findings["has_h4_plus"] or findings["has_table"]):
        print(f"  ✓ Batch 2 진입 안전 (parser crash 0, 2KB fixture로 충분)")
    return 0 if parser_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
