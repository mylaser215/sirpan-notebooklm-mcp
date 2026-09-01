"""sync_helpers detect_drift + format_drift_summary 회귀 가드.

ATOM-2 (세션44, 260521) — `detect_drift`를 MCP tool로 노출하기 전에 신설.
함수 본체는 NLM동기화 ⑥단계에서 매일 호출되지만 유닛 가드가 부재했음.

본 테스트가 깨지면 NLM동기화 ⑥단계가 침묵 회귀 — drift 잔재 누적
(세션342 NLM Pro 한도 incident 재발 위험).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from notebooklm_tools.services import sync_helpers
from notebooklm_tools.services.sync_helpers import (
    _classify_bundle,
    check_processed_stale,
    detect_drift,
    find_disk_path,
    format_drift_summary,
    load_bundle_registry,
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


def test_detect_drift_bundle_origin_dup(vault_with_files: Path) -> None:
    """번들 registry 등재 원본이 낱개 소스로 올라오면 bundle_origin_dup 분류 (세션493).

    라우팅 규칙 미준수 재발(번들 전속 원본이 낱개로 재업로드)을 detect_drift가
    사후 포착 — 기존엔 matched로 silent 통과하던 사각. matched로 새지 않아야 함.
    """
    import json

    essay = vault_with_files / "500-지식정원" / "essay.md"
    reg = vault_with_files / "reg.json"
    reg.write_text(
        json.dumps({"bundles": {"Some_Bundle": {"domain": "t", "files": [str(essay)]}}}),
        encoding="utf-8",
    )
    fetcher = _make_fetcher([
        {"id": "dup1", "title": "essay.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(
        fetcher, "nb1", vault_root=vault_with_files, bundle_registry_path=reg
    )

    assert len(report["bundle_origin_dup"]) == 1
    assert report["bundle_origin_dup"][0]["source_id"] == "dup1"
    assert report["bundle_origin_dup"][0]["status"] == "bundle_origin_dup"
    assert len(report["matched"]) == 0  # matched로 새지 않음
    # 요약에 🔴 경고 노출
    assert "번들원본 낱개중복" in format_drift_summary(report)


def test_detect_drift_bundle_origin_dup_glob(vault_with_files: Path) -> None:
    """glob 패턴(`*.md`) registry 원본도 확장되어 낱개 재업로드를 포착 (세션493 ④)."""
    import json

    reg = vault_with_files / "reg_glob.json"
    pat = str(vault_with_files / "500-지식정원" / "*.md")
    reg.write_text(
        json.dumps({"bundles": {"G_Bundle": {"domain": "t", "files": [pat]}}}),
        encoding="utf-8",
    )
    fetcher = _make_fetcher([
        {"id": "dupg", "title": "essay.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(
        fetcher, "nb1", vault_root=vault_with_files, bundle_registry_path=reg
    )
    assert len(report["bundle_origin_dup"]) == 1
    assert report["bundle_origin_dup"][0]["source_id"] == "dupg"


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


# ---------------------------------------------------------------------------
# Tier 2 N:1 번들 회귀 가드 (Batch 3 ATOM-1, 세션368)
# ---------------------------------------------------------------------------


def _write_bundle_registry(path: Path, bundles: dict) -> Path:
    """Helper — write a minimal bundle registry JSON for tests."""
    payload = {
        "_comment": "test fixture",
        "_version": "1.0",
        "bundles": bundles,
    }
    import json as _json
    path.write_text(_json.dumps(payload), encoding="utf-8")
    return path


def test_load_bundle_registry_fail_safe(tmp_path: Path) -> None:
    """Registry 파일 부재 → 빈 dict (Fail-safe). 예외 0."""
    nonexistent = tmp_path / "missing_registry.json"
    assert load_bundle_registry(nonexistent) == {}


def test_classify_bundle_matched(tmp_path: Path) -> None:
    """Registry 매칭 시 (bundle_name, origins) 반환."""
    reg_path = _write_bundle_registry(
        tmp_path / "reg.json",
        {
            "Utils_Bundle": {
                "domain": "test",
                "files": ["/abs/a.md", "/abs/b.py"],
            }
        },
    )
    registry = load_bundle_registry(reg_path)
    name, origins = _classify_bundle("Utils_Bundle.md", registry)
    assert name == "Utils_Bundle"
    assert origins == ["/abs/a.md", "/abs/b.py"]


def test_classify_bundle_not_registered(tmp_path: Path) -> None:
    """`*_Bundle.md` 형식이지만 registry 미등록 → (None, [])."""
    reg_path = _write_bundle_registry(tmp_path / "reg.json", {})
    registry = load_bundle_registry(reg_path)
    name, origins = _classify_bundle("Ghost_Bundle.md", registry)
    assert name is None
    assert origins == []


def test_classify_bundle_no_bundle_suffix_key(tmp_path: Path) -> None:
    """실 registry 키(`NLM_MCP_Archive`, `_Bundle` 접미사 없음)도 매칭 (B② 결함 픽스)."""
    reg_path = _write_bundle_registry(
        tmp_path / "reg.json",
        {"NLM_MCP_Archive": {"domain": "test", "files": ["/abs/v2.md"]}},
    )
    registry = load_bundle_registry(reg_path)
    name, origins = _classify_bundle("NLM_MCP_Archive.md", registry)
    assert name == "NLM_MCP_Archive"
    assert origins == ["/abs/v2.md"]


def test_classify_bundle_part_suffix(tmp_path: Path) -> None:
    """`{name}_partN.md` → 동일 name + 도메인 origins 서브셋 전체 (1:N 역매핑)."""
    reg_path = _write_bundle_registry(
        tmp_path / "reg.json",
        {"NLM_MCP_Archive": {"domain": "test", "files": ["/abs/v2.md", "/abs/v3.md"]}},
    )
    registry = load_bundle_registry(reg_path)
    for title in ("NLM_MCP_Archive_part1.md", "NLM_MCP_Archive_part2.md"):
        name, origins = _classify_bundle(title, registry)
        assert name == "NLM_MCP_Archive"
        assert origins == ["/abs/v2.md", "/abs/v3.md"]


def test_classify_bundle_part_fp_guard(tmp_path: Path) -> None:
    """`_partN` 형식이어도 name 이 registry 미등록이면 기각 (loose regex FP 차단)."""
    reg_path = _write_bundle_registry(
        tmp_path / "reg.json",
        {"NLM_MCP_Archive": {"domain": "test", "files": ["/abs/v2.md"]}},
    )
    registry = load_bundle_registry(reg_path)
    name, origins = _classify_bundle("my_special_part1.md", registry)
    assert name is None
    assert origins == []


def test_detect_drift_classifies_bundle(tmp_path: Path) -> None:
    """Bundle source → matched_bundle, 기존 matched/missing 비건드림."""
    reg_path = _write_bundle_registry(
        tmp_path / "reg.json",
        {
            "Utils_Bundle": {
                "domain": "test",
                "files": ["/abs/a.md", "/abs/b.py"],
            }
        },
    )
    fetcher = _make_fetcher([
        {"id": "bd", "title": "Utils_Bundle.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(
        fetcher, "nb1", vault_root=tmp_path, bundle_registry_path=reg_path
    )

    assert len(report["matched_bundle"]) == 1
    entry = report["matched_bundle"][0]
    assert entry["status"] == "matched_bundle"
    assert entry["source_id"] == "bd"
    assert entry["bundle_origins"] == ["/abs/a.md", "/abs/b.py"]
    assert entry["markdown_relevant"] is True
    # 기존 카테고리는 비어있어야 (회귀 격리)
    assert len(report["matched"]) == 0
    assert len(report["missing"]) == 0


def test_format_drift_summary_with_bundles(tmp_path: Path) -> None:
    """Summary 1줄에 번들(N:1) 카운트 포함."""
    reg_path = _write_bundle_registry(
        tmp_path / "reg.json",
        {"Utils_Bundle": {"domain": "test", "files": ["/abs/a.md"]}},
    )
    fetcher = _make_fetcher([
        {"id": "bd", "title": "Utils_Bundle.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(
        fetcher, "nb1", vault_root=tmp_path, bundle_registry_path=reg_path
    )
    summary = format_drift_summary(report)
    assert "1 번들(N:1)" in summary


# ---------------------------------------------------------------------------
# 가공 꼬리 fallback (결함 1 박제 — auto_wrap_to_md / generate_code_md.py 산출물)
# ---------------------------------------------------------------------------


@pytest.fixture
def vault_with_processed_tail_files(tmp_path: Path) -> Path:
    """가공 꼬리 산출물 케이스 — raw 원본만 디스크 존재 (NLM title은 .json.md/.py.md)."""
    (tmp_path / "030-Configs" / "시스템환경").mkdir(parents=True)
    (tmp_path / "030-Configs" / "시스템환경" / "nlm_bundle_registry.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "060-Automations").mkdir()
    (tmp_path / "060-Automations" / "vault_cron.py").write_text(
        "# stub", encoding="utf-8"
    )
    return tmp_path


def test_detect_drift_processed_tail_json_md(
    vault_with_processed_tail_files: Path,
) -> None:
    """auto_wrap_to_md 산출물 .json.md → raw .json fallback matched (결함 1 박제)."""
    fetcher = _make_fetcher([
        {
            "id": "a700bfe0",
            "title": "nlm_bundle_registry.json.md",
            "source_type_name": "generated_text",
        }
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_processed_tail_files)
    assert len(report["matched"]) == 1
    assert len(report["missing"]) == 0
    assert report["matched"][0]["disk_path"].endswith("nlm_bundle_registry.json")
    assert report["matched"][0]["markdown_relevant"] is False  # raw .json


def test_detect_drift_processed_tail_py_md(
    vault_with_processed_tail_files: Path,
) -> None:
    """generate_code_md.py 산출물 .py.md → raw .py fallback matched."""
    fetcher = _make_fetcher([
        {
            "id": "dc9135cd",
            "title": "vault_cron.py.md",
            "source_type_name": "generated_text",
        }
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_processed_tail_files)
    assert len(report["matched"]) == 1
    assert len(report["missing"]) == 0
    assert report["matched"][0]["disk_path"].endswith("vault_cron.py")
    assert report["matched"][0]["markdown_relevant"] is False  # raw .py


# ---------------------------------------------------------------------------
# 볼트밖 EXTERNAL_FILE_MAP + 가공 꼬리 정합 (070b566f Split-Brain 오탐 박제)
#
# NLM title 에 가공 꼬리(.md)가 붙은 볼트밖 소스(예: sirpan-sidebar_main.ts.md)가
# find_disk_path 진입부 EXTERNAL_FILE_MAP 조회(원형 키)를 놓치고 _glob_vault(볼트
# 한정)로도 도달 불가하여 상시 missing 오탐 → source_delete 데이터 유실 위험.
# 폴백에서 가공 꼬리를 뗀 raw 키로 EXTERNAL_FILE_MAP 재조회하는 픽스의 회귀 가드.
# ---------------------------------------------------------------------------


def test_find_disk_path_external_with_processed_tail(monkeypatch, tmp_path: Path) -> None:
    """볼트밖 EXTERNAL_FILE_MAP 항목 + 가공 꼬리(.md) title → 외부 경로 1개 matched."""
    ext_file = tmp_path / "external_repo" / "src" / "widget_main.ts"
    ext_file.parent.mkdir(parents=True)
    ext_file.write_text("// stub", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setitem(sync_helpers.EXTERNAL_FILE_MAP, "widget_main.ts", ext_file)

    # NLM title 은 가공 꼬리 .md 가 붙어 진입부 원형 조회를 놓침 → 폴백 재조회로 흡수
    result = find_disk_path("widget_main.ts.md", vault_root=vault)
    assert result == [ext_file]


def test_find_disk_path_external_processed_tail_missing_returns_empty(
    monkeypatch, tmp_path: Path
) -> None:
    """볼트밖 매핑은 있으나 디스크 파일 부재 → [] (Fail-safe, blind 삭제 방지 아님 = 진짜 잔재)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    ghost = tmp_path / "external_repo" / "src" / "gone.ts"  # 미생성 (부재)
    monkeypatch.setitem(sync_helpers.EXTERNAL_FILE_MAP, "gone.ts", ghost)

    result = find_disk_path("gone.ts.md", vault_root=vault)
    assert result == []


