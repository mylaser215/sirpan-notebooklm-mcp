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

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


def _write_words(path: Path, n: int) -> Path:
    """Create a UTF-8 file with exactly ``n`` whitespace-delimited words."""
    path.write_text(" ".join(f"w{i}" for i in range(n)) + "\n", encoding="utf-8")
    return path

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


# ---------------------------------------------------------------------------
# --max-words chunking (1:N file-boundary split, opt-in)
# ---------------------------------------------------------------------------

def test_max_words_split_multipart(tmp_path: Path) -> None:
    """Three 10-word files, --max-words 15 → 3 parts, JSON manifest to stdout."""
    a = _write_words(tmp_path / "a.md", 10)
    b = _write_words(tmp_path / "b.md", 10)
    c = _write_words(tmp_path / "c.md", 10)
    out = tmp_path / "Chunk_Bundle.md"
    result = _run(
        "--files", str(a), str(b), str(c),
        "--output", str(out),
        "--bundle-name", "Chunk_Bundle",
        "--max-words", "15",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["split"] is True
    assert len(payload["parts"]) == 3
    # No un-suffixed single bundle when split; part files exist on disk.
    assert not out.exists()
    for i, p in enumerate(payload["parts"], start=1):
        pp = Path(p)
        assert pp.name == f"Chunk_Bundle_part{i}.md"
        assert pp.exists()


def test_max_words_single_part_backcompat(tmp_path: Path) -> None:
    """--max-words larger than total → 1 part reusing {stem}.md (no _part suffix)."""
    a = _write_words(tmp_path / "a.md", 10)
    b = _write_words(tmp_path / "b.md", 10)
    out = tmp_path / "Solo_Bundle.md"
    result = _run(
        "--files", str(a), str(b),
        "--output", str(out),
        "--bundle-name", "Solo_Bundle",
        "--max-words", "100000",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload["split"] is False
    assert len(payload["parts"]) == 1
    assert Path(payload["parts"][0]).name == "Solo_Bundle.md"
    assert out.exists()  # {stem}.md — byte-identical layout to legacy single mode


def test_max_words_file_boundary_no_mid_split(tmp_path: Path) -> None:
    """A file's content never straddles two parts (each H3 section is intact)."""
    a = _write_words(tmp_path / "a.md", 10)
    b = _write_words(tmp_path / "b.md", 10)
    c = _write_words(tmp_path / "c.md", 10)
    out = tmp_path / "Bnd_Bundle.md"
    result = _run(
        "--files", str(a), str(b), str(c),
        "--output", str(out),
        "--bundle-name", "Bnd_Bundle",
        "--max-words", "25",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    # 25 words: [a+b]=20 fits, +c=30 splits → part1=[a,b], part2=[c].
    assert len(payload["parts"]) == 2
    part1 = Path(payload["parts"][0]).read_text(encoding="utf-8")
    part2 = Path(payload["parts"][1]).read_text(encoding="utf-8")
    assert "### 파일: a.md" in part1 and "### 파일: b.md" in part1
    assert "### 파일: c.md" in part2
    # No file appears in more than one part.
    assert "### 파일: c.md" not in part1
    assert "### 파일: a.md" not in part2


def test_single_file_exceeds_max_words_own_part(tmp_path: Path) -> None:
    """A lone oversized file gets its own part + a stderr warning (no mid-file split)."""
    big = _write_words(tmp_path / "big.md", 30)
    small = _write_words(tmp_path / "small.md", 5)
    out = tmp_path / "Over_Bundle.md"
    result = _run(
        "--files", str(big), str(small),
        "--output", str(out),
        "--bundle-name", "Over_Bundle",
        "--max-words", "15",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert len(payload["parts"]) == 2
    assert "exceeds --max-words" in result.stderr


def test_no_max_words_preserves_legacy_wrote(tmp_path: Path) -> None:
    """Without --max-words: legacy single output + 'wrote:' stdout (no JSON)."""
    a = _write_words(tmp_path / "a.md", 10)
    out = tmp_path / "Legacy_Bundle.md"
    result = _run(
        "--files", str(a),
        "--output", str(out),
        "--bundle-name", "Legacy_Bundle",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("wrote:")
    assert out.exists()
