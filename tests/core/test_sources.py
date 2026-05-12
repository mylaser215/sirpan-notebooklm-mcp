"""Tests for SourceMixin class."""

from unittest.mock import MagicMock, patch

import pytest


def test_source_mixin_import():
    """Test that SourceMixin can be imported."""
    from notebooklm_tools.core.sources import SourceMixin

    assert SourceMixin is not None


def test_source_mixin_inherits_base():
    """Test that SourceMixin inherits from BaseClient."""
    from notebooklm_tools.core.base import BaseClient
    from notebooklm_tools.core.sources import SourceMixin

    assert issubclass(SourceMixin, BaseClient)


def test_source_mixin_has_methods():
    """Test that SourceMixin has all expected methods."""
    from notebooklm_tools.core.sources import SourceMixin

    expected_methods = [
        "check_source_freshness",
        "sync_drive_source",
        "delete_source",
        "get_notebook_sources_with_types",
        "add_url_source",
        "add_text_source",
        "add_drive_source",
        "add_file",  # HTTP-based file upload
        "get_source_guide",
        "get_source_fulltext",
    ]

    for method_name in expected_methods:
        assert hasattr(SourceMixin, method_name), f"Missing method: {method_name}"


def test_add_url_source_uses_correct_rpc():
    """Test that add_url_source calls the correct RPC."""
    from notebooklm_tools.core.sources import SourceMixin

    with patch.object(SourceMixin, "_refresh_auth_tokens"):  # noqa: SIM117
        with patch.object(SourceMixin, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.text = ')]}\'\n[[["wrb.fr","abcdef","[[]]",null,null,null,"generic"]]]'
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            with patch.object(SourceMixin, "_parse_response") as mock_parse:
                mock_parse.return_value = []
                with patch.object(SourceMixin, "_extract_rpc_result") as mock_extract:
                    mock_extract.return_value = [[[[["id123"], "Test Source"]]]]

                    mixin = SourceMixin(cookies={"test": "cookie"}, csrf_token="test")
                    mixin.add_url_source("notebook_id_123", "https://example.com")

                    mock_client.post.assert_called_once()


def test_delete_source_uses_correct_rpc():
    """Test that delete_source calls the correct RPC."""
    from notebooklm_tools.core.sources import SourceMixin

    with patch.object(SourceMixin, "_refresh_auth_tokens"):  # noqa: SIM117
        with patch.object(SourceMixin, "_get_client") as mock_get_client:
            mock_response = MagicMock()
            mock_response.text = ')]}\'\n[[["wrb.fr","abcdef","[]",null,null,null,"generic"]]]'
            mock_client = MagicMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client

            with patch.object(SourceMixin, "_parse_response") as mock_parse:
                mock_parse.return_value = []
                with patch.object(SourceMixin, "_extract_rpc_result") as mock_extract:
                    mock_extract.return_value = []

                    mixin = SourceMixin(cookies={"test": "cookie"}, csrf_token="test")
                    result = mixin.delete_source("source_id_123")

                    mock_client.post.assert_called_once()
                    assert result is True


def test_get_source_guide_uses_call_rpc():
    """Test that get_source_guide uses _call_rpc."""
    from notebooklm_tools.core.sources import SourceMixin

    with patch.object(SourceMixin, "_refresh_auth_tokens"):  # noqa: SIM117
        with patch.object(SourceMixin, "_call_rpc") as mock_rpc:
            mock_rpc.return_value = []

            mixin = SourceMixin(cookies={"test": "cookie"}, csrf_token="test")
            result = mixin.get_source_guide("source_id_123")

            mock_rpc.assert_called_once()
            assert result == {"summary": "", "keywords": []}


class TestDeleteSourceRouting:
    """Type-aware routing for delete_source / delete_sources.

    Generated_text sources are NotebookLM 'Note' objects and require
    RPC AH0mwd (delete_note) instead of tGMBJ (delete_source).
    """

    def test_delete_source_routes_generated_text_to_note(self):
        from notebooklm_tools.core.client import NotebookLMClient
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "delete_note") as mock_delete_note:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_delete_note.return_value = True
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.delete_source(
                        "src_id",
                        notebook_id="nb_id",
                        source_type=SOURCE_TYPE_GENERATED_TEXT,
                    )

                    mock_delete_note.assert_called_once_with("src_id", "nb_id")
                    mock_rpc.assert_not_called()
                    assert result is True

    def test_delete_source_regular_uses_tgmbj(self):
        from notebooklm_tools.core.client import NotebookLMClient
        from notebooklm_tools.core.constants import SOURCE_TYPE_PASTED_TEXT

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "delete_note") as mock_delete_note:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_rpc.return_value = []
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.delete_source(
                        "src_id",
                        notebook_id="nb_id",
                        source_type=SOURCE_TYPE_PASTED_TEXT,
                    )

                    mock_delete_note.assert_not_called()
                    mock_rpc.assert_called_once()
                    args = mock_rpc.call_args[0]
                    assert args[0] == NotebookLMClient.RPC_DELETE_SOURCE
                    assert args[1] == [[["src_id"]], [2]]
                    assert result is True

    def test_delete_source_no_notebook_id_uses_legacy(self):
        """Backward compat: no notebook_id → no routing → legacy tGMBJ."""
        from notebooklm_tools.core.client import NotebookLMClient

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "delete_note") as mock_delete_note:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_rpc.return_value = []
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.delete_source("src_id")

                    mock_delete_note.assert_not_called()
                    mock_rpc.assert_called_once()
                    assert result is True

    def test_delete_sources_batch_splits_by_type(self):
        """Mixed batch: notes (list_notes 멤버십) → delete_note, regular sources → tGMBJ batch.

        v3 회귀 픽스 (세션310): get_notebook의 metadata[4]가 모든 text source에서 8로
        응답되어 SOURCE_TYPE_GENERATED_TEXT 상수와 우연 일치 → sources_meta source_type
        신뢰 폐기. list_notes 멤버십(+content 키)을 단일 권위 기준으로 사용.
        """
        from notebooklm_tools.core.client import NotebookLMClient

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "list_notes") as mock_list_notes:
                with patch.object(NotebookLMClient, "delete_note") as mock_delete_note:
                    with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                        mock_list_notes.return_value = [
                            {"id": "note1", "content": "body1"},
                            {"id": "note2", "content": "body2"},
                        ]
                        mock_delete_note.return_value = True
                        mock_rpc.return_value = []
                        client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                        result = client.delete_sources(
                            ["note1", "src1", "note2"], notebook_id="nb_id"
                        )

                        # Notes deleted individually via delete_note
                        assert mock_delete_note.call_count == 2
                        mock_delete_note.assert_any_call("note1", "nb_id")
                        mock_delete_note.assert_any_call("note2", "nb_id")
                        # Regular sources sent as a single batch
                        mock_rpc.assert_called_once()
                        args = mock_rpc.call_args[0]
                        assert args[0] == NotebookLMClient.RPC_DELETE_SOURCE
                        assert args[1] == [[["src1"]], [2]]
                        assert result is True

    def test_delete_sources_batch_no_notebook_id_uses_legacy(self):
        """Backward compat: no notebook_id → single batched tGMBJ call."""
        from notebooklm_tools.core.client import NotebookLMClient

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                mock_rpc.return_value = []
                client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                result = client.delete_sources(["a", "b", "c"])

                mock_rpc.assert_called_once()
                args = mock_rpc.call_args[0]
                assert args[0] == NotebookLMClient.RPC_DELETE_SOURCE
                assert args[1] == [[["a"], ["b"], ["c"]], [2]]
                assert result is True


