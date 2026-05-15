"""Regression tests for scripts/generate_code_md.py (세션44 통합).

Pins down equivalence with the legacy generate_py_md.py / generate_ts_md.py
outputs via fixture comparison (timestamp / generator lines masked), plus
unit coverage for `--check`, `--force`, summary idempotency, and unsupported
extension handling.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJ_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJ_ROOT / "scripts" / "generate_code_md.py"
FIXTURE_DIR = PROJ_ROOT / "tests" / "fixtures" / "generate_code_md"

# Lines we must mask before byte-comparing wrapper outputs across runs.
MASK_PATTERNS = [
    re.compile(r"^generated_at:.*$", re.MULTILINE),
    re.compile(r"^generator:.*$", re.MULTILINE),
]


def _normalize(text: str) -> str:
    """Strip volatile frontmatter lines that differ between tools/runs."""
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
# Equivalence vs. legacy fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "sample,expected",
    [
        ("sample_python.py", "expected_python.py.md"),
        ("sample_typescript.ts", "expected_typescript.ts.md"),
        ("sample_tsx.tsx", "expected_tsx.tsx.md"),
    ],
)
def test_output_equivalence(tmp_path: Path, sample: str, expected: str) -> None:
    """New tool must produce byte-equal output to the legacy tools (after masking)."""
    src = FIXTURE_DIR / sample
    out = tmp_path / (sample + ".md")
    result = _run(str(src), "--out", str(out), "--force", "--root", str(FIXTURE_DIR))
    assert result.returncode == 0, result.stderr
    assert out.exists()

    actual = _normalize(out.read_text(encoding="utf-8"))
    fixture = _normalize((FIXTURE_DIR / expected).read_text(encoding="utf-8"))
    assert actual == fixture, "Wrapper output drifted from legacy fixture"


# ---------------------------------------------------------------------------
# --check (stale detection)
# ---------------------------------------------------------------------------

def test_check_missing(tmp_path: Path) -> None:
    src = FIXTURE_DIR / "sample_python.py"
    out = tmp_path / "nonexistent.py.md"
    result = _run(str(src), "--out", str(out), "--check")
    assert result.returncode == 2
    assert "missing" in result.stdout


def test_check_fresh(tmp_path: Path) -> None:
    src = FIXTURE_DIR / "sample_python.py"
    out = tmp_path / "fresh.py.md"
    assert _run(str(src), "--out", str(out), "--force").returncode == 0
    result = _run(str(src), "--out", str(out), "--check")
    assert result.returncode == 0
    assert "fresh" in result.stdout


def test_check_stale(tmp_path: Path) -> None:
    # Render once against the original source, then mutate the source so the
    # cached SHA256 no longer matches.
    src = tmp_path / "mutating.py"
    src.write_text("def a():\n    return 1\n", encoding="utf-8")
    out = tmp_path / "mutating.py.md"
    assert _run(str(src), "--out", str(out), "--force").returncode == 0
    src.write_text("def a():\n    return 2\n", encoding="utf-8")
    result = _run(str(src), "--out", str(out), "--check")
    assert result.returncode == 1
    assert "stale" in result.stdout


# ---------------------------------------------------------------------------
# --force / fresh-skip
# ---------------------------------------------------------------------------

def test_skip_when_fresh(tmp_path: Path) -> None:
    src = FIXTURE_DIR / "sample_python.py"
    out = tmp_path / "skip.py.md"
    assert _run(str(src), "--out", str(out), "--force").returncode == 0
    first_mtime = out.stat().st_mtime_ns
    # Second invocation without --force should report "skip (fresh)" and leave
    # the file untouched.
    result = _run(str(src), "--out", str(out))
    assert result.returncode == 0
    assert "skip" in result.stdout
    assert out.stat().st_mtime_ns == first_mtime


def test_force_regenerates(tmp_path: Path) -> None:
    src = FIXTURE_DIR / "sample_python.py"
    out = tmp_path / "force.py.md"
    assert _run(str(src), "--out", str(out), "--force").returncode == 0
    # Tamper with the wrapper, then re-run with --force; the wrapper should be
    # rebuilt from source (TAMPERED marker disappears).
    tampered = out.read_text(encoding="utf-8") + "\n<!-- TAMPERED -->\n"
    out.write_text(tampered, encoding="utf-8")
    assert _run(str(src), "--out", str(out), "--force").returncode == 0
    assert "TAMPERED" not in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Summary idempotency
# ---------------------------------------------------------------------------

def test_summary_idempotent(tmp_path: Path) -> None:
    src = FIXTURE_DIR / "sample_python.py"
    out = tmp_path / "idempotent.py.md"
    assert _run(str(src), "--out", str(out), "--force").returncode == 0

    # Replace the placeholder with a real summary.
    text = out.read_text(encoding="utf-8")
    custom = "이 모듈은 회귀 테스트 fixture 용도임. 멱등성 검증."
    new_text = re.sub(
        r"(## 아키텍처 요약\n\n).*?(\n\n## )",
        rf"\1{custom}\2",
        text,
        count=1,
        flags=re.DOTALL,
    )
    out.write_text(new_text, encoding="utf-8")

    # Regenerate with --force; the custom summary must survive.
    assert _run(str(src), "--out", str(out), "--force").returncode == 0
    final = out.read_text(encoding="utf-8")
    assert custom in final
    assert "(TODO:" not in final


# ---------------------------------------------------------------------------
# Unsupported extension
# ---------------------------------------------------------------------------

def test_unsupported_extension(tmp_path: Path) -> None:
    src = tmp_path / "hello.rs"
    src.write_text("fn main() {}\n", encoding="utf-8")
    result = _run(str(src))
    assert result.returncode == 2
    assert "unsupported extension" in result.stderr
