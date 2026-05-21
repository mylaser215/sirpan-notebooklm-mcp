"""sync_helpers detect_drift + format_drift_summary 회귀 가드.

ATOM-2 (세션44, 260521) — `detect_drift`를 MCP tool로 노출하기 전에 신설.
함수 본체는 NLM동기화 ⑥단계에서 매일 호출되지만 유닛 가드가 부재했음.

본 테스트가 깨지면 NLM동기화 ⑥단계가 침묵 회귀 — drift 잔재 누적
(세션342 NLM Pro 한도 incident 재발 위험).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from notebooklm_tools.services.sync_helpers import (
    detect_drift,
    format_drift_summary,
)


@pytest.fixture
def vault_with_files(tmp_path: Path) -> Path:
    """Build a minimal vault: priority folders + a few representative files."""
    (tmp_path / "000-시스템" / "050-Docs").mkdir(parents=True)
    (tmp_path / "000-시스템" / "070-세션로그").mkdir(parents=True)
    (tmp_path / "300-작업중").mkdir()
    (tmp_path / "500-지식정원").mkdir()
    (tmp_path / "000-시스템" / "050-Docs" / "guide.md").write_text("g", encoding="utf-8")
    (tmp_path / "500-지식정원" / "essay.md").write_text("e", encoding="utf-8")
    # Ambiguous: same filename in two non-priority dirs so _narrow_by_priority
    # cannot tie-break and yields the original 2-candidate list.
    (tmp_path / "outer_a").mkdir()
    (tmp_path / "outer_b").mkdir()
    (tmp_path / "outer_a" / "dup.md").write_text("a", encoding="utf-8")
    (tmp_path / "outer_b" / "dup.md").write_text("b", encoding="utf-8")
    return tmp_path


def _make_fetcher(sources: list[dict[str, Any]]):
    """Return a sources_fetcher callable that ignores the notebook_id arg."""
    def fetcher(notebook_id: str) -> list[dict[str, Any]]:
        return sources
    return fetcher


def test_detect_drift_matched_single(vault_with_files: Path) -> None:
    """One source title with a unique disk file → matched."""
    fetcher = _make_fetcher([
        {"id": "s1", "title": "guide.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    assert report["total"] == 1
    assert len(report["matched"]) == 1
    assert len(report["missing"]) == 0
    assert len(report["ambiguous"]) == 0
    assert report["matched"][0]["status"] == "matched"
    assert report["matched"][0]["source_id"] == "s1"
    assert report["matched"][0]["markdown_relevant"] is True


def test_detect_drift_missing(vault_with_files: Path) -> None:
    """Title with no disk file → missing (NLM 잔재)."""
    fetcher = _make_fetcher([
        {"id": "ghost", "title": "vanished.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    assert report["total"] == 1
    assert len(report["matched"]) == 0
    assert len(report["missing"]) == 1
    assert report["missing"][0]["source_id"] == "ghost"
    assert report["missing"][0]["disk_path"] is None


def test_detect_drift_ambiguous(vault_with_files: Path) -> None:
    """Title matching multiple non-priority files → ambiguous."""
    fetcher = _make_fetcher([
        {"id": "dup", "title": "dup.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    assert len(report["ambiguous"]) == 1
    entry = report["ambiguous"][0]
    assert entry["status"] == "ambiguous"
    assert len(entry["candidates"]) >= 2


def test_detect_drift_skip_type(vault_with_files: Path) -> None:
    """Non-relevant source types (e.g., url, note) classified as skip_type."""
    fetcher = _make_fetcher([
        {"id": "u1", "title": "https://example.com", "source_type_name": "url"},
        {"id": "n1", "title": "Inline note", "source_type_name": "note"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    assert report["total"] == 2
    assert len(report["matched"]) == 0
    assert len(report["missing"]) == 0
    assert len(report["skip_type"]) == 2
    assert {e["source_id"] for e in report["skip_type"]} == {"u1", "n1"}


def test_detect_drift_markdown_split(vault_with_files: Path) -> None:
    """matched_markdown vs matched_non_markdown split (v4 정책)."""
    (vault_with_files / "000-시스템" / "050-Docs" / "script.py").write_text(
        "x", encoding="utf-8"
    )
    fetcher = _make_fetcher([
        {"id": "md", "title": "guide.md", "source_type_name": "generated_text"},
        {"id": "py", "title": "script.py", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    assert len(report["matched"]) == 2
    assert len(report["matched_markdown"]) == 1
    assert len(report["matched_non_markdown"]) == 1
    assert report["matched_markdown"][0]["source_id"] == "md"
    assert report["matched_non_markdown"][0]["source_id"] == "py"


def test_format_drift_summary_clean(vault_with_files: Path) -> None:
    """All matched → no warning suffix."""
    fetcher = _make_fetcher([
        {"id": "s1", "title": "guide.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)
    summary = format_drift_summary(report)

    assert "drift 점검" in summary
    assert "청소·매핑 보강 권고" not in summary
    assert "NLM 잔재" not in summary or "0 NLM 잔재" in summary


def test_format_drift_summary_with_issues(vault_with_files: Path) -> None:
    """Missing/ambiguous present → warning + detail list."""
    fetcher = _make_fetcher([
        {"id": "ghost", "title": "vanished.md", "source_type_name": "generated_text"},
        {"id": "dup", "title": "dup.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)
    summary = format_drift_summary(report)

    assert "청소·매핑 보강 권고" in summary
    assert "NLM 잔재" in summary
    assert "모호" in summary
    assert "vanished.md" in summary
    assert "dup.md" in summary


def test_detect_drift_vault_root_override(tmp_path: Path) -> None:
    """Explicit vault_root overrides env/default."""
    (tmp_path / "alt.md").write_text("x", encoding="utf-8")
    fetcher = _make_fetcher([
        {"id": "alt", "title": "alt.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=tmp_path)
    assert len(report["matched"]) == 1
    assert report["matched"][0]["disk_path"] == str(tmp_path / "alt.md")


def test_mcp_detect_drift_smoke(monkeypatch, vault_with_files: Path) -> None:
    """MCP wrapper `detect_drift(notebook_id, vault_root)` returns
    {status, report, summary} structure."""
    from notebooklm_tools.mcp.tools import notebooks as nb_tools

    class StubClient:
        def get_notebook_sources_with_types(self, notebook_id: str):
            return [
                {"id": "s1", "title": "guide.md", "source_type_name": "generated_text"},
            ]

    monkeypatch.setattr(nb_tools, "get_client", lambda: StubClient())

    result = nb_tools.detect_drift(
        notebook_id="nb1", vault_root=str(vault_with_files)
    )

    assert result["status"] == "success"
    assert "report" in result
    assert "summary" in result
    assert result["report"]["total"] == 1
    assert len(result["report"]["matched"]) == 1
    assert "drift 점검" in result["summary"]


def test_mcp_detect_drift_vault_root_none_uses_env(
    monkeypatch, vault_with_files: Path
) -> None:
    """vault_root=None → defers to SIRPAN_VAULT env (NLM Q3 ●● 권고)."""
    from notebooklm_tools.mcp.tools import notebooks as nb_tools

    class StubClient:
        def get_notebook_sources_with_types(self, notebook_id: str):
            return [
                {"id": "s1", "title": "guide.md", "source_type_name": "generated_text"},
            ]

    monkeypatch.setattr(nb_tools, "get_client", lambda: StubClient())
    monkeypatch.setenv("SIRPAN_VAULT", str(vault_with_files))

    result = nb_tools.detect_drift(notebook_id="nb1")

    assert result["status"] == "success"
    assert result["report"]["total"] == 1
    assert len(result["report"]["matched"]) == 1