class TestRenameSourceRouting:
    """Type-aware routing for rename_source.

    Generated_text sources are NotebookLM 'Note' objects and require
    RPC cYAfTb (update_note title-only) instead of b7Wfje (rename_source).
    """

    def test_rename_source_routes_generated_text_to_update_note(self):
        from notebooklm_tools.core.client import NotebookLMClient
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "update_note") as mock_update:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_update.return_value = {
                        "id": "note_id",
                        "title": "New Title",
                        "content": "old body",
                    }
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.rename_source(
                        "nb_id",
                        "note_id",
                        "New Title",
                        source_type=SOURCE_TYPE_GENERATED_TEXT,
                    )

                    mock_update.assert_called_once_with(
                        "note_id", title="New Title", notebook_id="nb_id"
                    )
                    mock_rpc.assert_not_called()
                    assert result == {"id": "note_id", "title": "New Title"}

    def test_rename_source_regular_uses_b7wfje(self):
        from notebooklm_tools.core.client import NotebookLMClient
        from notebooklm_tools.core.constants import SOURCE_TYPE_PASTED_TEXT

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "update_note") as mock_update:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_rpc.return_value = [[["src_id"], "Renamed"]]
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.rename_source(
                        "nb_id",
                        "src_id",
                        "Renamed",
                        source_type=SOURCE_TYPE_PASTED_TEXT,
                    )

                    mock_update.assert_not_called()
                    mock_rpc.assert_called_once()
                    args = mock_rpc.call_args[0]
                    assert args[0] == NotebookLMClient.RPC_RENAME_SOURCE
                    assert result == {"id": "src_id", "title": "Renamed"}

    def test_rename_source_no_source_type_uses_legacy(self):
        """Backward compat: no source_type → legacy b7Wfje."""
        from notebooklm_tools.core.client import NotebookLMClient

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "update_note") as mock_update:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_rpc.return_value = [[["src_id"], "T"]]
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    client.rename_source("nb_id", "src_id", "T")

                    mock_update.assert_not_called()
                    mock_rpc.assert_called_once()


