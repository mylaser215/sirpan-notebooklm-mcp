"""Generate NLM RAG-friendly `.py.md` wrappers from Python source files.

Wraps `<py_path>` into `<py_path>.md` with three H2 sections:
    ## 아키텍처 요약       — manual summary (idempotently preserved across re-runs)
    ## 함수별 역할          — AST-extracted class/function signatures + first-line docstring
    ## 원본 코드            — full source body in a ```python fenced block

Frontmatter records `source_path`, `generated_at`, and `original_sha256` so stale
detection is content-based (immune to mtime / git-stash false positives).

v6 중기 ② (세션35, NLM 자문 conv 803fdca1):
    - Q1 권고: 다중 H2 분리 + 함수별 H3 + 원본 코드 최하단 + FM SHA256
    - Q2 권고: 옵션 D 하이브리드 — AST 결정론 + `## 아키텍처 요약`만 LLM/수동
    - Q3 권고: 옵션 C — 컨텐츠 SHA256 비교 (git/mtime 의존 X)

Usage:
    uv run python scripts/generate_py_md.py <py_path>
    uv run python scripts/generate_py_md.py <py_path> --out <md_path>
    uv run python scripts/generate_py_md.py <py_path> --force
    uv run python scripts/generate_py_md.py <py_path> --check    # exit 0=fresh, 1=stale, 2=missing
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import ast
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


def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _first_line(docstring: str | None) -> str:
    if not docstring:
        return ""
    for line in docstring.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a readable signature string from an AST function node."""
    try:
        args_src = ast.unparse(node.args)
    except Exception:
        args_src = "..."
    returns = ""
    if node.returns is not None:
        try:
            returns = f" -> {ast.unparse(node.returns)}"
        except Exception:
            returns = ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args_src}){returns}"


def parse_module(path: Path) -> dict:
    """Extract module docstring + top-level class/function metadata via AST."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    module_doc = ast.get_docstring(tree) or ""

    items: list[dict] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_doc = ast.get_docstring(node) or ""
            methods: list[dict] = []
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(
                        {
                            "kind": "method",
                            "name": sub.name,
                            "signature": _signature(sub),
                            "doc": _first_line(ast.get_docstring(sub)),
                            "lineno": sub.lineno,
                        }
                    )
            items.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "signature": f"class {node.name}",
                    "doc": _first_line(class_doc),
                    "lineno": node.lineno,
                    "methods": methods,
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "signature": _signature(node),
                    "doc": _first_line(ast.get_docstring(node)),
                    "lineno": node.lineno,
                }
            )

    return {"module_doc": module_doc, "items": items, "source": source}


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
    py_path: Path,
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
    lines.append("generator: scripts/generate_py_md.py")
    lines.append("---")
    lines.append("")

    # 1. 아키텍처 요약 (수동 정성 — 멱등성 보존)
    lines.append("## 아키텍처 요약")
    lines.append("")
    lines.append(existing_summary if existing_summary else SUMMARY_PLACEHOLDER)
    lines.append("")

    # 2. 함수별 역할 (AST 자동)
    lines.append("## 함수별 역할")
    lines.append("")
    module_doc = parsed["module_doc"]
    if module_doc:
        first = _first_line(module_doc)
        if first:
            lines.append(f"*모듈 docstring*: {first}")
            lines.append("")

    items = parsed["items"]
    if not items:
        lines.append("*(top-level 클래스/함수 없음)*")
        lines.append("")
    else:
        for item in items:
            sig = item["signature"]
            doc = item["doc"]
            lineno = item["lineno"]
            lines.append(f"### `{item['name']}` (line {lineno})")
            lines.append("")
            lines.append(f"```python\n{sig}\n```")
            if doc:
                lines.append("")
                lines.append(doc)
            if item["kind"] == "class" and item.get("methods"):
                lines.append("")
                lines.append("**Methods**:")
                for m in item["methods"]:
                    method_line = f"- `{m['name']}` (line {m['lineno']})"
                    if m["doc"]:
                        method_line += f" — {m['doc']}"
                    lines.append(method_line)
            lines.append("")

    # 3. 원본 코드 (최하단)
    lines.append("## 원본 코드")
    lines.append("")
    lines.append("```python")
    lines.append(parsed["source"].rstrip("\n"))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def check_stale(py_path: Path, md_path: Path) -> int:
    """Return 0 (fresh), 1 (stale), 2 (missing md)."""
    if not md_path.exists():
        return 2
    current = compute_sha256(py_path)
    md_text = md_path.read_text(encoding="utf-8")
    m = re.search(r"^original_sha256:\s*(?P<hash>[0-9a-f]+)\s*$", md_text, re.MULTILINE)
    if not m:
        return 1
    return 0 if m.group("hash") == current else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate NLM RAG-friendly .py.md wrapper for a Python source file.",
    )
    parser.add_argument("py_path", type=Path, help="Path to the .py file to wrap")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .md path (default: <py_path>.md alongside the source)",
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

    py_path: Path = args.py_path.resolve()
    if not py_path.exists():
        print(f"error: file not found: {py_path}", file=sys.stderr)
        return 2
    if py_path.suffix != ".py":
        print(f"error: expected a .py file: {py_path}", file=sys.stderr)
        return 2

    md_path: Path = (args.out.resolve() if args.out else py_path.with_suffix(".py.md"))

    if args.check:
        status = check_stale(py_path, md_path)
        label = {0: "fresh", 1: "stale", 2: "missing"}[status]
        print(f"{label}: {md_path}")
        return status

    current_sha = compute_sha256(py_path)
    if not args.force and check_stale(py_path, md_path) == 0:
        print(f"skip (fresh): {md_path}")
        return 0

    existing_summary = extract_existing_summary(md_path)
    parsed = parse_module(py_path)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    root = (args.root.resolve() if args.root else Path.cwd())
    try:
        source_path_rel = str(py_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        source_path_rel = str(py_path).replace("\\", "/")

    rendered = render_md(
        py_path=py_path,
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