def test_detect_drift_dup_disk_path(vault_with_files: Path) -> None:
    """서로 다른 제목의 소스 2개가 같은 디스크 파일을 가리키면 dup_disk_path (세션540).

    실 사고 재현: 본관에 `SKILL.md (suno-lyric-refine)`(폴더태그형 규약)과
    `suno-lyric-refine/SKILL.md`(v7에서 기각된 슬래시형 잔재)가 공존해 같은 로컬
    파일을 가리켰다. 둘 다 각자 len(candidates)==1이라 나란히 matched로 통과했고,
    그날 detect_drift는 "잔재 0 / 모호 1"로 깨끗하게 보고했다 — 중복이 총계 안에
    은폐된 것. source->disk 단방향 검사의 구조적 사각이다.
    """
    fetcher = _make_fetcher([
        {"id": "s1", "title": "guide.md", "source_type_name": "generated_text"},
        {"id": "s2", "title": "050-Docs/guide.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    # 둘 다 matched에서 빠지고 dup_disk_path로 이동
    assert len(report["dup_disk_path"]) == 2
    assert {e["source_id"] for e in report["dup_disk_path"]} == {"s1", "s2"}
    assert all(e["status"] == "dup_disk_path" for e in report["dup_disk_path"])
    assert len(report["matched"]) == 0
    # 파생 계약: matched에서 빠졌으므로 markdown 집계도 오염되지 않는다
    assert len(report["matched_markdown"]) == 0
    # 잔재/모호 어느 버킷도 울리지 않던 것이 이 검사의 존재 이유
    assert len(report["missing"]) == 0
    assert len(report["ambiguous"]) == 0

    summary = format_drift_summary(report)
    assert "2 동일파일 중복소스" in summary
    assert "청소·매핑 보강 권고" in summary


def test_detect_drift_dup_disk_path_clean_when_unique(vault_with_files: Path) -> None:
    """역방향 유일성이 지켜지면 dup_disk_path는 빈 리스트 (인위 샘플 양방향 검증).

    검출기가 상시 발화하는 오탐이 아님을 증명 — 세션530 false-green 학습.
    """
    fetcher = _make_fetcher([
        {"id": "s1", "title": "guide.md", "source_type_name": "generated_text"},
        {"id": "s2", "title": "essay.md", "source_type_name": "generated_text"},
    ])
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)

    assert report["dup_disk_path"] == []
    assert len(report["matched"]) == 2
    assert "0 동일파일 중복소스" in format_drift_summary(report)


def _write_processed_artifact(src: Path, md: Path) -> None:
    """`.{ext}.md` 가공물 1건을 규격대로 생성 (FM에 절대 source_path + 원본 해시)."""
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    md.write_text(
        "---\n"
        f"source_path: {str(src).replace(chr(92), '/')}\n"
        "generated_at: 2026-09-02T03:00\n"
        f"original_sha256: {digest}\n"
        "generator: scripts/generate_code_md.py\n"
        "---\n\n## 원본 코드\n",
        encoding="utf-8",
    )


def test_detect_drift_stale_processed_detects_and_stays_clean(
    vault_with_files: Path,
) -> None:
    """층3 — 가공물 내용 stale 검출 + 인위 샘플 양방향 검증 (세션540).

    `detect_drift`는 원래 "디스크에 파일이 있는가"만 봐서, 원본 코드가 갱신됐는데
    `generate_code_md.py` 재가공을 빠뜨리면 NLM에 구버전이 무음 잔존했다(층3 사각).
    검출기가 상시 발화하는 오탐이 아님을 fresh 경로로 함께 고정한다.
    """
    docs = vault_with_files / "000-시스템" / "050-Docs"
    src = docs / "thing.py"
    src.write_text("print('v1')\n", encoding="utf-8")
    md = docs / "thing.py.md"
    _write_processed_artifact(src, md)

    fetcher = _make_fetcher([
        {"id": "s1", "title": "thing.py.md", "source_type_name": "generated_text"},
    ])

    # (1) fresh — 검출 없음
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)
    assert report["stale_processed"] == []
    assert len(report["matched"]) == 1
    assert "0 가공물 내용 stale" in format_drift_summary(report)

    # (2) 원본만 갱신 (재가공 누락 재현) — stale 검출
    src.write_text("print('v2 — 재가공 누락')\n", encoding="utf-8")
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)
    assert len(report["stale_processed"]) == 1
    assert report["stale_processed"][0]["status"] == "stale"
    assert report["stale_processed"][0]["source_id"] == "s1"
    # 파생 뷰이므로 matched 카운트 계약은 무손상
    assert len(report["matched"]) == 1
    summary = format_drift_summary(report)
    assert "1 가공물 내용 stale" in summary
    assert "청소·매핑 보강 권고" in summary

    # (3) 원본 소실 — origin_missing
    src.unlink()
    report = detect_drift(fetcher, "nb1", vault_root=vault_with_files)
    assert report["stale_processed"][0]["status"] == "origin_missing"


def test_check_processed_stale_ignores_plain_md(vault_with_files: Path) -> None:
    """일반 `.md` 노트는 가공물이 아니므로 판정 대상 밖 (None)."""
    assert check_processed_stale(vault_with_files / "500-지식정원" / "essay.md") is None
