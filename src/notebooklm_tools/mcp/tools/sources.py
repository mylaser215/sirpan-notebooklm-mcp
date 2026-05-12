"""Source tools - Source management with consolidated source_add."""

from ...services import ServiceError, ValidationError
from ...services import sources as sources_service
from ._utils import ResultDict, coerce_list, error_result, get_client, logged_tool


def _normalize_source_validation_error(message: str) -> str:
    """Preserve historical MCP wire wording for invalid source_type."""
    if message.startswith("Unknown source type "):
        return message.replace("Unknown source type", "Unknown source_type", 1)
    return message


@logged_tool()
def source_add(
    notebook_id: str,
    source_type: str,
    url: str | None = None,
    urls: list[str] | None = None,
    text: str | None = None,
    title: str | None = None,
    file_path: str | None = None,
    document_id: str | None = None,
    doc_type: str = "doc",
    wait: bool = False,
    wait_timeout: float = 120.0,
) -> ResultDict:
    """Add a source to a notebook. Unified tool for all source types.

    Supports: url, text, drive, file

    Args:
        notebook_id: Notebook UUID
        source_type: Type of source to add:
            - url: Web page or YouTube URL
            - text: Pasted text content
            - drive: Google Drive document
            - file: Local file upload (PDF, text, audio)
        url: URL to add (for source_type=url)
        urls: List of URLs to add in bulk (for source_type=url, alternative to url)
        text: Text content to add (for source_type=text)
        title: Display title (for text sources)
        file_path: Local file path (for source_type=file)
        document_id: Google Drive document ID (for source_type=drive)
        doc_type: Drive doc type: doc|slides|sheets|pdf (for source_type=drive)
        wait: If True, wait for source processing to complete before returning
        wait_timeout: Max seconds to wait if wait=True (default 120)

    Example:
        source_add(notebook_id="abc", source_type="url", url="https://example.com")
        source_add(notebook_id="abc", source_type="url", urls=["https://a.com", "https://b.com"])
        source_add(notebook_id="abc", source_type="url", url="https://example.com", wait=True)
        source_add(notebook_id="abc", source_type="file", file_path="/path/to/doc.pdf", wait=True)
    """
    try:
        client = get_client()

        # Coerce list params from MCP clients (may arrive as strings)
        coerced_urls: list[str] | None = coerce_list(urls)

        # Bulk URL add: when urls list is provided
        if coerced_urls and source_type == "url":
            bulk_result = sources_service.add_sources(
                client,
                notebook_id,
                [{"source_type": "url", "url": url_value} for url_value in coerced_urls],
                wait=wait,
                wait_timeout=wait_timeout,
            )
            return {"status": "success", "ready": wait, **bulk_result}

        # Single source add (existing behavior)
        single_result = sources_service.add_source(
            client,
            notebook_id,
            source_type,
            url=url,
            text=text,
            title=title,
            file_path=file_path,
            document_id=document_id,
            doc_type=doc_type,
            wait=wait,
            wait_timeout=wait_timeout,
        )
        return {"status": "success", "ready": wait, **single_result}
    except ValidationError as e:
        return error_result(_normalize_source_validation_error(str(e)))
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_list_drive(notebook_id: str) -> ResultDict:
    """List sources with types and Drive freshness status.

    Use before source_sync_drive to identify stale sources.

    Args:
        notebook_id: Notebook UUID
    """
    try:
        client = get_client()
        result = sources_service.list_drive_sources(client, notebook_id)
        return {"status": "success", "notebook_id": notebook_id, **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_sync_drive(source_ids: list[str], confirm: bool = False) -> ResultDict:
    """Sync Drive sources with latest content. Requires confirm=True.

    Call source_list_drive first to identify stale sources.

    Args:
        source_ids: Source UUIDs to sync
        confirm: Must be True after user approval
    """
    if not confirm:
        return error_result(
            "Sync not confirmed. Set confirm=True after user approval.",
            hint="Call source_list_drive first to see which sources are stale.",
        )

    try:
        client = get_client()
        # Coerce list params from MCP clients (may arrive as strings)
        coerced_source_ids: list[str] | None = coerce_list(source_ids)
        if not coerced_source_ids:
            return error_result("source_ids is required.")
        sync_results = sources_service.sync_drive_sources(client, coerced_source_ids)
        synced_count = sum(1 for item in sync_results if item.get("synced"))
        return {
            "status": "success",
            "synced_count": synced_count,
            "total_count": len(coerced_source_ids),
            "results": sync_results,
        }
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_rename(notebook_id: str, source_id: str, new_title: str) -> ResultDict:
    """Rename a source in a notebook.

    Works for both regular Sources (Source RPC b7Wfje) and generated_text
    Notes (routed to update_note title-only RPC cYAfTb). Type is auto-detected
    from notebook_id.

    Args:
        notebook_id: Notebook UUID containing the source
        source_id: Source UUID to rename
        new_title: New display title for the source
    """
    try:
        client = get_client()
        result = sources_service.rename_source(client, notebook_id, source_id, new_title)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_delete(
    source_id: str | None = None,
    source_ids: list[str] | None = None,
    notebook_id: str | None = None,
    confirm: bool = False,
) -> ResultDict:
    """Delete source(s) permanently. IRREVERSIBLE. Requires confirm=True.

    For generated_text sources (saved AI responses, mind maps stored as
    notebook content), pass `notebook_id` so the call is routed to the
    correct backend RPC. Without notebook_id the legacy Source-only RPC is
    used and generated_text deletion will fail.

    Args:
        source_id: Source UUID to delete (single)
        source_ids: List of source UUIDs to delete (bulk, alternative to source_id)
        notebook_id: Optional notebook UUID — required for generated_text routing
        confirm: Must be True after user approval
    """
    if not confirm:
        return error_result(
            "Deletion not confirmed. Set confirm=True after user approval.",
            warning="This action is IRREVERSIBLE.",
        )

    try:
        client = get_client()

        # Coerce list params from MCP clients (may arrive as strings)
        coerced_source_ids: list[str] | None = coerce_list(source_ids)

        # Bulk delete: when source_ids list is provided
        if coerced_source_ids:
            sources_service.delete_sources(
                client, coerced_source_ids, notebook_id=notebook_id
            )
            return {
                "status": "success",
                "message": f"{len(coerced_source_ids)} sources have been permanently deleted.",
                "deleted_count": len(coerced_source_ids),
            }

        # Single delete (existing behavior)
        if not source_id:
            return error_result("Either source_id or source_ids is required.")

        sources_service.delete_source(client, source_id, notebook_id=notebook_id)
        return {
            "status": "success",
            "message": f"Source {source_id} has been permanently deleted.",
        }
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_replace_file(
    notebook_id: str,
    source_id: str,
    file_path: str,
    confirm: bool = False,
    fallback_to_text: bool = False,
) -> ResultDict:
    """Replace an existing source by deleting it and uploading a new local file.

    NLM has no in-place update RPC for file sources, so this is a
    delete + add transaction. The MCP server reads the file directly from
    disk — avoid round-tripping file contents through Claude.

    The source_id changes after replacement (NLM mints a new ID on add).
    Pre-checks file existence, regular-file status, non-empty size, and
    supported extension before the destructive delete so a missing/invalid
    file cannot orphan the source.

    When ``fallback_to_text=True``, unsupported extensions (e.g. ``.json``,
    ``.py``) are routed to a text-mode upload — the file contents are read
    as UTF-8 and uploaded as a text source. Default ``False`` preserves the
    strict-extension behavior. The response ``mode`` field reports which
    path was taken (``"file"`` or ``"text"``).

    Args:
        notebook_id: Notebook UUID containing the source
        source_id: Source UUID to replace
        file_path: Absolute path to the local file to upload
        confirm: Must be True after user approval (replace is destructive —
            the old source is deleted before the new file is uploaded)
        fallback_to_text: Opt-in — route unsupported extensions to a text
            upload (UTF-8 only). Default ``False``.
    """
    if not confirm:
        return error_result(
            "Replace not confirmed. Set confirm=True after user approval.",
            warning="The existing source will be deleted before the new file is uploaded.",
        )

    try:
        client = get_client()
        result = sources_service.replace_source_file(
            client,
            notebook_id,
            source_id,
            file_path,
            fallback_to_text=fallback_to_text,
        )
        return {"status": "success", **result}
    except ValidationError as e:
        return error_result(str(e), hint=e.hint)
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_describe(source_id: str, notebook_id: str | None = None) -> ResultDict:
    """Get AI-generated source summary with keyword chips.

    For generated_text sources (saved AI responses, mind maps stored as
    notebook content), pass `notebook_id` so the call is routed to the
    correct backend. Without notebook_id the legacy Source-only RPC is
    used and generated_text describe will fail.

    Args:
        source_id: Source UUID
        notebook_id: Optional notebook UUID — required for generated_text routing

    Returns: summary (markdown with **bold** keywords), keywords list
    """
    try:
        client = get_client()
        result = sources_service.describe_source(client, source_id, notebook_id=notebook_id)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def source_get_content(source_id: str, notebook_id: str | None = None) -> ResultDict:
    """Get raw text content of a source (no AI processing).

    Returns the original indexed text from PDFs, web pages, pasted text,
    or YouTube transcripts. Much faster than notebook_query for content export.

    For generated_text sources (saved AI responses), pass `notebook_id` so
    the call returns the note body directly. Without notebook_id the
    legacy Source-only RPC is used and generated_text content will fail.

    Args:
        source_id: Source UUID
        notebook_id: Optional notebook UUID — required for generated_text routing

    Returns: content (str), title (str), source_type (str), char_count (int)
    """
    try:
        client = get_client()
        result = sources_service.get_source_content(client, source_id, notebook_id=notebook_id)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))