class TestGetSourceGuideRouting:
    """Type-aware routing for get_source_guide. Note fallback returns
    list_notes content as the 'summary' (no per-note summary RPC exists)."""

    def test_get_source_guide_routes_generated_text_to_list_notes(self):
        from notebooklm_tools.core.client import NotebookLMClient
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "list_notes") as mock_list:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_list.return_value = [
                        {"id": "other_id", "title": "Other", "content": "x"},
                        {"id": "note_id", "title": "Note", "content": "Note body."},
                    ]
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.get_source_guide(
                        "note_id",
                        notebook_id="nb_id",
                        source_type=SOURCE_TYPE_GENERATED_TEXT,
                    )

                    mock_list.assert_called_once_with("nb_id")
                    mock_rpc.assert_not_called()
                    assert result == {"summary": "Note body.", "keywords": []}

    def test_get_source_guide_regular_uses_tr032e(self):
        from notebooklm_tools.core.client import NotebookLMClient

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "list_notes") as mock_list:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_rpc.return_value = []
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    client.get_source_guide("src_id")

                    mock_list.assert_not_called()
                    mock_rpc.assert_called_once()
                    args = mock_rpc.call_args[0]
                    assert args[0] == NotebookLMClient.RPC_GET_SOURCE_GUIDE


class TestGetSourceFulltextRouting:
    """Type-aware routing for get_source_fulltext. Note fallback extracts
    body from list_notes (cFji9 already returns it)."""

    def test_get_source_fulltext_routes_generated_text_to_list_notes(self):
        from notebooklm_tools.core.client import NotebookLMClient
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "list_notes") as mock_list:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_list.return_value = [
                        {"id": "note_id", "title": "T", "content": "Hello world."},
                    ]
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    result = client.get_source_fulltext(
                        "note_id",
                        notebook_id="nb_id",
                        source_type=SOURCE_TYPE_GENERATED_TEXT,
                    )

                    mock_list.assert_called_once_with("nb_id")
                    mock_rpc.assert_not_called()
                    assert result == {
                        "content": "Hello world.",
                        "title": "T",
                        "source_type": "generated_text",
                        "url": None,
                        "char_count": 12,
                    }

    def test_get_source_fulltext_regular_uses_hizojc(self):
        from notebooklm_tools.core.client import NotebookLMClient

        with patch.object(NotebookLMClient, "_refresh_auth_tokens"):  # noqa: SIM117
            with patch.object(NotebookLMClient, "list_notes") as mock_list:
                with patch.object(NotebookLMClient, "_call_rpc") as mock_rpc:
                    mock_rpc.return_value = []
                    client = NotebookLMClient(cookies={"t": "c"}, csrf_token="t")

                    client.get_source_fulltext("src_id")

                    mock_list.assert_not_called()
                    mock_rpc.assert_called_once()
                    args = mock_rpc.call_args[0]
                    assert args[0] == NotebookLMClient.RPC_GET_SOURCE


