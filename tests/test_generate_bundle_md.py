"""Regression tests for scripts/generate_bundle_md.py (Batch 1 ATOM-2).

Patterned after test_generate_code_md.py: subprocess CLI invocation +
normalized byte comparison vs a frozen fixture (volatile lines masked).

Covers:
    - Output equivalence (full bundle byte-equal to expected fixture)
    - Fail-close: missing file, non-UTF-8, empty --files
    - --root relative path rendering
    - Default absolute path rendering (no --root)
    - bundle_sha256 stability across runs (idempotency)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJ_ROOT / "scripts" / "generate_bundle_md.py"
FIXTURE_DIR = PROJ_ROOT / "tests" / "fixtures" / "generate_bundle_md"
SAMPLE1_INPUT = FIXTURE_DIR / "sample1_input"

MASK_PATTERNS = [
    re.compile(r"^generated_at:.*$", re.MULTILINE),
]


def _normalize(text: str) -> str:
    """Mask volatile frontmatter so byte comparison ignores wall-clock time."""
    for pat in MASK_PATTERNS:
        text = pat.sub("<MASKED>", text)
    return text.replace("\r\n", "\n")


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Equivalence vs frozen fixture
# ---------------------------------------------------------------------------

def test_output_equivalence_sample1(tmp_path: Path) -> None:
    """Full bundle output (with --root) must byte-equal expected fixture."""
    out = tmp_path / "Sample1_Bundle.md"
    result = _run(
        "--files",
        str(SAMPLE1_INPUT / "mini_util_a.md"),
        str(SAMPLE1_INPUT / "mini_util_b.py"),
        str(SAMPLE1_INPUT / "mini_util_c.json"),
        "--output",
        str(out),
        "--bundle-name",
        "Sample1_Bundle",
        "--root",
        str(SAMPLE1_INPUT),
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()

    actual = _normalize(out.read_text(encoding="utf-8"))
    expected = _normalize((FIXTURE_DIR / "expected_sample1_Bundle.md").read_text(encoding="utf-8"))
    assert actual == expected, "bundle output drifted from frozen fixture"


# ---------------------------------------------------------------------------
# Fail-close: input validation
# ---------------------------------------------------------------------------

def test_fail_close_missing_file(tmp_path: Path) -> None:
    """Missing input file → exit 1, no output written, no temp leftovers."""
    out = tmp_path / "out.md"
    result = _run(
        "--files",
        str(SAMPLE1_INPUT / "mini_util_a.md"),
        str(tmp_path / "does_not_exist.md"),
        "--output",
        str(out),
        "--bundle-name",
        "Broken_Bundle",
    )
    assert result.returncode == 1
    assert "missing" in result.stderr.lower()
    assert not out.exists()


def test_fail_close_non_utf8(tmp_path: Path) -> None:
    """Non-UTF-8 input → exit 1 (UnicodeDecodeError surfaced before write)."""
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xff\xfe\xfa\x00\x01binary")
    out = tmp_path / "out.md"
    result = _run(
        "--files",
        str(bad),
        "--output",
        str(out),
        "--bundle-name",
        "Broken_Bundle",
    )
    assert result.returncode == 1
    assert "utf-8" in result.stderr.lower()
    assert not out.exists()


# ---------------------------------------------------------------------------
# Path rendering modes
# ---------------------------------------------------------------------------

def test_absolute_paths_without_root(tmp_path: Path) -> None:
    """Without --root, bundled_files entries are absolute (posix slashes)."""
    out = tmp_path / "abs.md"
    result = _run(
        "--files",
        str(SAMPLE1_INPUT / "mini_util_a.md"),
        "--output",
        str(out),
        "--bundle-name",
        "Abs_Bundle",
    )
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    # Absolute path always contains a colon on Windows (C:) or starts with / on POSIX.
    expected_abs = (SAMPLE1_INPUT / "mini_util_a.md").resolve().as_posix()
    assert f"  - {expected_abs}" in text


# ---------------------------------------------------------------------------
# bundle_sha256 stability (idempotency)
# ---------------------------------------------------------------------------

def test_bundle_sha256_stable_across_runs(tmp_path: Path) -> None:
    """Same inputs → identical bundle_sha256 even across separate invocations."""
    out1 = tmp_path / "first.md"
    out2 = tmp_path / "second.md"
    for out in (out1, out2):
        result = _run(
            "--files",
            str(SAMPLE1_INPUT / "mini_util_a.md"),
            str(SAMPLE1_INPUT / "mini_util_b.py"),
            "--output",
            str(out),
            "--bundle-name",
            "Stable_Bundle",
            "--root",
            str(SAMPLE1_INPUT),
        )
        assert result.returncode == 0, result.stderr

    def _extract_sha(text: str) -> str:
        m = re.search(r"^bundle_sha256:\s*([0-9a-f]+)\s*$", text, re.MULTILINE)
        assert m, "bundle_sha256 not found in output"
        return m.group(1)

    sha1 = _extract_sha(out1.read_text(encoding="utf-8"))
    sha2 = _extract_sha(out2.read_text(encoding="utf-8"))
    assert sha1 == sha2, "bundle_sha256 must be deterministic for the same inputs"


# ---------------------------------------------------------------------------
# Missing --files
# ---------------------------------------------------------------------------

def test_argparse_requires_files(tmp_path: Path) -> None:
    """No --files → argparse returns non-zero (usage error)."""
    out = tmp_path / "out.md"
    result = _run("--output", str(out), "--bundle-name", "Empty")
    assert result.returncode != 0
