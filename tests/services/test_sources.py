"""Tests for services.sources module."""

from unittest.mock import MagicMock

import pytest

from notebooklm_tools.services.errors import ServiceError, ValidationError
from notebooklm_tools.services.sources import (
    VALID_SOURCE_TYPES,
    add_source,
    add_sources,
    delete_source,
    delete_sources,
    describe_source,
    get_source_content,
    list_drive_sources,
    replace_source_file,
    resolve_drive_mime_type,
    sync_drive_sources,
    validate_source_type,
)


@pytest.fixture
def mock_client():
    client = MagicMock()
    # Add source methods
    client.add_url_source.return_value = {"id": "src-1", "title": "Example Page"}
    client.add_text_source.return_value = {"id": "src-2", "title": "My Text"}
    client.add_drive_source.return_value = {"id": "src-3", "title": "Drive Doc"}
    client.add_file.return_value = {"id": "src-4", "title": "doc.pdf"}
    # List/freshness methods
    client.get_notebook_sources_with_types.return_value = [
        {"id": "s1", "title": "Source 1", "source_type_name": "URL", "can_sync": False},
        {
            "id": "s2",
            "title": "Source 2",
            "source_type_name": "Drive",
            "can_sync": True,
            "drive_doc_id": "d1",
        },
    ]
    client.check_source_freshness.return_value = True
    # Sync/delete/describe/content
    client.sync_drive_source.return_value = True
    client.delete_source.return_value = True
    client.get_source_guide.return_value = {"summary": "Test summary", "keywords": ["a", "b"]}
    client.get_source_fulltext.return_value = {
        "content": "Hello world",
        "title": "Test Source",
        "source_type": "url",
        "url": None,
        "char_count": 11,
    }
    client.rename_source.return_value = {"id": "src-1", "title": "New Title"}
    return client


class TestValidateSourceType:
    """Test validate_source_type function."""

    @pytest.mark.parametrize("source_type", VALID_SOURCE_TYPES)
    def test_valid_types_pass(self, source_type):
        validate_source_type(source_type)  # should not raise

    def test_invalid_type_raises(self):
        with pytest.raises(ValidationError, match="Unknown source type"):
            validate_source_type("podcast")


class TestResolveDriveMimeType:
    """Test resolve_drive_mime_type function."""

    def test_doc(self):
        assert resolve_drive_mime_type("doc") == "application/vnd.google-apps.document"

    def test_slides(self):
        assert resolve_drive_mime_type("slides") == "application/vnd.google-apps.presentation"

    def test_sheets(self):
        assert resolve_drive_mime_type("sheets") == "application/vnd.google-apps.spreadsheet"

    def test_pdf(self):
        assert resolve_drive_mime_type("pdf") == "application/pdf"

    def test_unknown_defaults_to_doc(self):
        assert resolve_drive_mime_type("unknown") == "application/vnd.google-apps.document"


