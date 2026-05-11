"""Tests for services.notebooks module."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from notebooklm_tools.services.errors import (
    CreationError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from notebooklm_tools.services.notebooks import (
    clone_notebook,
    create_notebook,
    delete_notebook,
    describe_notebook,
    get_notebook,
    list_notebooks,
    rename_notebook,
)


@pytest.fixture
def mock_client():
    return MagicMock()


def _make_notebook(**kwargs):
    """Create a mock notebook object with default attrs."""
    defaults = {
        "id": "nb-1",
        "title": "Test Notebook",
        "source_count": 3,
        "url": "https://notebooklm.google.com/notebook/nb-1",
        "ownership": "owned",
        "is_owned": True,
        "is_shared": False,
        "created_at": "2024-01-01",
        "modified_at": "2024-01-02",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestListNotebooks:
    """Test list_notebooks service function."""

    def test_returns_notebooks_with_counts(self, mock_client):
        mock_client.list_notebooks.return_value = [
            _make_notebook(id="nb-1", is_owned=True, is_shared=False),
            _make_notebook(id="nb-2", is_owned=True, is_shared=True),
            _make_notebook(id="nb-3", is_owned=False, is_shared=False),
        ]

        result = list_notebooks(mock_client)

        assert result["count"] == 3
        assert result["owned_count"] == 2
        assert result["shared_count"] == 1
        assert result["shared_by_me_count"] == 1
        assert len(result["notebooks"]) == 3

    def test_max_results_truncates(self, mock_client):
        mock_client.list_notebooks.return_value = [_make_notebook(id=f"nb-{i}") for i in range(10)]

        result = list_notebooks(mock_client, max_results=3)

        assert len(result["notebooks"]) == 3
        assert result["count"] == 10  # count reflects total, not truncated

    def test_empty_list(self, mock_client):
        mock_client.list_notebooks.return_value = []

        result = list_notebooks(mock_client)

        assert result["count"] == 0
        assert result["notebooks"] == []

    def test_api_error_raises_service_error(self, mock_client):
        mock_client.list_notebooks.side_effect = RuntimeError("API error")
        with pytest.raises(ServiceError, match="Failed to list notebooks"):
            list_notebooks(mock_client)


class TestGetNotebook:
    """Test get_notebook service function."""

    def test_raw_rpc_list_parsed(self, mock_client):
        # Simulate the nested list structure from the API
        mock_client.get_notebook.return_value = [
            [
                "My Notebook",  # title
                [  # sources
                    [["src-1"], "Source A"],
                    [["src-2"], "Source B"],
                ],
                "nb-123",  # id
            ]
        ]

        result = get_notebook(mock_client, "nb-123")

        assert result["notebook_id"] == "nb-123"
        assert result["title"] == "My Notebook"
        assert result["source_count"] == 2
        assert result["sources"][0]["id"] == "src-1"
        assert result["sources"][1]["title"] == "Source B"

    def test_dataclass_fallback(self, mock_client):
        mock_client.get_notebook.return_value = _make_notebook(id="nb-42", title="Fallback")

        result = get_notebook(mock_client, "nb-42")

        assert result["notebook_id"] == "nb-42"
        assert result["title"] == "Fallback"

    def test_none_raises_not_found(self, mock_client):
        mock_client.get_notebook.return_value = None
        with pytest.raises(NotFoundError, match="not found"):
            get_notebook(mock_client, "nb-missing")

    def test_api_error_raises_service_error(self, mock_client):
        mock_client.get_notebook.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to get notebook"):
            get_notebook(mock_client, "nb-123")


class TestDescribeNotebook:
    """Test describe_notebook service function."""

    def test_returns_summary_and_topics(self, mock_client):
        mock_client.get_notebook_summary.return_value = {
            "summary": "A great notebook about AI.",
            "suggested_topics": ["machine learning", "neural networks"],
        }

        result = describe_notebook(mock_client, "nb-123")

        assert "AI" in result["summary"]
        assert len(result["suggested_topics"]) == 2

    def test_falsy_result_raises_service_error(self, mock_client):
        mock_client.get_notebook_summary.return_value = None
        with pytest.raises(ServiceError, match="no data"):
            describe_notebook(mock_client, "nb-123")

    def test_api_error_raises_service_error(self, mock_client):
        mock_client.get_notebook_summary.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to get notebook summary"):
            describe_notebook(mock_client, "nb-123")


class TestCreateNotebook:
    """Test create_notebook service function."""

    def test_successful_creation(self, mock_client):
        mock_client.create_notebook.return_value = _make_notebook(id="nb-new", title="New NB")

        result = create_notebook(mock_client, "New NB")

        assert result["notebook_id"] == "nb-new"
        assert result["title"] == "New NB"
        assert "Created" in result["message"]

    def test_falsy_result_raises_creation_error(self, mock_client):
        mock_client.create_notebook.return_value = None
        with pytest.raises(CreationError, match="no data"):
            create_notebook(mock_client, "Test")

    def test_api_error_raises_creation_error(self, mock_client):
        mock_client.create_notebook.side_effect = RuntimeError("fail")
        with pytest.raises(CreationError, match="Failed to create notebook"):
            create_notebook(mock_client, "Test")


class TestRenameNotebook:
    """Test rename_notebook service function."""

    def test_successful_rename(self, mock_client):
        mock_client.rename_notebook.return_value = True

        result = rename_notebook(mock_client, "nb-123", "New Title")

        assert result["new_title"] == "New Title"
        assert "Renamed" in result["message"]

    def test_empty_title_raises_validation_error(self, mock_client):
        with pytest.raises(ValidationError, match="title"):
            rename_notebook(mock_client, "nb-123", "")

    def test_whitespace_title_raises_validation_error(self, mock_client):
        with pytest.raises(ValidationError, match="title"):
            rename_notebook(mock_client, "nb-123", "   ")

    def test_falsy_result_raises_service_error(self, mock_client):
        mock_client.rename_notebook.return_value = None
        with pytest.raises(ServiceError, match="falsy result"):
            rename_notebook(mock_client, "nb-123", "Valid Title")

    def test_api_error_raises_service_error(self, mock_client):
        mock_client.rename_notebook.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to rename notebook"):
            rename_notebook(mock_client, "nb-123", "Valid Title")


class TestDeleteNotebook:
    """Test delete_notebook service function."""

    def test_successful_deletion(self, mock_client):
        mock_client.delete_notebook.return_value = True

        result = delete_notebook(mock_client, "nb-123")

        assert "deleted" in result["message"].lower()

    def test_falsy_result_raises_service_error(self, mock_client):
        mock_client.delete_notebook.return_value = None
        with pytest.raises(ServiceError, match="falsy result"):
            delete_notebook(mock_client, "nb-123")

    def test_api_error_raises_service_error(self, mock_client):
        mock_client.delete_notebook.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to delete notebook"):
            delete_notebook(mock_client, "nb-123")


def _clone_fixture_client(sources=None, notes=None, create_id="nb-clone"):
    """Build a MagicMock client preconfigured for clone_notebook scenarios."""
    client = MagicMock()
    client.get_notebook.return_value = [["Src Title", [], "nb-src"]]
    client.get_notebook_sources_with_types.return_value = sources or []
    client.list_notes.return_value = notes or []
    client.create_notebook.return_value = _make_notebook(id=create_id, title="Cloned")
    client.add_url_source.return_value = {"id": "url-new", "title": "Url Page"}
    client.add_text_source.return_value = {"id": "text-new", "title": "Pasted"}
    client.add_drive_source.return_value = {"id": "drive-new", "title": "Drive Doc"}
    client.get_source_fulltext.return_value = {"content": "body", "title": "Pasted"}
    client.create_note.return_value = {"id": "note-new", "title": "Note A", "content": "x"}
    client.delete_notebook.return_value = True
    return client


class TestCloneNotebook:
    """Test clone_notebook service function."""

    def test_happy_path_clones_urls_text_and_note(self):
        sources = [
            {
                "id": "s1",
                "title": "Page A",
                "source_type": 5,
                "source_type_name": "web_page",
                "url": "https://example.com/a",
            },
            {
                "id": "s2",
                "title": "Page B",
                "source_type": 5,
                "source_type_name": "web_page",
                "url": "https://example.com/b",
            },
            {
                "id": "s3",
                "title": "Pasted",
                "source_type": 4,
                "source_type_name": "pasted_text",
            },
        ]
        notes = [{"id": "n1", "title": "Note A", "content": "hello"}]
        client = _clone_fixture_client(sources=sources, notes=notes)

        result = clone_notebook(client, "nb-src", "Cloned")

        assert result["new_notebook_id"] == "nb-clone"
        assert result["new_title"] == "Cloned"
        assert result["total_cloned"] == 4
        assert len(result["cloned_sources"]) == 3
        assert len(result["cloned_notes"]) == 1
        assert result["skipped"] == []
        assert client.add_url_source.call_count == 2
        assert client.add_text_source.call_count == 1
        assert client.create_note.call_count == 1

    def test_default_excludes_binary_pdf(self):
        sources = [
            {
                "id": "s1",
                "title": "Doc.pdf",
                "source_type": 3,
                "source_type_name": "pdf",
            },
            {
                "id": "s2",
                "title": "Page",
                "source_type": 5,
                "source_type_name": "web_page",
                "url": "https://example.com",
            },
        ]
        client = _clone_fixture_client(sources=sources)

        result = clone_notebook(client, "nb-src", "Cloned")

        assert len(result["cloned_sources"]) == 1
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["type"] == "pdf"
        assert result["skipped"][0]["reason"] == "binary_no_source_file"
        client.add_drive_source.assert_not_called()

    def test_exclude_types_url_skips_all_urls(self):
        sources = [
            {
                "id": "s1",
                "title": "Page A",
                "source_type": 5,
                "source_type_name": "web_page",
                "url": "https://example.com/a",
            },
            {
                "id": "s2",
                "title": "Page B",
                "source_type": 9,
                "source_type_name": "youtube",
                "url": "https://youtu.be/x",
            },
        ]
        client = _clone_fixture_client(sources=sources)

        result = clone_notebook(client, "nb-src", "Cloned", exclude_types=["web_page", "youtube"])

        assert len(result["cloned_sources"]) == 0
        assert len(result["skipped"]) == 2
        assert all(s["reason"] == "excluded" for s in result["skipped"])
        client.add_url_source.assert_not_called()

    def test_fail_close_rollback_on_add_failure(self):
        sources = [
            {
                "id": "s1",
                "title": "Page A",
                "source_type": 5,
                "source_type_name": "web_page",
                "url": "https://example.com/a",
            },
            {
                "id": "s2",
                "title": "Page B",
                "source_type": 5,
                "source_type_name": "web_page",
                "url": "https://example.com/b",
            },
        ]
        client = _clone_fixture_client(sources=sources)
        client.add_url_source.side_effect = [
            {"id": "url-1", "title": "Page A"},
            RuntimeError("API rate-limited"),
        ]

        with pytest.raises(ServiceError, match="Clone failed"):
            clone_notebook(client, "nb-src", "Cloned")

        client.delete_notebook.assert_called_once_with("nb-clone")

    def test_source_notebook_not_found_raises(self):
        client = _clone_fixture_client()
        client.get_notebook.return_value = None

        with pytest.raises(NotFoundError, match="not found"):
            clone_notebook(client, "nb-missing", "Cloned")

        client.create_notebook.assert_not_called()

    def test_empty_new_title_raises_validation(self):
        client = _clone_fixture_client()
        with pytest.raises(ValidationError, match="new_title"):
            clone_notebook(client, "nb-src", "   ")
