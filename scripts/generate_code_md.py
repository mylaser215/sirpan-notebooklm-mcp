"""Generate NLM RAG-friendly `<basename>.{py,ts,tsx,kt,json}.md` wrappers from source files.

Unified successor to `generate_py_md.py` (세션35) + `generate_ts_md.py` (세션39).
Dispatch is driven by file extension via the `PARSERS` registry at the bottom
of this module — adding a new language is an O(1) edit (register a parser +
renderer pair).

Three H2 sections in every output:
    ## 아키텍처 요약   — manual summary (idempotently preserved across re-runs)
    ## 함수별 역할      — Python AST extraction (H3 nested methods)
       또는
    ## 코드 구조        — TypeScript regex extraction (flat symbols)
    ## 원본 코드        — full source body in a fenced block

Frontmatter records `source_path`, `generated_at`, `original_sha256`, and
`generator` so stale detection is content-based (immune to mtime / git-stash
false positives).

세션44 통합 (단교차삼단시공, NLM 자문 conv 803fdca1, ●●● B안):
    - 단일 진입점 + 확장자 자동 분기 (lang 인자 없음 → UX 극대화)
    - 60% 중복 로직 제거, 공통 코어 1회 정의
    - `PARSERS` dict로 OCP 강제 → rust/go 추가 시 함수 2개만 추가 (O(1))

Usage:
    uv run python scripts/generate_code_md.py <path>
    uv run python scripts/generate_code_md.py <path> --out <md_path>
    uv run python scripts/generate_code_md.py <path> --force
    uv run python scripts/generate_code_md.py <path> --check    # 0=fresh, 1=stale, 2=missing
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

GENERATOR_NAME = "scripts/generate_code_md.py"

SUMMARY_PLACEHOLDER = (
    "(TODO: 사용자 정성 작성 — 본 모듈의 책임 / 핵심 설계 패턴 / 의존 관계를 3-5단락으로 요약. "
    "재생성 시 본 섹션은 *그대로 보존됨* — 멱등성)"
)

SUMMARY_BLOCK_RE = re.compile(
    r"^## 아키텍처 요약\s*\n(?P<body>.*?)(?=^## |\Z)",
    re.DOTALL | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# 공통 유틸 (양 언어 공유)
# ---------------------------------------------------------------------------

def compute_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_existing_summary(md_path: Path) -> str | None:
    """Return the body of `## 아키텍처 요약` if present (idempotency).

    Returns None when the section is absent or matches the placeholder marker
    (so the marker doesn't propagate indefinitely).
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


def check_stale(src_path: Path, md_path: Path) -> int:
    """Return 0 (fresh), 1 (stale), 2 (missing md)."""
    if not md_path.exists():
        return 2
    current = compute_sha256(src_path)
    md_text = md_path.read_text(encoding="utf-8")
    m = re.search(r"^original_sha256:\s*(?P<hash>[0-9a-f]+)\s*$", md_text, re.MULTILINE)
    if not m:
        return 1
    return 0 if m.group("hash") == current else 1


def _default_md_path(src_path: Path) -> Path:
    """Compute `<basename><ext>.md` sibling path, preserving original extension.

    `Path.with_suffix` only replaces the final suffix, so we splice the output
    name manually so that `foo.py` → `foo.py.md` and `foo.tsx` → `foo.tsx.md`.
    """
    return src_path.with_name(src_path.name + ".md")


# ---------------------------------------------------------------------------
# Python: AST 기반 추출 + H3 nested methods 렌더링
# ---------------------------------------------------------------------------

def _py_first_line(docstring: str | None) -> str:
    if not docstring:
        return ""
    for line in docstring.splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def _py_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
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


def _parse_py(path: Path) -> dict:
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
                            "signature": _py_signature(sub),
                            "doc": _py_first_line(ast.get_docstring(sub)),
                            "lineno": sub.lineno,
                        }
                    )
            items.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "signature": f"class {node.name}",
                    "doc": _py_first_line(class_doc),
                    "lineno": node.lineno,
                    "methods": methods,
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            items.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "signature": _py_signature(node),
                    "doc": _py_first_line(ast.get_docstring(node)),
                    "lineno": node.lineno,
                }
            )

    return {"module_doc": module_doc, "items": items, "source": source}


