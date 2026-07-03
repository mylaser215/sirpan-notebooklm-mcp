"""Regression guards for services.sources.sync_bundle (Batch 3 ATOM-3, 세션368).

Mocks the NLM client + the bundle builder script so tests are network-free
and OS-temp-safe. Covers add/replace dispatch, registry lookup, and
fail-close pre-flight checks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from notebooklm_tools.services import sources as sources_service
from notebooklm_tools.services import sync_helpers
from notebooklm_tools.services.errors import ServiceError, ValidationError
from notebooklm_tools.services.sources import sync_bundle
from notebooklm_tools.services.sync_helpers import _should_skip_bundle_upload


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def origin_files(tmp_path: Path) -> list[Path]:
    """Three minimal origin files for a fake bundle."""
    a = tmp_path / "origin_a.md"
    b = tmp_path / "origin_b.py"
    a.write_text("# A\n", encoding="utf-8")
    b.write_text("x = 1\n", encoding="utf-8")
    return [a, b]


@pytest.fixture
def registry_path(tmp_path: Path, origin_files: list[Path]) -> Path:
    """Bundle registry referencing the origin files above."""
    reg = tmp_path / "bundle_registry.json"
    reg.write_text(
        json.dumps(
            {
                "_version": "1.0",
                "bundles": {
                    "Test_Bundle": {
                        "domain": "test",
                        "files": [str(p) for p in origin_files],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return reg


def _bundle_tool_script() -> Path:
    """Resolve the real generator script for E2E builder invocation."""
    return (
        Path(__file__).resolve().parents[2]
        / "src"
        / "notebooklm_tools"
        / "scripts"
        / "generate_bundle_md.py"
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_sync_bundle_add_new(
    mock_client: MagicMock, registry_path: Path
) -> None:
    """No matching source in NLM → add_source path; mode == 'add'."""
    mock_client.get_notebook_sources_with_types.return_value = [
        {"id": "other-id", "title": "Other.md", "source_type_name": "generated_text"},
    ]
    mock_client.add_file.return_value = {"id": "new-bundle-id", "title": "Test_Bundle.md"}

    result = sync_bundle(
        mock_client,
        "nb1",
        "Test_Bundle",
        registry_path=registry_path,
        bundle_tool_script=_bundle_tool_script(),
        python_executable=sys.executable,
    )

    assert result["mode"] == "add"
    assert result["bundle_name"] == "Test_Bundle"
    assert result["source_id"] == "new-bundle-id"
    assert result["bundled_count"] == 2
    mock_client.add_file.assert_called_once()
    mock_client.delete_source.assert_not_called()


def test_sync_bundle_replace_existing(
    mock_client: MagicMock, registry_path: Path
) -> None:
    """Matching title in NLM → replace_source_file(atomic=True); mode == 'replace'."""
    mock_client.get_notebook_sources_with_types.return_value = [
        {"id": "old-bundle-id", "title": "Test_Bundle.md", "source_type_name": "generated_text"},
    ]
    # atomic replace = ADD-first then DELETE; mock both.
    mock_client.add_file.return_value = {"id": "new-bundle-id", "title": "Test_Bundle.md"}
    mock_client.delete_source.return_value = True
    mock_client.list_notes.return_value = []  # _resolve_source_type fallback

    result = sync_bundle(
        mock_client,
        "nb1",
        "Test_Bundle",
        registry_path=registry_path,
        bundle_tool_script=_bundle_tool_script(),
        python_executable=sys.executable,
    )

    assert result["mode"] == "replace"
    assert result["source_id"] == "new-bundle-id"
    assert result["bundled_count"] == 2
    mock_client.add_file.assert_called_once()
    mock_client.delete_source.assert_called_once()


# ---------------------------------------------------------------------------
# 1:N chunking (Full-Sync: multipart add + stale part deletion)
# ---------------------------------------------------------------------------

@pytest.fixture
def registry_path_maxwords(tmp_path: Path, origin_files: list[Path]) -> Path:
    """Registry whose max_words=1 forces one part per origin file (2 parts)."""
    reg = tmp_path / "reg_mw.json"
    reg.write_text(
        json.dumps(
            {
                "_version": "1.0",
                "bundles": {
                    "Test_Bundle": {
                        "domain": "test",
                        "files": [str(p) for p in origin_files],
                        "max_words": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return reg


def test_sync_bundle_multipart_add(
    mock_client: MagicMock, registry_path_maxwords: Path
) -> None:
    """max_words=1 → 2 parts, both new → add ×2; parts/source_ids reflect split."""
    mock_client.get_notebook_sources_with_types.return_value = []
    mock_client.add_file.return_value = {"id": "new-id", "title": "Test_Bundle_part1.md"}

    result = sync_bundle(
        mock_client,
        "nb1",
        "Test_Bundle",
        registry_path=registry_path_maxwords,
        bundle_tool_script=_bundle_tool_script(),
        python_executable=sys.executable,
    )

    assert result["mode"] == "add"
    assert result["parts"] == 2
    assert len(result["source_ids"]) == 2
    assert result["source_id"] == "new-id"
    assert mock_client.add_file.call_count == 2
    mock_client.delete_source.assert_not_called()


def test_sync_bundle_stale_part_deleted(
    mock_client: MagicMock, registry_path_maxwords: Path
) -> None:
    """3 existing parts, only 2 regenerated → stale part3 deleted (DELETE-last)."""
    mock_client.get_notebook_sources_with_types.return_value = [
        {"id": "p1", "title": "Test_Bundle_part1.md", "source_type_name": "generated_text"},
        {"id": "p2", "title": "Test_Bundle_part2.md", "source_type_name": "generated_text"},
        {"id": "p3-stale", "title": "Test_Bundle_part3.md", "source_type_name": "generated_text"},
    ]
    mock_client.add_file.return_value = {"id": "new-id", "title": "Test_Bundle_part1.md"}
    mock_client.delete_source.return_value = True
    mock_client.list_notes.return_value = []

    result = sync_bundle(
        mock_client,
        "nb1",
        "Test_Bundle",
        registry_path=registry_path_maxwords,
        bundle_tool_script=_bundle_tool_script(),
        python_executable=sys.executable,
    )

    assert result["parts"] == 2
    assert result["mode"] == "replace"
    # The stale part3 must have been deleted (its source_id appears in a delete call).
    deleted_ids = [c.args[0] for c in mock_client.delete_source.call_args_list]
    assert "p3-stale" in deleted_ids


# ---------------------------------------------------------------------------
# Fail-close: pre-flight validation
# ---------------------------------------------------------------------------

def test_sync_bundle_unknown_name(
    mock_client: MagicMock, registry_path: Path
) -> None:
    """Unregistered bundle name → ValidationError; no NLM call made."""
    with pytest.raises(ValidationError) as excinfo:
        sync_bundle(
            mock_client,
            "nb1",
            "Ghost_Bundle",
            registry_path=registry_path,
            bundle_tool_script=_bundle_tool_script(),
        )
    assert "not registered" in str(excinfo.value).lower()
    mock_client.add_file.assert_not_called()
    mock_client.delete_source.assert_not_called()


def test_sync_bundle_missing_origin_file(
    mock_client: MagicMock, tmp_path: Path
) -> None:
    """Origin file gone from disk → ValidationError before any NLM call."""
    reg = tmp_path / "reg.json"
    reg.write_text(
        json.dumps(
            {
                "_version": "1.0",
                "bundles": {
                    "Ghost_Bundle": {
                        "domain": "test",
                        "files": [str(tmp_path / "does_not_exist.md")],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError) as excinfo:
        sync_bundle(
            mock_client,
            "nb1",
            "Ghost_Bundle",
            registry_path=reg,
            bundle_tool_script=_bundle_tool_script(),
        )
    assert "missing" in str(excinfo.value).lower()
    mock_client.add_file.assert_not_called()


def test_sync_bundle_empty_files_list(
    mock_client: MagicMock, tmp_path: Path
) -> None:
    """Bundle entry has empty files list → ValidationError."""
    reg = tmp_path / "reg.json"
    reg.write_text(
        json.dumps(
            {
                "_version": "1.0",
                "bundles": {"Empty_Bundle": {"domain": "test", "files": []}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        sync_bundle(
            mock_client,
            "nb1",
            "Empty_Bundle",
            registry_path=reg,
            bundle_tool_script=_bundle_tool_script(),
        )
    mock_client.add_file.assert_not_called()


# ---------------------------------------------------------------------------
# Bundle tool missing
# ---------------------------------------------------------------------------

def test_sync_bundle_tool_script_missing(
    mock_client: MagicMock, registry_path: Path, tmp_path: Path
) -> None:
    """Builder script path doesn't exist → ServiceError; NLM not touched."""
    with pytest.raises(ServiceError) as excinfo:
        sync_bundle(
            mock_client,
            "nb1",
            "Test_Bundle",
            registry_path=registry_path,
            bundle_tool_script=tmp_path / "no_such_tool.py",
        )
    assert "not found" in str(excinfo.value).lower()
    mock_client.add_file.assert_not_called()