class TestAddSource:
    """Test add_source function."""

    def test_add_url_source(self, mock_client):
        result = add_source(mock_client, "nb-1", "url", url="https://example.com")
        assert result["source_type"] == "url"
        assert result["source_id"] == "src-1"
        assert result["title"] == "Example Page"

    def test_add_text_source(self, mock_client):
        result = add_source(mock_client, "nb-1", "text", text="some content")
        assert result["source_type"] == "text"
        assert result["source_id"] == "src-2"

    def test_add_text_source_default_title(self, mock_client):
        add_source(mock_client, "nb-1", "text", text="content")
        mock_client.add_text_source.assert_called_once_with(
            "nb-1",
            "content",
            "Pasted Text",
            wait=False,
            wait_timeout=120.0,
        )

    def test_add_drive_source(self, mock_client):
        result = add_source(mock_client, "nb-1", "drive", document_id="doc-123")
        assert result["source_type"] == "drive"
        assert result["source_id"] == "src-3"

    def test_add_drive_source_mime_type(self, mock_client):
        add_source(mock_client, "nb-1", "drive", document_id="d1", doc_type="slides")
        call_args = mock_client.add_drive_source.call_args
        assert call_args[0][3] == "application/vnd.google-apps.presentation"

    def test_add_file_source(self, mock_client):
        result = add_source(mock_client, "nb-1", "file", file_path="/tmp/doc.pdf")
        assert result["source_type"] == "file"
        assert result["source_id"] == "src-4"

    def test_invalid_source_type(self, mock_client):
        with pytest.raises(ValidationError, match="Unknown source type"):
            add_source(mock_client, "nb-1", "podcast")

    def test_url_missing_raises(self, mock_client):
        with pytest.raises(ValidationError, match="url is required"):
            add_source(mock_client, "nb-1", "url")

    def test_text_missing_raises(self, mock_client):
        with pytest.raises(ValidationError, match="text is required"):
            add_source(mock_client, "nb-1", "text")

    def test_drive_missing_document_id_raises(self, mock_client):
        with pytest.raises(ValidationError, match="document_id is required"):
            add_source(mock_client, "nb-1", "drive")

    def test_file_missing_path_raises(self, mock_client):
        with pytest.raises(ValidationError, match="file_path is required"):
            add_source(mock_client, "nb-1", "file")

    def test_api_error_wraps_in_service_error(self, mock_client):
        mock_client.add_url_source.side_effect = RuntimeError("boom")
        with pytest.raises(ServiceError, match="Failed to add"):
            add_source(mock_client, "nb-1", "url", url="https://example.com")

    def test_no_id_returned_raises_service_error(self, mock_client):
        mock_client.add_url_source.return_value = {}
        with pytest.raises(ServiceError, match="no ID returned"):
            add_source(mock_client, "nb-1", "url", url="https://example.com")

    def test_wait_forwarded(self, mock_client):
        add_source(mock_client, "nb-1", "url", url="http://ex.com", wait=True, wait_timeout=60)
        mock_client.add_url_source.assert_called_once_with(
            "nb-1",
            "http://ex.com",
            wait=True,
            wait_timeout=60,
        )

    # --- 폴더태그 재생성 / bare 고착 차단 (세션486, 신드리 ●●● + NLM ●●●) -------

    def test_file_bare_dup_title_regenerates_folder_tag(self, mock_client, tmp_path):
        """replace가 넘긴 bare `SKILL.md`(title==basename) → 폴더태그 재생성.

        옛 `if not title:` 관문은 truthy bare title을 우회시켜 자기고착했다.
        확장 조건 `title.strip() == _p.name`이 그 회로를 끊는다.
        """
        fp = tmp_path / "SKILL.md"
        mock_client.add_file.return_value = {"id": "src-4", "title": "SKILL.md"}

        result = add_source(mock_client, "nb-1", "file", file_path=str(fp), title="SKILL.md")

        expected = f"SKILL.md ({fp.parent.name})"
        # rename RPC가 재생성된 폴더태그로 호출됨
        assert mock_client.rename_source.call_args[0][2] == expected
        assert result["title"] == expected

    def test_file_folder_tag_title_preserved(self, mock_client, tmp_path):
        """이미 폴더태그인 title(`SKILL.md (two_step_solver)`)은 재생성 스킵 → preserve."""
        fp = tmp_path / "SKILL.md"
        mock_client.add_file.return_value = {"id": "src-4", "title": "SKILL.md (two_step_solver)"}

        add_source(
            mock_client, "nb-1", "file", file_path=str(fp), title="SKILL.md (two_step_solver)"
        )

        # 재생성되지 않고 원본 폴더태그 그대로 rename
        assert mock_client.rename_source.call_args[0][2] == "SKILL.md (two_step_solver)"

    def test_file_rename_falsy_sets_flag(self, mock_client, tmp_path):
        """rename_source falsy 반환 → title_rename_failed 플래그 (무음 삼킴 방지)."""
        fp = tmp_path / "SKILL.md"
        mock_client.add_file.return_value = {"id": "src-4", "title": "SKILL.md"}
        mock_client.rename_source.return_value = None  # falsy

        result = add_source(mock_client, "nb-1", "file", file_path=str(fp), title="SKILL.md")

        assert result.get("title_rename_failed") is True

    def test_file_rename_exception_sets_flag_no_crash(self, mock_client, tmp_path):
        """rename_source 예외 → main 흐름 계속 + title_rename_failed 플래그 (best-effort)."""
        fp = tmp_path / "SKILL.md"
        mock_client.add_file.return_value = {"id": "src-4", "title": "SKILL.md"}
        mock_client.rename_source.side_effect = RuntimeError("rename RPC boom")

        result = add_source(mock_client, "nb-1", "file", file_path=str(fp), title="SKILL.md")

        assert result["source_id"] == "src-4"  # 크래시 없이 반환
        assert result.get("title_rename_failed") is True

    def test_file_non_dup_name_not_regenerated(self, mock_client, tmp_path):
        """DUP_FILENAMES 외 파일명은 재생성 미발동 + 성공 경로엔 플래그 부재."""
        fp = tmp_path / "doc.pdf"
        mock_client.add_file.return_value = {"id": "src-4", "title": "doc.pdf"}

        result = add_source(mock_client, "nb-1", "file", file_path=str(fp))

        # title 미지정 + DUP 외 → rename 미호출, 플래그 없음
        mock_client.rename_source.assert_not_called()
        assert "title_rename_failed" not in result