def _render_py(parsed: dict) -> list[str]:
    """Render the language-specific middle section + source fence for Python."""
    lines: list[str] = []
    lines.append("## 함수별 역할")
    lines.append("")
    module_doc = parsed["module_doc"]
    if module_doc:
        first = _py_first_line(module_doc)
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

    # 원본 코드
    lines.append("## 원본 코드")
    lines.append("")
    lines.append("```python")
    lines.append(parsed["source"].rstrip("\n"))
    lines.append("```")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# TypeScript: regex 기반 추출 + flat 심볼 렌더링
# ---------------------------------------------------------------------------

# Top-level symbol extractors. Each pattern captures the symbol name in group 1
# and matches at column 0 (no indentation) to avoid catching nested helpers.
TS_SYMBOL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("function", re.compile(r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)\s*[<(]", re.MULTILINE)),
    # arrow: variable type annotation may span lines; RHS may start with a generic param list.
    ("arrow", re.compile(r"^(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+(\w+)\s*(?::[^=]+?)?=\s*(?:async\s+)?(?:<[^>]*>\s*)?(?:\([^)]*\)|\w+)\s*(?::[^=\n]+)?\s*=>", re.MULTILINE)),
    ("class", re.compile(r"^(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE)),
    ("interface", re.compile(r"^(?:export\s+)?interface\s+(\w+)", re.MULTILINE)),
    ("type", re.compile(r"^(?:export\s+)?type\s+(\w+)\s*[<=]", re.MULTILINE)),
    ("enum", re.compile(r"^(?:export\s+)?(?:declare\s+)?(?:const\s+)?enum\s+(\w+)", re.MULTILINE)),
]


def _ts_line_of(source: str, offset: int) -> int:
    """Return 1-indexed line number for a character offset in source."""
    return source.count("\n", 0, offset) + 1


def _ts_signature_line(source: str, offset: int) -> str:
    """Return the source line at offset (no trailing newline)."""
    start = source.rfind("\n", 0, offset) + 1
    end = source.find("\n", offset)
    if end == -1:
        end = len(source)
    return source[start:end].rstrip()


def _parse_flat(path: Path, patterns: list[tuple[str, re.Pattern[str]]]) -> dict:
    """Extract top-level symbols via a regex pattern registry (TS/Kotlin share this).

    Each pattern captures the symbol name in group 1 at column 0. Results are
    deduped by (name, line) — patterns earlier in the list win a collision, so
    order the more-specific pattern (e.g. `enum class`) before the general one
    (`class`) to keep its kind label.
    """
    source = path.read_text(encoding="utf-8")
    items: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for kind, pattern in patterns:
        for m in pattern.finditer(source):
            name = m.group(1)
            line = _ts_line_of(source, m.start())
            key = (name, line)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                {
                    "kind": kind,
                    "name": name,
                    "signature": _ts_signature_line(source, m.start()),
                    "lineno": line,
                }
            )
    items.sort(key=lambda x: (x["lineno"], x["name"]))
    return {"items": items, "source": source}


def _render_flat(parsed: dict, fence: str) -> list[str]:
    """Render the `## 코드 구조` flat-symbol section + source fence (TS/Kotlin share).

    `fence` is the code-fence language tag (e.g. "typescript", "kotlin").
    """
    lines: list[str] = []
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
            lines.append(f"```{fence}\n{sig}\n```")
            lines.append("")

    # 원본 코드
    lines.append("## 원본 코드")
    lines.append("")
    lines.append(f"```{fence}")
    lines.append(parsed["source"].rstrip("\n"))
    lines.append("```")
    lines.append("")
    return lines


def _parse_ts(path: Path) -> dict:
    """Extract top-level TypeScript symbols via regex."""
    return _parse_flat(path, TS_SYMBOL_PATTERNS)


def _render_ts(parsed: dict) -> list[str]:
    """Render the language-specific middle section + source fence for TypeScript."""
    return _render_flat(parsed, "typescript")


# ---------------------------------------------------------------------------
# Kotlin: regex 기반 추출 (TS와 _parse_flat/_render_flat 공유) + flat 심볼 렌더링
# ---------------------------------------------------------------------------

# Shared modifier/annotation prefix that may precede a top-level declaration.
# Matches at column 0; annotations (`@Foo`, `@Foo(...)`) and soft keywords are
# all optional so the following declaration keyword is what actually anchors.
_KT_MODS = (
    r"(?:@[\w.]+(?:\([^)]*\))?\s+)*"  # annotations
    r"(?:(?:public|private|internal|protected|open|final|abstract|sealed|data|"
    r"inner|inline|value|external|expect|actual|const|lateinit|override|"
    r"operator|infix|suspend|tailrec|annotation|companion|vararg)\s+)*"
)

# Top-level Kotlin symbol extractors. `enum` precedes `class` so `enum class Foo`
# keeps its enum kind under (name, line) dedup in _parse_flat.
KT_SYMBOL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("enum", re.compile(r"^" + _KT_MODS + r"enum\s+class\s+(\w+)", re.MULTILINE)),
    ("class", re.compile(r"^" + _KT_MODS + r"class\s+(\w+)", re.MULTILINE)),
    ("object", re.compile(r"^" + _KT_MODS + r"object\s+(\w+)", re.MULTILINE)),
    ("interface", re.compile(r"^" + _KT_MODS + r"(?:fun\s+)?interface\s+(\w+)", re.MULTILINE)),
    # fun: optional generics + optional receiver (`String.` in extension funcs).
    ("fun", re.compile(r"^" + _KT_MODS + r"fun\s+(?:<[^>]*>\s*)?(?:\w+(?:<[^>]*>)?\.)?(\w+)\s*[(<]", re.MULTILINE)),
    ("property", re.compile(r"^" + _KT_MODS + r"(?:val|var)\s+(?:<[^>]*>\s*)?(?:\w+(?:<[^>]*>)?\.)?(\w+)\b", re.MULTILINE)),
    ("typealias", re.compile(r"^" + _KT_MODS + r"typealias\s+(\w+)", re.MULTILINE)),
]


def _parse_kt(path: Path) -> dict:
    """Extract top-level Kotlin symbols via regex."""
    return _parse_flat(path, KT_SYMBOL_PATTERNS)


def _render_kt(parsed: dict) -> list[str]:
    """Render the language-specific middle section + source fence for Kotlin."""
    return _render_flat(parsed, "kotlin")


# ---------------------------------------------------------------------------
# JSON: 키 구조 추출 (top-level keys + 값 타입/요약) + 원본 fence
# ---------------------------------------------------------------------------

def _json_type(value: object) -> str:
    """Map a parsed JSON value to its type label (bool before int — bool ⊂ int)."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _json_value_summary(value: object) -> str:
    """One-line summary of a JSON value for the 키 구조 section."""
    t = _json_type(value)
    if t == "object":
        assert isinstance(value, dict)
        keys = list(value.keys())
        if not keys:
            return "object — (빈 object)"
        preview = ", ".join(f"`{k}`" for k in keys[:8])
        more = f" … (+{len(keys) - 8})" if len(keys) > 8 else ""
        return f"object — {len(keys)} keys: {preview}{more}"
    if t == "array":
        assert isinstance(value, list)
        if not value:
            return "array — (빈 배열)"
        elem_types = ", ".join(sorted({_json_type(v) for v in value}))
        return f"array — {len(value)} items ({elem_types})"
    if t == "string":
        assert isinstance(value, str)
        s = value.replace("\n", " ")
        return f'string — "{s[:60]}{"…" if len(s) > 60 else ""}"'
    if t == "boolean":
        return f"boolean — {'true' if value else 'false'}"  # JSON 표기 (not Python True/False)
    if t == "null":
        return "null"
    if t == "number":
        return f"number — {value!r}"
    return ""


def _parse_json(path: Path) -> dict:
    """Extract top-level JSON key structure. Invalid JSON degrades gracefully
    (raw source is still preserved in the wrapper so NLM keeps the content)."""
    source = path.read_text(encoding="utf-8")
    try:
        data = json.loads(source)
        error: str | None = None
    except json.JSONDecodeError as e:
        data = None
        error = str(e)

    items: list[dict] = []
    if isinstance(data, dict):
        for key, value in data.items():
            items.append(
                {
                    "name": key,
                    "type": _json_type(value),
                    "summary": _json_value_summary(value),
                }
            )

    root_type = _json_type(data) if error is None else None
    root_len = len(data) if isinstance(data, (dict, list)) else None
    return {
        "items": items,
        "root_type": root_type,
        "root_len": root_len,
        "error": error,
        "source": source,
    }


def _render_json(parsed: dict) -> list[str]:
    """Render the JSON key-structure section + source fence."""
    lines: list[str] = []
    lines.append("## 키 구조")
    lines.append("")

    error = parsed.get("error")
    if error:
        lines.append(f"*(JSON 파싱 실패: {error} — 원본 코드만 보존)*")
        lines.append("")
    elif parsed["root_type"] == "object":
        items = parsed["items"]
        if not items:
            lines.append("*(빈 object)*")
            lines.append("")
        for item in items:
            lines.append(f"### `{item['name']}` (*{item['type']}*)")
            lines.append("")
            if item["summary"]:
                lines.append(item["summary"])
                lines.append("")
    else:
        root_len = parsed.get("root_len")
        suffix = f": {root_len} 요소" if root_len is not None else ""
        lines.append(f"*(루트가 {parsed['root_type']}{suffix})*")
        lines.append("")

    # 원본 코드
    lines.append("## 원본 코드")
    lines.append("")
    lines.append("```json")
    lines.append(parsed["source"].rstrip("\n"))
    lines.append("```")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Dispatch registry (OCP — adding a language = registering one pair)
# ---------------------------------------------------------------------------

Parser = Callable[[Path], dict]
Renderer = Callable[[dict], list[str]]

PARSERS: dict[str, tuple[Parser, Renderer]] = {
    ".py": (_parse_py, _render_py),
    ".ts": (_parse_ts, _render_ts),
    ".tsx": (_parse_ts, _render_ts),
    ".kt": (_parse_kt, _render_kt),
    ".json": (_parse_json, _render_json),
}

SUPPORTED_EXTS: set[str] = set(PARSERS.keys())


# ---------------------------------------------------------------------------
# Composite render (frontmatter + summary + language section)
# ---------------------------------------------------------------------------

def render_md(
    src_path: Path,
    parsed: dict,
    body_lines: list[str],
    sha256: str,
    existing_summary: str | None,
    timestamp: str,
    source_path_rel: str,
) -> str:
    lines: list[str] = []
    lines.append("---")
    lines.append(f"source_path: {source_path_rel}")
    lines.append(f"generated_at: {timestamp}")
    lines.append(f"original_sha256: {sha256}")
    lines.append(f"generator: {GENERATOR_NAME}")
    lines.append("---")
    lines.append("")

    lines.append("## 아키텍처 요약")
    lines.append("")
    lines.append(existing_summary if existing_summary else SUMMARY_PLACEHOLDER)
    lines.append("")

    lines.extend(body_lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate NLM RAG-friendly <basename>.{py,ts,tsx,kt,json}.md wrapper for a "
            "source file. Dispatch is automatic by file extension."
        ),
    )
    parser.add_argument("path", type=Path, help="Path to the source file to wrap")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output .md path (default: <basename><ext>.md alongside the source)",
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

    src_path: Path = args.path.resolve()
    if not src_path.exists():
        print(f"error: file not found: {src_path}", file=sys.stderr)
        return 2

    ext = src_path.suffix
    if ext not in SUPPORTED_EXTS:
        supported = ", ".join(sorted(SUPPORTED_EXTS))
        print(
            f"error: unsupported extension '{ext}' (supported: {supported}): {src_path}",
            file=sys.stderr,
        )
        return 2

    parse_fn, render_fn = PARSERS[ext]
    md_path: Path = args.out.resolve() if args.out else _default_md_path(src_path)

    if args.check:
        status = check_stale(src_path, md_path)
        label = {0: "fresh", 1: "stale", 2: "missing"}[status]
        print(f"{label}: {md_path}")
        return status

    current_sha = compute_sha256(src_path)
    if not args.force and check_stale(src_path, md_path) == 0:
        print(f"skip (fresh): {md_path}")
        return 0

    existing_summary = extract_existing_summary(md_path)
    parsed = parse_fn(src_path)
    body_lines = render_fn(parsed)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    root = args.root.resolve() if args.root else Path.cwd()
    try:
        source_path_rel = str(src_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        source_path_rel = str(src_path).replace("\\", "/")

    rendered = render_md(
        src_path=src_path,
        parsed=parsed,
        body_lines=body_lines,
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
