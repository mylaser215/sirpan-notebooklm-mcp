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


# v7 (260528 ATOM-3) — `{filename} ({folder})` 결정론 매칭 회귀 가드
# 동명 다폴더 ambiguous → matched 전환 검증 (SKILL.md / nlm_seed.md 5건 잔재 사례 박제).


@pytest.fixture
def vault_with_folder_hint_files(tmp_path: Path) -> Path:
    """동명 파일 + 영문 폴더 hint 구조 (외부 ~/.claude/skills 다폴더 모방)."""
    (tmp_path / "skill_a").mkdir()
    (tmp_path / "skill_b").mkdir()
    (tmp_path / "skill_a" / "shared.md").write_text("a", encoding="utf-8")
    (tmp_path / "skill_b" / "shared.md").write_text("b", encoding="utf-8")
    return tmp_path


def test_detect_drift_folder_hint_matches(
    vault_with_folder_hint_files: Path,
) -> None:
    """`{filename} ({folder})` 패턴 → 결정론 matched (ATOM-2 핵심 — v7 5건 잔재 케이스)."""
    fetcher = _make_fetcher([
        {
            "id": "sa",
            "title": "shared.md (skill_a)",
            "source_type_name": "generated_text",
        },
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_folder_hint_files)

    assert len(report["matched"]) == 1
    assert len(report["ambiguous"]) == 0
    assert report["matched"][0]["source_id"] == "sa"
    assert "skill_a" in report["matched"][0]["disk_path"]


def test_detect_drift_folder_hint_no_match_falls_back(
    vault_with_folder_hint_files: Path,
) -> None:
    """`{filename} ({nonexistent})` → 폴더 hint 매칭 실패 → ambiguous 유지."""
    fetcher = _make_fetcher([
        {
            "id": "sb",
            "title": "shared.md (nonexistent_folder)",
            "source_type_name": "generated_text",
        },
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_folder_hint_files)

    assert len(report["ambiguous"]) == 1
    assert len(report["matched"]) == 0


def test_detect_drift_no_hint_still_ambiguous(
    vault_with_folder_hint_files: Path,
) -> None:
    """순수 파일명 (폴더 hint 0) → ambiguous 유지 (호환 — 박제 가설 회귀 차단)."""
    fetcher = _make_fetcher([
        {"id": "sn", "title": "shared.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_folder_hint_files)

    assert len(report["ambiguous"]) == 1
    assert len(report["matched"]) == 0


def test_detect_drift_v7_real_residual_cases(tmp_path: Path) -> None:
    """v7 실 NLM 잔재 5건 케이스 직접 박제 — 영문 폴더명 직접 매칭 우월성.

    실측 (1ffa3a16, 260528): NLM 박제 title이 순수 `SKILL.md` / `nlm_seed.md`만
    이라 ambiguous 5건 누적. ATOM-1 박제 후 `{filename} ({folder})` 패턴이
    `find_disk_path` 결정론 매칭에 흡수되어야 함.

    NLM_SEED_SKILL_KEYWORDS 한글 키워드 매핑은 `extract_filename`이 한글 prefix를
    떼지 못해 glob 0건이 되므로 *실측 NLM title 구조에서는 dead code*임을 확인.
    영문 폴더명 직접 매칭 (`_narrow_by_folder_hint` 신규 분기)만이 유효 경로.
    """
    # 실 skill 폴더 모방 (cross_3step_solver / batch_cross_3step_solver)
    base = tmp_path / "skills_mock"
    (base / "cross_3step_solver").mkdir(parents=True)
    (base / "batch_cross_3step_solver").mkdir(parents=True)
    (base / "cross_3step_solver" / "nlm_seed.md").write_text("a", encoding="utf-8")
    (base / "batch_cross_3step_solver" / "nlm_seed.md").write_text(
        "b", encoding="utf-8"
    )

    # 영문 폴더명 직접 매칭 (ATOM-1로 박제된 신규 title 형식) → matched
    fetcher_with_hint = _make_fetcher([
        {
            "id": "v7",
            "title": "nlm_seed.md (cross_3step_solver)",
            "source_type_name": "generated_text",
        },
    ])
    report = detect_drift(fetcher_with_hint, "nb1", vault_root=tmp_path)
    assert len(report["matched"]) == 1
    assert "cross_3step_solver" in report["matched"][0]["disk_path"]
    assert (
        "batch_cross_3step_solver" not in report["matched"][0]["disk_path"]
    )

    # 한글 키워드 매핑은 extract_filename 결함으로 dead code (호환 매핑 발동 X) → ambiguous 유지
    fetcher_korean = _make_fetcher([
        {
            "id": "kr",
            "title": "단교차 nlm_seed.md",
            "source_type_name": "generated_text",
        },
    ])
    report_kr = detect_drift(fetcher_korean, "nb1", vault_root=tmp_path)
    # extract_filename 결함으로 glob 0건 → missing (호환 매핑 실제 발동 X)
    assert len(report_kr["missing"]) == 1
    assert len(report_kr["matched"]) == 0