def test_is_note_type_helper():
    """_is_note_type centralizes the Note vs Source distinction."""
    from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT, SOURCE_TYPE_PASTED_TEXT
    from notebooklm_tools.core.sources import _is_note_type

    assert _is_note_type(SOURCE_TYPE_GENERATED_TEXT) is True
    assert _is_note_type(SOURCE_TYPE_PASTED_TEXT) is False
    assert _is_note_type(None) is False
    assert _is_note_type(0) is False


# ---------------------------------------------------------------------------
# Batch 1: get_source_fulltext markdown parser helpers
# ---------------------------------------------------------------------------


class TestGetSourceFulltextMarkdownParser:
    """Pure module-level parser helpers for hizoJc RPC tree → markdown.

    Covers every transformation rule fixture-driven: paragraph flag 4/5/6
    → H1/H2/H3, bullet meta 104 → dynamic indent, segment format flags
    0/1/7 → bold/italic/inline-code, and 2×2 table reconstruction.
    """

    @pytest.fixture(scope="class")
    def fixture_data(self) -> dict:
        import json
        from pathlib import Path

        path = Path(__file__).parent.parent / "fixtures" / "source_fulltext_2kb.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def unit_cases(self, fixture_data: dict) -> dict:
        return fixture_data["unit_cases"]

    def test_parse_segment_plain(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_segment

        case = unit_cases["segment_plain"]
        assert _parse_segment(case["input"]) == case["expected"]

    def test_parse_segment_bold(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_segment

        case = unit_cases["segment_bold"]
        assert _parse_segment(case["input"]) == case["expected"]

    def test_parse_segment_italic_asterisk(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_segment

        case = unit_cases["segment_italic_asterisk"]
        result = _parse_segment(case["input"])
        assert result == case["expected"]
        # Obsidian underscore-conflict avoidance
        assert "_" not in result.replace(case["input"][2][0], "")

    def test_parse_segment_inline_code(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_segment

        case = unit_cases["segment_inline_code"]
        assert _parse_segment(case["input"]) == case["expected"]

    def test_parse_segment_bold_inline_code(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_segment

        case = unit_cases["segment_bold_inline_code"]
        assert _parse_segment(case["input"]) == case["expected"]

    def test_parse_paragraph_h1_h2_h3(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_paragraph

        for key in ("paragraph_h1", "paragraph_h2", "paragraph_h3"):
            case = unit_cases[key]
            assert _parse_paragraph(case["input"]) == case["expected"], f"failed: {key}"

    def test_parse_paragraph_bullet_depth_0_1_2(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_paragraph

        for key in (
            "paragraph_bullet_depth_0",
            "paragraph_bullet_depth_1",
            "paragraph_bullet_depth_2",
        ):
            case = unit_cases[key]
            assert _parse_paragraph(case["input"]) == case["expected"], f"failed: {key}"

    def test_parse_paragraph_numbered_bullet(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_paragraph

        case = unit_cases["paragraph_numbered_bullet"]
        assert _parse_paragraph(case["input"]) == case["expected"]

    def test_parse_paragraph_unknown_flag_fallback(self, unit_cases, caplog):
        """Unknown paragraph flag (99) → plain text + logger.warning."""
        import logging

        from notebooklm_tools.core.sources import _parse_paragraph

        case = unit_cases["paragraph_unknown_flag_fallback"]
        with caplog.at_level(logging.WARNING, logger="notebooklm_tools.core.sources"):
            result = _parse_paragraph(case["input"])
        assert result == case["expected"]
        assert any(
            "unknown" in r.message.lower() or "99" in str(r.message)
            for r in caplog.records
        ), f"expected warning about unknown flag, got: {[r.message for r in caplog.records]}"

    def test_parse_table_basic(self, unit_cases):
        from notebooklm_tools.core.sources import _parse_table

        case = unit_cases["table_basic_2x2"]
        # block = [start, end, null, null, [cols, rows, cells]]
        table_data = case["input"][4]
        assert _parse_table(table_data) == case["expected"]

    def test_render_2kb_fixture_full(self, fixture_data):
        """Integration: 7 content blocks → full markdown matches anchor."""
        from notebooklm_tools.core.sources import _render_markdown_from_blocks

        blocks = fixture_data["integration_content_blocks"]
        expected = fixture_data["integration_expected_markdown"]
        assert _render_markdown_from_blocks(blocks) == expected