# ---------------------------------------------------------------------------
# Smoke: service exposes the symbol (catches name-collision regressions)
# ---------------------------------------------------------------------------

def test_sync_bundle_exported() -> None:
    """sync_bundle is importable from the sources service module."""
    assert hasattr(sources_service, "sync_bundle")
    assert callable(sources_service.sync_bundle)


# ---------------------------------------------------------------------------
# v10 git churn skip — _should_skip_bundle_upload (세션409)
# ---------------------------------------------------------------------------

class _FakeProc:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout


@pytest.fixture
def vault_with_anchor(tmp_path: Path) -> Path:
    """Vault root holding a valid .last_nlm_sync anchor (한글 경로 포함)."""
    anchor_dir = tmp_path / "000-시스템" / "050-Docs"
    anchor_dir.mkdir(parents=True)
    (anchor_dir / ".last_nlm_sync").write_text("deadbeef", encoding="utf-8")
    return tmp_path


def test_skip_when_no_changes(
    vault_with_anchor: Path, origin_files: list[Path], monkeypatch
) -> None:
    """앵커 존재 + git diff 빈 stdout → skip=True (업로드 회피)."""
    monkeypatch.setattr(
        sync_helpers.subprocess, "run", lambda *a, **k: _FakeProc(0, "")
    )
    assert _should_skip_bundle_upload(vault_with_anchor, origin_files) is True