class TestListDriveSources:
    """Test list_drive_sources function."""

    def test_returns_categorized_sources(self, mock_client):
        result = list_drive_sources(mock_client, "nb-1")
        assert result["drive_count"] == 1
        assert len(result["other_sources"]) == 1
        assert result["drive_sources"][0]["id"] == "s2"

    def test_stale_count(self, mock_client):
        mock_client.check_source_freshness.return_value = False
        result = list_drive_sources(mock_client, "nb-1")
        assert result["stale_count"] == 1
        assert result["drive_sources"][0]["stale"] is True

    def test_fresh_sources(self, mock_client):
        result = list_drive_sources(mock_client, "nb-1")
        assert result["stale_count"] == 0
        assert result["drive_sources"][0]["stale"] is False

    def test_api_error(self, mock_client):
        mock_client.get_notebook_sources_with_types.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to list"):
            list_drive_sources(mock_client, "nb-1")


class TestSyncDriveSources:
    """Test sync_drive_sources function."""

    def test_sync_success(self, mock_client):
        results = sync_drive_sources(mock_client, ["s1", "s2"])
        assert len(results) == 2
        assert all(r["synced"] for r in results)

    def test_sync_partial_failure(self, mock_client):
        mock_client.sync_drive_source.side_effect = [True, RuntimeError("fail")]
        results = sync_drive_sources(mock_client, ["s1", "s2"])
        assert results[0]["synced"] is True
        assert results[1]["synced"] is False
        assert results[1]["error"] == "fail"

    def test_empty_list_raises(self, mock_client):
        with pytest.raises(ValidationError, match="No source IDs"):
            sync_drive_sources(mock_client, [])


class TestDeleteSource:
    """Test delete_source function."""

    def test_success(self, mock_client):
        delete_source(mock_client, "src-1")
        mock_client.delete_source.assert_called_once_with(
            "src-1", notebook_id=None, source_type=None
        )

    def test_falsy_result_raises(self, mock_client):
        mock_client.delete_source.return_value = False
        with pytest.raises(ServiceError, match="Delete returned falsy"):
            delete_source(mock_client, "src-1")

    def test_api_error(self, mock_client):
        mock_client.delete_source.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to delete"):
            delete_source(mock_client, "src-1")


class TestDescribeSource:
    """Test describe_source function."""

    def test_success(self, mock_client):
        result = describe_source(mock_client, "src-1")
        assert result["summary"] == "Test summary"
        assert result["keywords"] == ["a", "b"]

    def test_empty_result_raises(self, mock_client):
        mock_client.get_source_guide.return_value = None
        with pytest.raises(ServiceError, match="No description returned"):
            describe_source(mock_client, "src-1")


class TestGetSourceContent:
    """Test get_source_content function."""

    def test_success(self, mock_client):
        result = get_source_content(mock_client, "src-1")
        assert result["content"] == "Hello world"
        assert result["title"] == "Test Source"
        assert result["source_type"] == "url"
        assert result["char_count"] == 11

    def test_empty_result_raises(self, mock_client):
        mock_client.get_source_fulltext.return_value = None
        with pytest.raises(ServiceError, match="No content returned"):
            get_source_content(mock_client, "src-1")


