"""Bundle N source files into a single NLM-friendly `[Domain]_Bundle.md`.

Sibling tool to `scripts/generate_code_md.py` (1:1 wrapper). This tool builds
the *N:1 bundling* artifact that lets the NLM-sync pipeline collapse low-volatility
Tier 2 files (utilities, completed past logs) into a single source, freeing
NLM Pro 300-source-per-notebook headroom for the volatile Tier 1 1:1 sources.

The bundle is a *read-only build artifact*: originals on disk are never
modified or deleted; the bundle is rendered into a temp dir and atomically
copied to the requested output path. Failures clean up the temp dir.

Bundle structure:
    frontmatter:
        bundle_name, bundled_files (absolute paths, sorted),
        generated_at, generator, bundle_sha256
    `> [!warning] Facade` callout: origin file list + "do not edit bundle" notice
    `### 파일: {basename}` H3 header per file (RAG chunk boundary signal)
    body: `.md` raw passthrough / `.py|.ts|.tsx|.json` fenced code block /
          other → unlabeled fence

Usage:
    uv run python scripts/generate_bundle_md.py \\
        --files <p1> <p2> ... \\
        --output <bundle_md_path> \\
        --bundle-name "<DomainName>_Bundle" \\
        [--root <project_root>]   # render bundled_files as paths relative to root

Exit codes: 0=ok, 1=input validation failure, 2=I/O error.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

GENERATOR_NAME = "scripts/generate_bundle_md.py"

# NLM Pro 소스당 한도 50만 단어의 ~40% — word 여유가 아니라 마크다운 파서
# timeout 방어가 목적 (세션62 RPC read timeout 계열). conv 803fdca1 ●●●.
DEFAULT_BUNDLE_MAX_WORDS = 200_000

FENCE_LANG: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
}


class BundleError(Exception):
    """Bundle generation failed (input validation or I/O)."""


def _validate_inputs(files: list[Path]) -> None:
    """Fail-close pre-check: every input must exist, be a regular file, and decode as UTF-8.

    All checks run *before* any write so a failure leaves the output untouched.
    """
    if not files:
        raise BundleError("no input files provided (--files required)")
    for f in files:
        if not f.exists():
            raise BundleError(f"missing input file: {f}")
        if not f.is_file():
            raise BundleError(f"not a regular file: {f}")
        try:
            f.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise BundleError(f"input is not valid UTF-8: {f}") from e


def _compute_bundle_sha256(files: list[Path]) -> str:
    """SHA256 over (sorted absolute path + per-file SHA256), for idempotency."""
    h = hashlib.sha256()
    for f in sorted(files, key=lambda p: str(p)):
        h.update(str(f).encode("utf-8"))
        h.update(b"\x00")
        h.update(hashlib.sha256(f.read_bytes()).hexdigest().encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def _render_body_for(file: Path) -> str:
    """Return the body fragment for one file (raw .md / fenced code / unlabeled fence)."""
    text = file.read_text(encoding="utf-8").rstrip("\n")
    ext = file.suffix.lower()
    if ext == ".md":
        return text + "\n"
    lang = FENCE_LANG.get(ext, "")
    return f"```{lang}\n{text}\n```\n"


def _display_path(f: Path, root: Path | None) -> str:
    """Render `f` relative to `root` when possible, else as absolute path.

    Posix slashes for cross-platform stability (Windows backslashes break byte
    fixtures and YAML).
    """
    if root is not None:
        try:
            return f.relative_to(root).as_posix()
        except ValueError:
            pass
    return f.as_posix()


def _render_bundle(
    files: list[Path], bundle_name: str, timestamp: str, root: Path | None
) -> str:
    """Compose the full bundle markdown (frontmatter + Facade callout + H3 sections)."""
    sorted_files = sorted(files, key=lambda p: str(p))
    bundle_sha = _compute_bundle_sha256(sorted_files)

    lines: list[str] = []
    # Frontmatter
    lines.append("---")
    lines.append(f"bundle_name: {bundle_name}")
    lines.append("bundled_files:")
    for f in sorted_files:
        lines.append(f"  - {_display_path(f, root)}")
    lines.append(f"generated_at: {timestamp}")
    lines.append(f"generator: {GENERATOR_NAME}")
    lines.append(f"bundle_sha256: {bundle_sha}")
    lines.append("---")
    lines.append("")

    # Facade callout — Tier 2 read-only artifact notice + origin paths
    lines.append("> [!warning] Facade — 읽기 전용 자동 산출물")
    lines.append(
        "> 본 소스는 다음 "
        f"{len(sorted_files)}개 파일의 통합본입니다. "
        "**수정은 개별 원본 파일을 이용하십시오.**"
    )
    for f in sorted_files:
        lines.append(f"> - `{_display_path(f, root)}`")
    lines.append(f"> 자동 동기화 도구: `{GENERATOR_NAME}`")
    lines.append("")

    # Per-file sections — H3 boundary is the RAG chunk signal
    for f in sorted_files:
        lines.append(f"### 파일: {f.name}")
        lines.append("")
        lines.append(_render_body_for(f).rstrip("\n"))
        lines.append("")

    return "\n".join(lines)


def _word_count(text: str) -> int:
    """Whitespace-delimited token count (한글 어절 근사)."""
    return len(text.split())


def _split_into_parts(files: list[Path], max_words: int) -> list[list[Path]]:
    """Greedy file-boundary bin-packing — a file is never split mid-content.

    Deterministic (sorted by path) so repeated runs converge (멱등, Cascade
    허용). A single file exceeding ``max_words`` gets its own part (the caller
    warns); no mid-file split.
    """
    parts: list[list[Path]] = []
    current: list[Path] = []
    current_words = 0
    for f in sorted(files, key=lambda p: str(p)):
        w = _word_count(f.read_text(encoding="utf-8"))
        if current and current_words + w > max_words:
            parts.append(current)
            current = []
            current_words = 0
        current.append(f)
        current_words += w
    if current:
        parts.append(current)
    return parts


def _atomic_write(output: Path, rendered: str) -> None:
    """Write ``rendered`` to ``output`` via a temp dir then atomic copy.

    On any failure the temp dir is removed and ``output`` is not touched.
    """
    with tempfile.TemporaryDirectory(prefix="nlm-bundle-") as tmpdir:
        tmp_path = Path(tmpdir) / output.name
        tmp_path.write_text(rendered, encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_path, output)


def generate_bundle(
    files: list[Path],
    output: Path,
    bundle_name: str,
    root: Path | None = None,
    max_words: int | None = None,
) -> list[Path]:
    """Build the bundle(s) and atomically write to ``output``.

    When ``max_words`` is ``None`` (default) a single ``output`` file is written
    (legacy behavior). When set, files are packed into parts at file boundaries:
    a single part reuses ``output`` (``{stem}.md`` — no ``_part`` suffix, so the
    single-bundle case is byte-identical to legacy); multiple parts become
    ``{stem}_part1{suffix}``, ``{stem}_part2{suffix}`` … next to ``output``.

    Returns the list of written output paths (length 1 when unsplit). On any
    failure nothing is written (fail-close: validation runs first).
    """
    _validate_inputs(files)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M")

    if max_words is None:
        _atomic_write(output, _render_bundle(files, bundle_name, timestamp, root))
        return [output]

    parts = _split_into_parts(files, max_words)
    if len(parts) == 1:
        out_paths = [output]
    else:
        out_paths = [
            output.with_name(f"{output.stem}_part{i + 1}{output.suffix}")
            for i in range(len(parts))
        ]

    for part_files, out_path in zip(parts, out_paths):
        # Oversize warning: a lone file that alone exceeds the threshold.
        if len(part_files) == 1 and _word_count(
            part_files[0].read_text(encoding="utf-8")
        ) > max_words:
            print(
                f"warning: '{part_files[0].name}' alone exceeds --max-words "
                f"({max_words}); emitted as its own part (no mid-file split).",
                file=sys.stderr,
            )
        _atomic_write(out_path, _render_bundle(part_files, bundle_name, timestamp, root))

    return out_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Bundle N source files into a single read-only NLM-friendly markdown "
            "([Domain]_Bundle.md). Sibling tool to generate_code_md.py."
        ),
    )
    parser.add_argument(
        "--files",
        type=Path,
        nargs="+",
        required=True,
        help="One or more source files to bundle (paths resolved to absolute)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination path for the bundle markdown",
    )
    parser.add_argument(
        "--bundle-name",
        type=str,
        required=True,
        help="Logical bundle name recorded in frontmatter (e.g. 'Utils_Bundle')",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help=(
            "Project root for relative bundled_files rendering (default: absolute paths)."
        ),
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=None,
        help=(
            "Split into parts at file boundaries when cumulative word count "
            f"exceeds this (opt-in; e.g. {DEFAULT_BUNDLE_MAX_WORDS}). When set, "
            "emits a JSON {parts, split} object to stdout instead of 'wrote:'."
        ),
    )
    args = parser.parse_args()

    try:
        files = [p.resolve() for p in args.files]
        root = args.root.resolve() if args.root else None
        outputs = generate_bundle(
            files,
            args.output.resolve(),
            args.bundle_name,
            root=root,
            max_words=args.max_words,
        )
    except BundleError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"I/O error: {e}", file=sys.stderr)
        return 2

    if args.max_words is not None:
        # Machine-readable contract for sync_bundle (1:N part discovery).
        print(json.dumps({"parts": [str(p) for p in outputs], "split": len(outputs) > 1}))
    else:
        print(f"wrote: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