def test_no_skip_when_changed(
    vault_with_anchor: Path, origin_files: list[Path], monkeypatch
) -> None:
    """git diff가 변경 파일을 반환 → skip=False (업로드)."""
    monkeypatch.setattr(
        sync_helpers.subprocess,
        "run",
        lambda *a, **k: _FakeProc(0, "500-지식정원/origin_a.md\n"),
    )
    assert _should_skip_bundle_upload(vault_with_anchor, origin_files) is False


def test_failsafe_missing_anchor(
    tmp_path: Path, origin_files: list[Path]
) -> None:
    """앵커 파일 부재 (첫 동기화 등) → False (fail-safe 업로드)."""
    assert _should_skip_bundle_upload(tmp_path, origin_files) is False


def test_failsafe_git_error(
    vault_with_anchor: Path, origin_files: list[Path], monkeypatch
) -> None:
    """git returncode != 0 (무효 앵커 등) → False (fail-safe 업로드)."""
    monkeypatch.setattr(
        sync_helpers.subprocess, "run", lambda *a, **k: _FakeProc(128, "")
    )
    assert _should_skip_bundle_upload(vault_with_anchor, origin_files) is False


def test_failsafe_empty_files(vault_with_anchor: Path) -> None:
    """빈 파일 목록 → False (Empty List 덫 방어: `git diff --` 뒤 빈 경로=전체 스캔)."""
    assert _should_skip_bundle_upload(vault_with_anchor, []) is False


def test_sync_bundle_skips_when_unchanged(
    mock_client: MagicMock, registry_path: Path, monkeypatch
) -> None:
    """skip 판정 True → mode=='skip', NLM 전혀 안 건드림 (조회·업로드 0)."""
    monkeypatch.setattr(
        sources_service, "_should_skip_bundle_upload", lambda *a, **k: True
    )
    result = sync_bundle(
        mock_client,
        "nb1",
        "Test_Bundle",
        registry_path=registry_path,
        bundle_tool_script=_bundle_tool_script(),
        python_executable=sys.executable,
    )
    assert result["mode"] == "skip"
    assert result["parts"] == 0
    assert result["source_id"] == ""
    assert result["source_ids"] == []
    assert result["bundled_count"] == 2
    mock_client.add_file.assert_not_called()
    mock_client.get_notebook_sources_with_types.assert_not_called()
    mock_client.delete_source.assert_not_called()
