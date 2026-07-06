"""Tests for `nlm notebook clone` and `nlm source replace-file` CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from notebooklm_tools.cli.commands.notebook import app as notebook_app
from notebooklm_tools.cli.commands.source import app as source_app


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client_cm():
    """Mock context manager yielding a client."""
    client = MagicMock()
    cm = MagicMock()
    cm.__enter__ = lambda self: client
    cm.__exit__ = MagicMock(return_value=False)
    return cm


@pytest.fixture
def alias_identity():
    """Alias manager that returns its input unchanged."""
    mgr = MagicMock()
    mgr.resolve.side_effect = lambda x: x
    return mgr


class TestNotebookCloneCli:
    """Test `nlm notebook clone` command."""

    def _clone_result(self, **overrides):
        base = {
            "new_notebook_id": "nb-new",
            "new_title": "Cloned NB",
            "cloned_sources": [{"source_type": "web_page", "source_id": "s1", "title": "A"}],
            "cloned_notes": [{"note_id": "n1", "title": "Note A"}],
            "skipped": [],
            "total_cloned": 2,
        }
        base.update(overrides)
        return base

    def test_clone_invokes_service_with_default_exclude(
        self, runner, mock_client_cm, alias_identity
    ):
        result_dict = self._clone_result()

        with (
            patch(
                "notebooklm_tools.cli.commands.notebook.get_alias_manager",
                return_value=alias_identity,
            ),
            patch(
                "notebooklm_tools.cli.commands.notebook.get_client",
                return_value=mock_client_cm,
            ),
            patch(
                "notebooklm_tools.cli.commands.notebook.notebooks_service.clone_notebook",
                return_value=result_dict,
            ) as clone_mock,
        ):
            r = runner.invoke(
                notebook_app,
                ["clone", "nb-src", "Cloned NB"],
            )

        assert r.exit_code == 0
        # default: exclude_types=None
        clone_mock.assert_called_once()
        kwargs = clone_mock.call_args.kwargs
        assert kwargs["exclude_types"] is None
        assert "nb-new" in r.stdout

    def test_clone_exclude_option_parses_csv(self, runner, mock_client_cm, alias_identity):
        result_dict = self._clone_result()

        with (
            patch(
                "notebooklm_tools.cli.commands.notebook.get_alias_manager",
                return_value=alias_identity,
            ),
            patch(
                "notebooklm_tools.cli.commands.notebook.get_client",
                return_value=mock_client_cm,
            ),
            patch(
                "notebooklm_tools.cli.commands.notebook.notebooks_service.clone_notebook",
                return_value=result_dict,
            ) as clone_mock,
        ):
            r = runner.invoke(
                notebook_app,
                [
                    "clone",
                    "nb-src",
                    "Cloned",
                    "--exclude",
                    "url, note ,pdf",
                ],
            )

        assert r.exit_code == 0
        kwargs = clone_mock.call_args.kwargs
        assert kwargs["exclude_types"] == ["url", "note", "pdf"]


class TestSourceReplaceFileCli:
    """Test `nlm source replace-file` command."""

    def _replace_result(self):
        return {
            "notebook_id": "nb-1",
            "old_source_id": "src-old",
            "new_source_id": "src-new",
            "title": "doc.txt",
            "file_path": "/tmp/doc.txt",
            "message": "Replaced source src-old with src-new",
        }

    def test_replace_with_confirm_flag(self, runner, mock_client_cm, alias_identity, tmp_path):
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")
        result_dict = self._replace_result()

        with (
            patch(
                "notebooklm_tools.cli.commands.source.get_alias_manager",
                return_value=alias_identity,
            ),
            patch(
                "notebooklm_tools.cli.commands.source.get_client", return_value=mock_client_cm
            ),
            patch(
                "notebooklm_tools.cli.commands.source.sources_service.replace_source_file",
                return_value=result_dict,
            ) as replace_mock,
        ):
            r = runner.invoke(
                source_app,
                ["replace-file", "nb-1", str(file_path), "--source-id", "src-old", "--confirm"],
            )

        assert r.exit_code == 0
        replace_mock.assert_called_once()
        args = replace_mock.call_args.args
        kwargs = replace_mock.call_args.kwargs
        # call: replace_source_file(client, notebook_id, file_path, source_id=..., ...)
        assert args[1:] == ("nb-1", str(file_path))
        assert kwargs.get("source_id") == "src-old"
        assert "src-new" in r.stdout

    def test_replace_without_confirm_aborts(
        self, runner, mock_client_cm, alias_identity, tmp_path
    ):
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        with (
            patch(
                "notebooklm_tools.cli.commands.source.get_alias_manager",
                return_value=alias_identity,
            ),
            patch(
                "notebooklm_tools.cli.commands.source.get_client", return_value=mock_client_cm
            ),
            patch(
                "notebooklm_tools.cli.commands.source.sources_service.replace_source_file"
            ) as replace_mock,
        ):
            # Send "n" to the confirmation prompt
            r = runner.invoke(
                source_app,
                ["replace-file", "nb-1", str(file_path), "--source-id", "src-old"],
                input="n\n",
            )

        # typer aborts with non-zero exit when user declines
        assert r.exit_code != 0
        replace_mock.assert_not_called()
