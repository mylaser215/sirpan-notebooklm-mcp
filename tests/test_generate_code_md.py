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


# ---------------------------------------------------------------------------
# JSON 구조추출 (.json 지원 — bundle followup B①)
# ---------------------------------------------------------------------------

def test_json_structure_extraction(tmp_path: Path) -> None:
    """object 루트: top-level 키 이름·타입·요약 + 원본 fence가 모두 나온다."""
    src = tmp_path / "sample.json"
    src.write_text(
        '{"name": "x", "version": 2, "enabled": true, "deps": ["a", "b"], "cfg": {"k": 1}}',
        encoding="utf-8",
    )
    out = tmp_path / "sample.json.md"
    result = _run(str(src), "--out", str(out), "--force")
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    assert "## 키 구조" in text
    # 키 이름
    assert "`name`" in text and "`deps`" in text and "`cfg`" in text
    # 타입 라벨
    assert "*string*" in text and "*array*" in text and "*object*" in text
    # boolean/null은 Python repr이 아닌 JSON 표기
    assert "boolean — true" in text
    assert "True" not in text.split("## 원본 코드")[0]  # 키 구조 섹션엔 Python True 없음
    # 원본 보존
    assert "```json" in text


def test_json_invalid_graceful(tmp_path: Path) -> None:
    """깨진 JSON도 exit 0 — 구조추출만 실패하고 원본은 보존된다."""
    src = tmp_path / "broken.json"
    src.write_text('{"a": 1,, }', encoding="utf-8")
    out = tmp_path / "broken.json.md"
    result = _run(str(src), "--out", str(out), "--force")
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    assert "파싱 실패" in text
    assert "```json" in text  # 원본은 그대로 살아있음


def test_json_root_array(tmp_path: Path) -> None:
    """비-object 루트(array)도 루트 타입·길이를 표기한다."""
    src = tmp_path / "arr.json"
    src.write_text("[1, 2, 3]", encoding="utf-8")
    out = tmp_path / "arr.json.md"
    result = _run(str(src), "--out", str(out), "--force")
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    assert "루트가 array" in text


def test_json_is_supported_extension(tmp_path: Path) -> None:
    """.json은 지원 확장자 — unsupported가 아니라 정상 dispatch(여기선 missing)."""
    src = tmp_path / "x.json"
    src.write_text("{}", encoding="utf-8")
    result = _run(str(src), "--check")  # 기본 out(x.json.md) 부재 → missing(2)
    assert result.returncode == 2
    assert "missing" in result.stdout
    assert "unsupported" not in result.stderr


# ---------------------------------------------------------------------------
# Kotlin 구조추출 (.kt 지원 — PARSERS OCP 확장)
# ---------------------------------------------------------------------------

_KT_SAMPLE = """\
package com.example

const val VERSION = 3
var counter = 0

data class User(val id: Int, val name: String)

sealed class Result

enum class Color { RED, GREEN, BLUE }

interface Repository {
    fun findAll(): List<User>
}

object Registry {
    val items = mutableListOf<String>()
}

fun greet(name: String): String = "hi $name"

typealias Handler = (Int) -> Unit
"""


def test_kotlin_symbol_extraction(tmp_path: Path) -> None:
    """top-level Kotlin 심볼(class/data class/sealed/enum/interface/object/fun/property/typealias)이
    각자 kind와 함께 추출되고, 원본은 kotlin fence로 보존된다."""
    src = tmp_path / "sample.kt"
    src.write_text(_KT_SAMPLE, encoding="utf-8")
    out = tmp_path / "sample.kt.md"
    result = _run(str(src), "--out", str(out), "--force")
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")

    assert "## 코드 구조" in text
    # 심볼 이름
    for name in ("User", "Result", "Color", "Repository", "Registry", "greet", "Handler", "VERSION", "counter"):
        assert f"`{name}`" in text, name
    # kind 라벨 — enum class는 class가 아닌 enum으로 잡혀야 한다 (dedup 우선순위)
    assert "*enum*" in text
    assert "*interface*" in text
    assert "*object*" in text
    assert "*fun*" in text
    assert "*property*" in text
    assert "*typealias*" in text
    # data class / sealed class는 class kind
    assert "*class*" in text
    # fence는 kotlin
    assert "```kotlin" in text


def test_kotlin_extension_function(tmp_path: Path) -> None:
    """확장 함수 `fun String.shout()`는 receiver를 벗기고 심볼명만 추출한다."""
    src = tmp_path / "ext.kt"
    src.write_text("fun String.shout(): String = this.uppercase()\n", encoding="utf-8")
    out = tmp_path / "ext.kt.md"
    result = _run(str(src), "--out", str(out), "--force")
    assert result.returncode == 0, result.stderr
    text = out.read_text(encoding="utf-8")
    assert "`shout`" in text
    assert "*fun*" in text


def test_kotlin_is_supported_extension(tmp_path: Path) -> None:
    """.kt는 지원 확장자 — unsupported가 아니라 정상 dispatch(여기선 missing)."""
    src = tmp_path / "x.kt"
    src.write_text("fun main() {}\n", encoding="utf-8")
    result = _run(str(src), "--check")  # 기본 out(x.kt.md) 부재 → missing(2)
    assert result.returncode == 2
    assert "missing" in result.stdout
    assert "unsupported" not in result.stderr