class TestAddSources:
    """Test add_sources (bulk) function."""

    def test_batch_url_sources(self, mock_client):
        mock_client.add_url_sources.return_value = [
            {"id": "s1", "title": "Example"},
            {"id": "s2", "title": "Example Org"},
        ]
        result = add_sources(
            mock_client,
            "nb-1",
            [
                {"source_type": "url", "url": "https://example.com"},
                {"source_type": "url", "url": "https://example.org"},
            ],
        )
        assert result["added_count"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["source_id"] == "s1"
        assert result["results"][1]["source_id"] == "s2"
        # Should call batch method once, not individual add_url_source
        mock_client.add_url_sources.assert_called_once()
        mock_client.add_url_source.assert_not_called()

    def test_mixed_types_batches_urls(self, mock_client):
        """URL sources are batched; text sources fall back to individual calls."""
        mock_client.add_url_sources.return_value = [
            {"id": "s1", "title": "Example"},
        ]
        result = add_sources(
            mock_client,
            "nb-1",
            [
                {"source_type": "url", "url": "https://example.com"},
                {"source_type": "text", "text": "hello world"},
            ],
        )
        assert result["added_count"] == 2
        mock_client.add_url_sources.assert_called_once()
        mock_client.add_text_source.assert_called_once()

    def test_empty_list_raises(self, mock_client):
        with pytest.raises(ValidationError, match="No sources provided"):
            add_sources(mock_client, "nb-1", [])

    def test_invalid_source_type_raises(self, mock_client):
        with pytest.raises(ValidationError, match="Unknown source type"):
            add_sources(
                mock_client,
                "nb-1",
                [
                    {"source_type": "podcast", "url": "https://example.com"},
                ],
            )

    def test_url_missing_raises(self, mock_client):
        with pytest.raises(ValidationError, match="url is required"):
            add_sources(
                mock_client,
                "nb-1",
                [
                    {"source_type": "url"},
                ],
            )

    def test_batch_no_id_raises_service_error(self, mock_client):
        mock_client.add_url_sources.return_value = [{}]
        with pytest.raises(ServiceError, match="no ID returned"):
            add_sources(
                mock_client,
                "nb-1",
                [
                    {"source_type": "url", "url": "https://example.com"},
                ],
            )

    def test_batch_api_error_wraps(self, mock_client):
        mock_client.add_url_sources.side_effect = RuntimeError("boom")
        with pytest.raises(ServiceError, match="Failed to batch-add"):
            add_sources(
                mock_client,
                "nb-1",
                [
                    {"source_type": "url", "url": "https://example.com"},
                ],
            )

    def test_wait_forwarded(self, mock_client):
        mock_client.add_url_sources.return_value = [
            {"id": "s1", "title": "Example"},
        ]
        add_sources(
            mock_client,
            "nb-1",
            [
                {"source_type": "url", "url": "https://example.com"},
            ],
            wait=True,
            wait_timeout=60,
        )
        mock_client.add_url_sources.assert_called_once_with(
            "nb-1",
            ["https://example.com"],
            wait=True,
            wait_timeout=60,
        )


class TestDeleteSources:
    """Test delete_sources (bulk) function."""

    def test_batch_delete(self, mock_client):
        mock_client.delete_sources.return_value = True
        delete_sources(mock_client, ["s1", "s2", "s3"])
        mock_client.delete_sources.assert_called_once_with(
            ["s1", "s2", "s3"], notebook_id=None
        )

    def test_empty_list_raises(self, mock_client):
        with pytest.raises(ValidationError, match="No source IDs"):
            delete_sources(mock_client, [])

    def test_falsy_result_raises(self, mock_client):
        mock_client.delete_sources.return_value = False
        with pytest.raises(ServiceError, match="Bulk delete returned falsy"):
            delete_sources(mock_client, ["s1"])

    def test_api_error(self, mock_client):
        mock_client.delete_sources.side_effect = RuntimeError("fail")
        with pytest.raises(ServiceError, match="Failed to delete"):
            delete_sources(mock_client, ["s1"])


# ──────────────────────────────────────────────────────────────────────────
# v3: Source-Note 조회·수정 도메인 불일치 — 자동 type 조회 + fallback
# ──────────────────────────────────────────────────────────────────────────


def _client_with(sources=None, notes=None):
    """Build a MagicMock with predictable list/notes for v3 routing tests."""
    client = MagicMock()
    client.get_notebook_sources_with_types.return_value = sources or []
    client.list_notes.return_value = notes or []
    return client


class TestResolveSourceType:
    def test_returns_none_without_notebook_id(self):
        from notebooklm_tools.services.sources import _resolve_source_type

        client = _client_with()
        assert _resolve_source_type(client, None, "any") is None
        client.get_notebook_sources_with_types.assert_not_called()
        client.list_notes.assert_not_called()

    def test_ignores_sources_meta_source_type(self):
        """v3 회귀 픽스 (세션310): get_notebook의 metadata[4]가 모든 text source에서
        SOURCE_TYPE_GENERATED_TEXT(=8)와 우연 일치 → sources_meta의 source_type 신뢰 폐기.
        list_notes에 없으면 None 반환 (일반 RPC 라우팅).
        """
        from notebooklm_tools.services.sources import _resolve_source_type

        # sources_meta가 source_type=8을 응답해도 무시 (회귀 진단 결과)
        client = _client_with(
            sources=[{"id": "src1", "source_type": 8}],
            notes=[],
        )
        assert _resolve_source_type(client, "nb", "src1") is None

    def test_finds_in_notes_with_content(self):
        """list_notes 멤버십 + content 키 둘 다 매칭 시 generated_text 반환."""
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT
        from notebooklm_tools.services.sources import _resolve_source_type

        client = _client_with(sources=[], notes=[{"id": "note1", "content": "body"}])
        assert _resolve_source_type(client, "nb", "note1") == SOURCE_TYPE_GENERATED_TEXT

    def test_returns_none_when_note_lacks_content(self):
        """content 키 없는 note 항목은 매칭 제외 (mind_map JSON·deleted 필터링)."""
        from notebooklm_tools.services.sources import _resolve_source_type

        client = _client_with(sources=[], notes=[{"id": "note1"}])
        assert _resolve_source_type(client, "nb", "note1") is None

    def test_returns_none_when_not_found(self):
        from notebooklm_tools.services.sources import _resolve_source_type

        client = _client_with(sources=[{"id": "other"}], notes=[{"id": "another", "content": "x"}])
        assert _resolve_source_type(client, "nb", "missing") is None

    def test_swallows_list_notes_error(self):
        """list_notes lookup 에러 시 None 반환 (일반 RPC 라우팅으로 안전 fallback)."""
        from notebooklm_tools.services.sources import _resolve_source_type

        client = MagicMock()
        client.list_notes.side_effect = RuntimeError("boom")
        assert _resolve_source_type(client, "nb", "note1") is None


class TestDescribeSourceRouting:
    def test_passes_resolved_type_to_client(self):
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT

        client = _client_with(sources=[], notes=[{"id": "note1", "content": "body"}])
        client.get_source_guide.return_value = {"summary": "S", "keywords": ["k"]}

        result = describe_source(client, "note1", notebook_id="nb")

        client.get_source_guide.assert_called_once_with(
            "note1", notebook_id="nb", source_type=SOURCE_TYPE_GENERATED_TEXT
        )
        assert result == {"summary": "S", "keywords": ["k"]}

    def test_no_notebook_id_passes_through(self):
        client = MagicMock()
        client.get_source_guide.return_value = {"summary": "S", "keywords": []}

        describe_source(client, "src_id")

        client.get_source_guide.assert_called_once_with(
            "src_id", notebook_id=None, source_type=None
        )
        client.get_notebook_sources_with_types.assert_not_called()
        client.list_notes.assert_not_called()


class TestGetSourceContentRouting:
    def test_passes_resolved_type_to_client(self):
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT

        client = _client_with(sources=[], notes=[{"id": "note1", "content": "body"}])
        client.get_source_fulltext.return_value = {
            "content": "body",
            "title": "T",
            "source_type": "generated_text",
            "url": None,
            "char_count": 4,
        }

        result = get_source_content(client, "note1", notebook_id="nb")

        client.get_source_fulltext.assert_called_once_with(
            "note1", notebook_id="nb", source_type=SOURCE_TYPE_GENERATED_TEXT
        )
        assert result["content"] == "body"
        assert result["source_type"] == "generated_text"
        assert result["char_count"] == 4

    def test_no_notebook_id_passes_through(self):
        client = MagicMock()
        client.get_source_fulltext.return_value = {
            "content": "body",
            "title": "T",
            "source_type": "web_page",
            "url": None,
            "char_count": 4,
        }

        get_source_content(client, "src_id")

        client.get_source_fulltext.assert_called_once_with(
            "src_id", notebook_id=None, source_type=None
        )


class TestRenameSourceRouting:
    def test_passes_resolved_type_to_client(self):
        from notebooklm_tools.core.constants import SOURCE_TYPE_GENERATED_TEXT
        from notebooklm_tools.services.sources import rename_source as svc_rename

        client = _client_with(sources=[], notes=[{"id": "note1", "content": "body"}])
        client.rename_source.return_value = {"id": "note1", "title": "New"}

        result = svc_rename(client, "nb", "note1", "New")

        client.rename_source.assert_called_once_with(
            "nb", "note1", "New", source_type=SOURCE_TYPE_GENERATED_TEXT
        )
        assert result == {"source_id": "note1", "title": "New"}

    def test_regular_source_passes_through(self):
        """v3 회귀 픽스 (세션310): 일반 source는 list_notes에 없으므로 source_type=None으로
        client.rename_source 위임 → 일반 RPC b7Wfje 사용. sources_meta source_type 신뢰 폐기.
        """
        from notebooklm_tools.services.sources import rename_source as svc_rename

        client = _client_with(sources=[{"id": "src1", "source_type": 8}], notes=[])
        client.rename_source.return_value = {"id": "src1", "title": "New"}

        svc_rename(client, "nb", "src1", "New")

        client.rename_source.assert_called_once_with(
            "nb", "src1", "New", source_type=None
        )


class TestReplaceSourceFile:
    """Test replace_source_file service function."""

    def test_legacy_delete_then_add_order(self, mock_client, tmp_path):
        """atomic=False (legacy opt-out) → delete-first 순서 유지 (회귀 가드)."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("hello world")

        # No matching source for title preservation
        mock_client.get_notebook_sources_with_types.return_value = []

        # Track call order
        call_order = []
        mock_client.delete_source.side_effect = lambda *a, **kw: (
            call_order.append("delete") or True
        )
        mock_client.add_file.side_effect = lambda *a, **kw: (
            call_order.append("add") or {"id": "src-new", "title": "doc.txt"}
        )

        result = replace_source_file(
            mock_client, "nb-1", str(file_path), source_id="src-old", atomic=False
        )

        assert call_order == ["delete", "add"]
        assert result["notebook_id"] == "nb-1"
        assert result["old_source_id"] == "src-old"
        assert result["new_source_id"] == "src-new"
        assert result["title"] == "doc.txt"
        assert "Replaced" in result["message"]

    def test_title_preserved_from_existing_source(self, mock_client, tmp_path):
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "src-old", "title": "Original Title", "source_type_name": "Text"},
        ]
        # Track that add_file was called with the preserved title metadata
        mock_client.add_file.return_value = {"id": "src-new", "title": "Original Title"}

        result = replace_source_file(mock_client, "nb-1", str(file_path), source_id="src-old")

        assert result["title"] == "Original Title"

    # --- source_id auto-match (session 418, NLM ●●● conv 803fdca1) ---------

    def test_auto_match_by_basename_exact(self, mock_client, tmp_path):
        """source_id 생략 → title==basename 정확일치로 자동 해소 (UUID 전사 제거)."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "src-other", "title": "other.txt", "source_type_name": "Text"},
            {"id": "src-match", "title": "doc.txt", "source_type_name": "Text"},
        ]
        mock_client.add_file.return_value = {"id": "src-new", "title": "doc.txt"}

        result = replace_source_file(mock_client, "nb-1", str(file_path))

        assert result["old_source_id"] == "src-match"
        assert result["new_source_id"] == "src-new"

    def test_auto_match_by_basename_prefix_folder_tag(self, mock_client, tmp_path):
        """보강일치 — NLM 자동 폴더태그 title(SKILL.md (two_step_solver))도 basename으로 매칭."""
        file_path = tmp_path / "SKILL.md"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "src-skill", "title": "SKILL.md (two_step_solver)", "source_type_name": "Text"},
        ]
        mock_client.add_file.return_value = {"id": "src-new", "title": "SKILL.md (two_step_solver)"}

        result = replace_source_file(mock_client, "nb-1", str(file_path))

        assert result["old_source_id"] == "src-skill"

    def test_replace_bare_stuck_source_regenerates_folder_tag(self, mock_client, tmp_path):
        """실 버그 재현 (세션486) — bare 고착 소스를 replace하면 폴더태그 재생성으로 자연 치유.

        옛 회로: 자동매칭 exact가 bare `SKILL.md`를 잡아 preserved_title=`SKILL.md`(truthy)를
        _do_add로 넘김 → 옛 `if not title:` 관문 우회 → add_file이 다시 bare → 영구 고착.
        """
        fp = tmp_path / "SKILL.md"
        fp.write_text("content")

        # NLM에 bare `SKILL.md`로 고착된 소스 (exact 매칭 대상)
        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "src-stuck", "title": "SKILL.md", "source_type_name": "Text"},
        ]
        mock_client.add_file.return_value = {"id": "src-new", "title": "SKILL.md"}

        result = replace_source_file(mock_client, "nb-1", str(fp))

        # 자동매칭이 bare 고착 소스를 해소하고
        assert result["old_source_id"] == "src-stuck"
        assert result["new_source_id"] == "src-new"
        # 재생성된 폴더태그로 rename RPC 발화 (치유 성립)
        expected = f"SKILL.md ({fp.parent.name})"
        assert mock_client.rename_source.call_args[0][2] == expected
        assert result["title"] == expected

    def test_auto_match_ambiguous_raises_before_delete(self, mock_client, tmp_path):
        """동일 basename 다수(ambiguous) → ValidationError, 파괴적 delete 미발동."""
        file_path = tmp_path / "README.md"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "r1", "title": "README.md", "source_type_name": "Text"},
            {"id": "r2", "title": "README.md", "source_type_name": "Text"},
        ]

        with pytest.raises(ValidationError, match="auto-match"):
            replace_source_file(mock_client, "nb-1", str(file_path))

        # Load-bearing: no destructive/add call when auto-match is ambiguous
        mock_client.delete_source.assert_not_called()
        mock_client.add_file.assert_not_called()

    def test_folder_hint_disambiguates_same_basename(self, mock_client, tmp_path):
        """Tier 1.5 (세션520) — N개 `SKILL.md (folder)` 중 파일 부모폴더명으로 유니크 해소."""
        skill_dir = tmp_path / "brokk-debate"
        skill_dir.mkdir()
        fp = skill_dir / "SKILL.md"
        fp.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "s-brokk", "title": "SKILL.md (brokk-debate)", "source_type_name": "Text"},
            {"id": "s-roul", "title": "SKILL.md (suno-lyric-roulette)", "source_type_name": "Text"},
            {"id": "s-cross", "title": "SKILL.md (cross_3step_solver)", "source_type_name": "Text"},
        ]
        mock_client.add_file.return_value = {"id": "s-new", "title": "SKILL.md (brokk-debate)"}

        result = replace_source_file(mock_client, "nb-1", str(fp))

        # 폴더힌트로 유니크 해소 — ambiguous 미발생, 정확한 소스만 교체
        assert result["old_source_id"] == "s-brokk"
        mock_client.delete_source.assert_called_once()

    def test_folder_hint_no_match_falls_to_prefix_ambiguous(self, mock_client, tmp_path):
        """폴더힌트가 어느 title과도 안 맞으면 prefix tier로 폴백 — 다수면 여전히 fail-close."""
        skill_dir = tmp_path / "unknown-skill"
        skill_dir.mkdir()
        fp = skill_dir / "SKILL.md"
        fp.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "s1", "title": "SKILL.md (brokk-debate)", "source_type_name": "Text"},
            {"id": "s2", "title": "SKILL.md (suno-lyric-roulette)", "source_type_name": "Text"},
        ]

        with pytest.raises(ValidationError, match="auto-match"):
            replace_source_file(mock_client, "nb-1", str(fp))

        mock_client.delete_source.assert_not_called()

    def test_auto_match_fetch_failure_raises_service_error(self, mock_client, tmp_path):
        """source_id=None인데 소스목록 조회 실패 → 묵음실패 금지, ServiceError (함정1)."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.side_effect = RuntimeError("network down")

        with pytest.raises(ServiceError, match="auto-match"):
            replace_source_file(mock_client, "nb-1", str(file_path))

        # Load-bearing: unresolved source must never reach the destructive path
        mock_client.delete_source.assert_not_called()
        mock_client.add_file.assert_not_called()

    @pytest.mark.parametrize(
        "scenario",
        ["missing", "directory", "empty", "unsupported_ext"],
    )
    def test_pre_check_failure_skips_destructive_delete(
        self, mock_client, tmp_path, scenario
    ):
        if scenario == "missing":
            bad_path = tmp_path / "ghost.txt"  # never created
        elif scenario == "directory":
            bad_path = tmp_path / "a_dir"
            bad_path.mkdir()
        elif scenario == "empty":
            bad_path = tmp_path / "empty.txt"
            bad_path.write_text("")
        else:  # unsupported_ext
            bad_path = tmp_path / "weird.xyz"
            bad_path.write_text("content")

        with pytest.raises(ValidationError):
            replace_source_file(mock_client, "nb-1", str(bad_path), source_id="src-old")

        # Load-bearing: delete must NEVER fire when pre-check fails
        mock_client.delete_source.assert_not_called()
        mock_client.add_file.assert_not_called()

    def test_delete_success_add_failure_surfaces_explicitly(self, mock_client, tmp_path):
        """legacy(atomic=False) delete 성공 + add 실패 → 원본 소실 명시 에러."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = []
        mock_client.delete_source.return_value = True
        mock_client.add_file.side_effect = RuntimeError("upload network error")

        with pytest.raises(ServiceError, match="delete succeeded but add failed"):
            replace_source_file(
                mock_client, "nb-1", str(file_path), source_id="src-old", atomic=False
            )

        # delete was called exactly once before the add failure
        assert mock_client.delete_source.call_count == 1

    # ──────────────────────────────────────────────────────────────────────
    # v6 중기 ①: fallback_to_text 옵션 (미지원 확장자 자동 text 폴백)
    # ──────────────────────────────────────────────────────────────────────

    def test_unsupported_ext_with_fallback_succeeds(self, mock_client, tmp_path):
        """`.json` + fallback_to_text=True → text-mode upload + mode='text'."""
        file_path = tmp_path / "settings.json"
        file_path.write_text('{"key": "value"}', encoding="utf-8")

        mock_client.get_notebook_sources_with_types.return_value = []
        mock_client.add_text_source.return_value = {"id": "src-new", "title": "settings.json"}

        result = replace_source_file(
            mock_client, "nb-1", str(file_path), source_id="src-old", fallback_to_text=True
        )

        # add_text_source was called with the file contents
        mock_client.add_text_source.assert_called_once()
        call_args = mock_client.add_text_source.call_args
        assert call_args[0][1] == '{"key": "value"}'  # text content
        # add_file must NOT be called when fallback fires
        mock_client.add_file.assert_not_called()

        assert result["mode"] == "text"
        assert result["new_source_id"] == "src-new"
        assert "fallback to text mode" in result["message"]

    def test_unsupported_ext_without_fallback_raises(self, mock_client, tmp_path):
        """`.json` + default fallback_to_text=False → ValidationError (호환 회귀 가드)."""
        file_path = tmp_path / "settings.json"
        file_path.write_text('{"key": "value"}', encoding="utf-8")

        with pytest.raises(ValidationError, match="Unsupported file type"):
            replace_source_file(mock_client, "nb-1", str(file_path), source_id="src-old")

        # Load-bearing: no destructive call when pre-check fails
        mock_client.delete_source.assert_not_called()
        mock_client.add_file.assert_not_called()
        mock_client.add_text_source.assert_not_called()

    def test_fallback_preserves_title(self, mock_client, tmp_path):
        """폴백 모드에서도 title preservation 동작 (regular file 경로와 일관)."""
        file_path = tmp_path / "core.py"
        file_path.write_text("def hello(): pass\n", encoding="utf-8")

        mock_client.get_notebook_sources_with_types.return_value = [
            {"id": "src-old", "title": "Original Core", "source_type_name": "Text"},
        ]
        mock_client.add_text_source.return_value = {
            "id": "src-new",
            "title": "Original Core",
        }

        result = replace_source_file(
            mock_client, "nb-1", str(file_path), source_id="src-old", fallback_to_text=True
        )

        # add_text_source called with preserved title (positional arg index 2)
        call_args = mock_client.add_text_source.call_args
        assert call_args[0][2] == "Original Core"
        assert result["title"] == "Original Core"
        assert result["mode"] == "text"

    def test_fallback_binary_decode_failure_skips_delete(self, mock_client, tmp_path):
        """폴백 모드 UTF-8 디코드 실패 → ValidationError + delete 미호출 (pre-delete 안전)."""
        bin_path = tmp_path / "weird.bin"
        bin_path.write_bytes(b"\xff\xfe\x00\x80\xff")  # invalid utf-8 bytes

        with pytest.raises(ValidationError, match="Cannot decode as UTF-8"):
            replace_source_file(
                mock_client, "nb-1", str(bin_path), source_id="src-old", fallback_to_text=True
            )

        # Load-bearing: utf-8 decode failure must surface before delete
        mock_client.delete_source.assert_not_called()
        mock_client.add_file.assert_not_called()
        mock_client.add_text_source.assert_not_called()

    def test_fallback_delete_success_add_text_failure_surfaces(self, mock_client, tmp_path):
        """legacy(atomic=False) 폴백 모드 delete 성공 + add_text 실패 → 명시적 ServiceError."""
        file_path = tmp_path / "settings.json"
        file_path.write_text('{"k": 1}', encoding="utf-8")

        mock_client.get_notebook_sources_with_types.return_value = []
        mock_client.delete_source.return_value = True
        mock_client.add_text_source.side_effect = RuntimeError("text upload failed")

        with pytest.raises(ServiceError, match="delete succeeded but add failed"):
            replace_source_file(
                mock_client, "nb-1", str(file_path), source_id="src-old",
                fallback_to_text=True, atomic=False,
            )

        # delete was called exactly once before the add_text failure
        assert mock_client.delete_source.call_count == 1

    # ──────────────────────────────────────────────────────────────────────
    # ATOM-1 (260515): atomic 옵션 (ADD-first → 분실 차단, opt-in trial)
    # ──────────────────────────────────────────────────────────────────────

    def test_atomic_uses_add_first_order(self, mock_client, tmp_path):
        """atomic=True → call_order == ['add', 'delete'] (반전 검증)."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = []

        call_order = []
        mock_client.add_file.side_effect = lambda *a, **kw: (
            call_order.append("add") or {"id": "src-new", "title": "doc.txt"}
        )
        mock_client.delete_source.side_effect = lambda *a, **kw: (
            call_order.append("delete") or True
        )

        result = replace_source_file(
            mock_client, "nb-1", str(file_path), source_id="src-old", atomic=True
        )

        assert call_order == ["add", "delete"]
        assert result["new_source_id"] == "src-new"
        assert "atomic" in result["message"]

    def test_atomic_add_failure_preserves_original(self, mock_client, tmp_path):
        """atomic=True + add 실패 → delete 호출 X + 옛 source 보존."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = []
        mock_client.add_file.side_effect = RuntimeError("upload network error")

        with pytest.raises(
            ServiceError, match="atomic.*add failed.*original source preserved"
        ):
            replace_source_file(
                mock_client, "nb-1", str(file_path), source_id="src-old", atomic=True
            )

        # Load-bearing: delete must NEVER fire when atomic add fails
        mock_client.delete_source.assert_not_called()

    def test_atomic_default_is_add_first(self, mock_client, tmp_path):
        """atomic 미지정 → default add-first 흐름 (v10 승격, Fail-close 회귀 가드)."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = []

        call_order = []
        mock_client.delete_source.side_effect = lambda *a, **kw: (
            call_order.append("delete") or True
        )
        mock_client.add_file.side_effect = lambda *a, **kw: (
            call_order.append("add") or {"id": "src-new", "title": "doc.txt"}
        )

        result = replace_source_file(mock_client, "nb-1", str(file_path), source_id="src-old")

        # Default promoted to ADD-first (data-loss defense)
        assert call_order == ["add", "delete"]
        assert "atomic" in result["message"]

    def test_atomic_add_success_delete_failure_surfaces(self, mock_client, tmp_path):
        """atomic=True + add 성공 + delete 실패 → 새 source 살아있음 + ServiceError."""
        file_path = tmp_path / "doc.txt"
        file_path.write_text("content")

        mock_client.get_notebook_sources_with_types.return_value = []
        mock_client.add_file.return_value = {"id": "src-new", "title": "doc.txt"}
        mock_client.delete_source.side_effect = RuntimeError("delete network error")

        with pytest.raises(
            ServiceError, match="atomic.*add succeeded but delete failed"
        ):
            replace_source_file(
                mock_client, "nb-1", str(file_path), source_id="src-old", atomic=True
            )

        # add was called once; delete was attempted (failed) — both sources
        # transiently present in the notebook
        mock_client.add_file.assert_called_once()
        mock_client.delete_source.assert_called_once()
