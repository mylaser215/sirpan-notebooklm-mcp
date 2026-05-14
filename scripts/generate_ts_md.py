"""Generate NLM RAG-friendly `.ts.md` wrappers from TypeScript source files.

Wraps `<ts_path>` into `<ts_path>.md` with three H2 sections:
    ## 아키텍처 요약       — manual summary (idempotently preserved across re-runs)
    ## 코드 구조           — regex-extracted top-level symbols
    ## 원본 코드           — full source body in a ```typescript fenced block

Frontmatter records `source_path`, `generated_at`, and `original_sha256` so stale
detection is content-based (immune to mtime / git-stash false positives).

Companion to `scripts/generate_py_md.py` (Python AST variant). Interface
intentionally mirrors that script — same flags, same output shape. TypeScript
lacks a stdlib AST module, so symbol extraction is regex-based and limited to
top-level `function` / arrow-const / `class` / `interface` / `type` / `enum`
declarations. Nested or dynamically-defined symbols are intentionally skipped.

Usage:
    uv run python scripts/generate_ts_md.py <ts_path>
    uv run python scripts/generate_ts_md.py <ts_path> --out <md_path>
    uv run python scripts/generate_ts_md.py <ts_path> --force
    uv run python scripts/generate_ts_md.py <ts_path> --check    # exit 0=fresh, 1=stale, 2=missing
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

SUMMARY_PLACEHOLDER = (
    "(TODO: 사용자 정성 작성 — 본 모듈의 책임 / 핵심 설계 패턴 / 의존 관계를 3-5단락으로 요약. "
    "재생성 시 본 섹션은 *그대로 보존됨* — 멱등성)"
)

SUMMARY_BLOCK_RE = re.compile(
    r"^## 아키텍처 요약\s*\n(?P<body>.*?)(?=^## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# Top-level symbol extractors. Each pattern captures the *symbol name* in
# group 1 and matches at column 0 (no indentation) to avoid catching nested
# helpers. `re.MULTILINE` makes `^` match the start of each line.
SYMBOL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("function", re.compile(r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)\s*[<(]", re.MULTILINE)),
    ("arrow", re.compile(r"^(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+(\w+)\s*(?::[^=\n]+)?=\s*(?:async\s+)?(?:\([^)]*\)|\w+)\s*(?::[^=\n]+)?\s*=>", re.MULTILINE)),
    ("class", re.compile(r"^(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)),
    ("interface", re.compile(r"^(?:export\s+)?interface\s+(\w+)", re.MULTILINE)),
    ("type", re.compile(r"^(?:export\s+)?type\s+(\w+)\s*[<=]", re.MULTILINE)),
    ("enum", re.compile(r"^(?:export\s+)?(?:const\s+)?enum\s+(\w+)", re.MULTILINE)),
]


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _line_of(source: str, offset: int) -> int:
    """Return 1-indexed line number for a character offset in source."""
    return source.count("\n", 0, offset) + 1


def _signature_line(source: str, offset: int) -> str:
    """Return the source line at offset (no trailing newline)."""
    start = source.rfind("\n", 0, offset) + 1
    end = source.find("\n", offset)
    if end == -1:
        end = len(source)
    return source[start:end].rstrip()


def parse_module(path: Path) -> dict:
    """Extract top-level TypeScript symbols via regex."""
    source = path.read_text(encoding="utf-8")
    items: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for kind, pattern in SYMBOL_PATTERNS:
        for m in pattern.finditer(source):
            name = m.group(1)
            line = _line_of(source, m.start())
            key = (name, line)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "kind": kind,
                    "name": name,
                    "signature": _signature_line(source, m.start()),
                    "lineno": line,
                }
            )
    items.sort(key=lambda x: (x["lineno"], x["name"]))
    return {"items": items, "source": source}


def extract_existing_summary(md_path: Path) -> str | None:
    """Return the body of `## 아키텍처 요약` if present (idempotency).

    Strips trailing whitespace but preserves internal structure. Returns None
    when the section is absent or matches the placeholder marker (so the marker
    doesn't get propagated indefinitely).
    """
    if not md_path.exists():
        return None
    text = md_path.read_text(encoding="utf-8")
    m = SUMMARY_BLOCK_RE.search(text)
    if not m:
        return None
    body = m.group("body").strip()
    if not body or body.startswith("(TODO:"):
        return None
    return body


def render_md(
    ts_path: Path,
    parsed: dict,
    sha256: str,
    existing_summary: str | None,
    timestamp: str,
    source_path_rel: str,
) -> str:
    lines: list[str] = []
    # Frontmatter
    lines.append("---")
    lines.append(f"source_path: {source_path_rel}")
    lines.append(f"generated_at: {timestamp}")
    lines.append(f"original_sha256: {sha256}")
    lines.append("generator: scripts/generate_ts_md.py")
    lines.append("---")
    lines.append("")

    # 1. 아키텍처 요약 (수동 정성 — 멱등성 보존)
    lines.append("## 아키텍처 요약")
    lines.append("")
    lines.append(existing_summary if existing_summary else SUMMARY_PLACEHOLDER)
    lines.append("")

    # 2. 코드 구조 (regex 추출)
    lines.append("## 코드 구조")
    lines.append("")
    items = parsed["items"]
    if not items:
        lines.append("*(top-level 심볼 없음)*")
        lines.append("")
    else:
        for item in items:
            sig = item["signature"]
            lines.append(f"### `{item['name']}` (line {item['lineno']}, *{item['kind']}*)")
            lines.append("")
            lines.append(f"```typescript\n{sig}\n```")
            lines.append("")

    # 3. 원본 코드 (최하단)
    lines.append("## 원본 코드")
    lines.append("")
    lines.append("```typescript")
    lines.append(parsed["source"].rstrip("\n"))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def check_stale(ts_path: Path, md_path: Path) -> int:
    """Return 0 (fresh), 1 (stale), 2 (missing md)."""
    if not md_path.exists():
        return 2
    current = compute_sha256(ts_path)
    md_text = md_path.read_text(encoding="utf-8")
    m = re.search(r"^original_sha256:\s*(?P<hash>[0-9a-f]+)\s*$", md_text, re.MULTILINE)
    if not m:
        return 1
    return 0 if m.group("hash") == current else 1


def _default_md_path(ts_path: Path) -> Path:
    """Compute `<basename>.ts.md` (or `.tsx.md`) sibling path.

    `Path.with_suffix` only replaces the final suffix, so we splice the
    output name manually to preserve the full original extension.
    """
    return ts_path.with_name(ts_path.name + ".md")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate NLM RAG-friendly .ts.md wrapper for a TypeScript source file.",
    )
    parser.add_argument("ts_path", type=Path, help="Path to the .ts/.tsx file to wrap")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .md path (default: <ts_path>.md alongside the source)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when SHA256 matches (default: skip if fresh)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Stale check only; exit 0=fresh, 1=stale, 2=missing. No write.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root for relative source_path (default: cwd)",
    )
    args = parser.parse_args()

    ts_path: Path = args.ts_path.resolve()
    if not ts_path.exists():
        print(f"error: file not found: {ts_path}", file=sys.stderr)
        return 2
    if ts_path.suffix not in {".ts", ".tsx"}:
        print(f"error: expected a .ts or .tsx file: {ts_path}", file=sys.stderr)
        return 2

    md_path: Path = args.out.resolve() if args.out else _default_md_path(ts_path)

    if args.check:
        status = check_stale(ts_path, md_path)
        label = {0: "fresh", 1: "stale", 2: "missing"}[status]
        print(f"{label}: {md_path}")
        return status

    current_sha = compute_sha256(ts_path)
    if not args.force and check_stale(ts_path, md_path) == 0:
        print(f"skip (fresh): {md_path}")
        return 0

    existing_summary = extract_existing_summary(md_path)
    parsed = parse_module(ts_path)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    root = (args.root.resolve() if args.root else Path.cwd())
    try:
        source_path_rel = str(ts_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        source_path_rel = str(ts_path).replace("\\", "/")

    rendered = render_md(
        ts_path=ts_path,
        parsed=parsed,
        sha256=current_sha,
        existing_summary=existing_summary,
        timestamp=timestamp,
        source_path_rel=source_path_rel,
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(rendered, encoding="utf-8")
    print(f"wrote: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
