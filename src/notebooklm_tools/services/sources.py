"""Sources service — shared validation and logic for source management."""

import urllib.parse
from pathlib import Path
from typing import Any, TypedDict

from ..core.client import NotebookLMClient
from .errors import ServiceError, ValidationError

VALID_SOURCE_TYPES = ("url", "text", "drive", "file")
VALID_DRIVE_DOC_TYPES = ("doc", "slides", "sheets", "pdf")

# Only allow safe, public URL schemes for URL sources
ALLOWED_URL_SCHEMES = frozenset({"http", "https"})

# MIME type mapping for Drive doc types
DRIVE_MIME_TYPES = {
    "doc": "application/vnd.google-apps.document",
    "slides": "application/vnd.google-apps.presentation",
    "sheets": "application/vnd.google-apps.spreadsheet",
    "pdf": "application/pdf",
}

# Mirrors the supported_extensions check in core/sources.py:add_file.
# Duplicated here so replace_source_file can fail BEFORE the destructive
# delete step (Pre-check pattern — load-bearing safety, not redundancy).
SUPPORTED_FILE_EXTS = frozenset(
    {
        ".pdf",
        ".txt",
        ".md",
        ".docx",
        ".csv",
        ".mp3",
        ".m4a",
        ".wav",
        ".aac",
        ".ogg",
        ".opus",
        ".mp4",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
    }
)


class AddSourceResult(TypedDict):
    """Result of adding a source."""

    source_type: str
    source_id: str
    title: str


class DriveSourceInfo(TypedDict, total=False):
    """Info about a Drive source including freshness."""

    id: str
    title: str
    type: str
    stale: bool | None
    drive_doc_id: str | None


class SyncResult(TypedDict):
    """Result of syncing Drive sources."""

    source_id: str
    synced: bool
    error: str | None


class SourceContentResult(TypedDict):
    """Result of getting source content."""

    content: str
    title: str
    source_type: str
    char_count: int


class RenameResult(TypedDict):
    """Result of renaming a source."""

    source_id: str
    title: str


class DescribeResult(TypedDict):
    """Result of describing a source."""

    summary: str
    keywords: list[str]


class DriveListResult(TypedDict):
    """Result of listing Drive sources."""

    drive_sources: list[DriveSourceInfo]
    other_sources: list[dict[str, object | None]]
    drive_count: int
    stale_count: int


class BulkAddResult(TypedDict):
    """Result of bulk adding sources."""

    results: list[AddSourceResult]
    added_count: int


class ReplaceSourceFileResult(TypedDict):
    """Result of replacing an existing source with a new local file upload."""

    notebook_id: str
    old_source_id: str
    new_source_id: str
    title: str
    file_path: str
    message: str


def validate_source_type(source_type: str) -> None:
    """Validate source type. Raises ValidationError if invalid."""
    if source_type not in VALID_SOURCE_TYPES:
        raise ValidationError(
            f"Unknown source type '{source_type}'. Valid types: {', '.join(VALID_SOURCE_TYPES)}",
        )


def resolve_drive_mime_type(doc_type: str) -> str:
    """Convert doc_type shorthand to MIME type.

    Returns the MIME type string, falling back to Google Doc MIME type.
    """
    return DRIVE_MIME_TYPES.get(doc_type, DRIVE_MIME_TYPES["doc"])


def add_source(
    client: NotebookLMClient,
    notebook_id: str,
    source_type: str,
    *,
    url: str | None = None,
    text: str | None = None,
    title: str | None = None,
    file_path: str | None = None,
    document_id: str | None = None,
    doc_type: str = "doc",
    wait: bool = False,
    wait_timeout: float = 120.0,
) -> AddSourceResult:
    """Add a source to a notebook.

    Centralizes validation and routing for all source types.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID
        source_type: Type of source (url, text, drive, file)
        url: URL to add (required for source_type=url)
        text: Text content (required for source_type=text)
        title: Display title (optional)
        file_path: Local file path (required for source_type=file)
        document_id: Drive document ID (required for source_type=drive)
        doc_type: Drive doc type: doc|slides|sheets|pdf
        wait: Wait for source processing
        wait_timeout: Max seconds to wait

    Returns:
        AddSourceResult with source_type, source_id, title

    Raises:
        ValidationError: If source_type or required params are invalid
        ServiceError: If the add operation fails
    """
    validate_source_type(source_type)

    try:
        if source_type == "url":
            if not url:
                raise ValidationError("url is required for source_type='url'")
            parsed = urllib.parse.urlparse(url)
            if not parsed.scheme or parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
                raise ValidationError(
                    f"URL scheme '{parsed.scheme}' is not allowed. "
                    f"Only http:// and https:// URLs are supported."
                )
            result = client.add_url_source(notebook_id, url, wait=wait, wait_timeout=wait_timeout)
            return _extract_result(result, "url", url)

        elif source_type == "text":
            if not text:
                raise ValidationError("text is required for source_type='text'")
            effective_title = title or "Pasted Text"
            result = client.add_text_source(
                notebook_id,
                text,
                effective_title,
                wait=wait,
                wait_timeout=wait_timeout,
            )
            return _extract_result(result, "text", effective_title)

        elif source_type == "drive":
            if not document_id:
                raise ValidationError("document_id is required for source_type='drive'")
            effective_title = title or "Drive Document"
            mime_type = resolve_drive_mime_type(doc_type)
            result = client.add_drive_source(
                notebook_id,
                document_id,
                effective_title,
                mime_type,
                wait=wait,
                wait_timeout=wait_timeout,
            )
            return _extract_result(result, "drive", effective_title)

        elif source_type == "file":
            if not file_path:
                raise ValidationError("file_path is required for source_type='file'")
            result = client.add_file(notebook_id, file_path, wait=wait, wait_timeout=wait_timeout)
            fallback_title = str(file_path).split("/")[-1]
            return _extract_result(result, "file", fallback_title)

    except (ValidationError, ServiceError):
        raise
    except Exception as e:
        hint = (
            "Check the URL is accessible. For YouTube, ensure the video is public."
            if source_type == "url"
            else None
        )
        raise ServiceError(
            f"Failed to add {source_type} source: {e}",
            user_message=f"Could not add {source_type} source.",
            hint=hint,
        ) from e

    # Should never reach here due to validate_source_type above
    raise ServiceError(f"Unexpected source type: {source_type}")


def _extract_result(
    result: dict[str, Any] | None,
    source_type: str,
    fallback_title: str,
) -> AddSourceResult:
    """Extract AddSourceResult from client response."""
    if not result or not result.get("id"):
        raise ServiceError(
            f"Failed to add {source_type} source — no ID returned",
            user_message=f"Failed to add {source_type} source.",
        )
    return {
        "source_type": source_type,
        "source_id": result["id"],
        "title": result.get("title", fallback_title),
    }


def add_sources(
    client: NotebookLMClient,
    notebook_id: str,
    sources: list[dict[str, Any]],
    *,
    wait: bool = False,
    wait_timeout: float = 120.0,
) -> BulkAddResult:
    """Add multiple sources to a notebook.

    URL sources are batched into a single API call for efficiency.
    Non-URL sources (text, drive, file) fall back to individual calls.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID
        sources: List of source descriptors, each a dict with:
            - source_type: str (url, text, drive, file)
            - url: str (for url type)
            - text: str (for text type)
            - title: str (optional)
            - document_id: str (for drive type)
            - doc_type: str (for drive type, default "doc")
            - file_path: str (for file type)
        wait: Wait for source processing
        wait_timeout: Max seconds to wait per source

    Returns:
        BulkAddResult with results list and added_count

    Raises:
        ValidationError: If sources list is empty or has invalid entries
        ServiceError: If the add operation fails
    """
    if not sources:
        raise ValidationError("No sources provided for bulk add.")

    # Validate all source types upfront
    for src in sources:
        st = src.get("source_type", "")
        validate_source_type(st)

    # Separate URL sources for batching vs others for individual adds
    url_sources = [s for s in sources if s.get("source_type") == "url"]
    other_sources = [s for s in sources if s.get("source_type") != "url"]

    results: list[AddSourceResult] = []

    # Batch URL sources in a single API call
    if url_sources:
        urls = []
        for src in url_sources:
            url = src.get("url")
            if not url:
                raise ValidationError("url is required for source_type='url'")
            urls.append(url)

        try:
            raw_results = client.add_url_sources(
                notebook_id,
                urls,
                wait=wait,
                wait_timeout=wait_timeout,
            )
            for i, raw in enumerate(raw_results):
                if raw and raw.get("id"):
                    results.append(
                        {
                            "source_type": "url",
                            "source_id": raw["id"],
                            "title": raw.get("title", urls[i]),
                        }
                    )
                else:
                    raise ServiceError(
                        f"Failed to add URL source '{urls[i]}' — no ID returned",
                        user_message=f"Failed to add URL source: {urls[i]}",
                    )
        except (ValidationError, ServiceError):
            raise
        except Exception as e:
            raise ServiceError(
                f"Failed to batch-add URL sources: {e}",
                user_message="Could not add URL sources.",
                hint="Check the URLs are accessible. For YouTube, ensure the videos are public.",
            ) from e

    # Add non-URL sources individually
    for src in other_sources:
        result = add_source(
            client,
            notebook_id,
            src["source_type"],
            text=src.get("text"),
            title=src.get("title"),
            file_path=src.get("file_path"),
            document_id=src.get("document_id"),
            doc_type=src.get("doc_type", "doc"),
            wait=wait,
            wait_timeout=wait_timeout,
        )
        results.append(result)

    return {
        "results": results,
        "added_count": len(results),
    }


def list_drive_sources(
    client: NotebookLMClient,
    notebook_id: str,
) -> DriveListResult:
    """List sources with Drive freshness status.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID

    Returns:
        DriveListResult with drive/other sources and counts

    Raises:
        ServiceError: If listing fails
    """
    try:
        sources = client.get_notebook_sources_with_types(notebook_id)
    except Exception as e:
        raise ServiceError(
            f"Failed to list sources: {e}",
            user_message="Could not list notebook sources.",
        ) from e

    drive_sources: list[DriveSourceInfo] = []
    other_sources: list[dict[str, object | None]] = []

    for source in sources:
        source_info: dict[str, object | None] = {
            "id": source.get("id"),
            "title": source.get("title"),
            "type": source.get("source_type_name"),
        }

        if source.get("can_sync"):
            is_fresh = client.check_source_freshness(source["id"])
            source_id = source.get("id")
            source_title = source.get("title")
            source_type_name = source.get("source_type_name")
            drive_info: DriveSourceInfo = {
                "id": source_id if isinstance(source_id, str) else "",
                "title": source_title if isinstance(source_title, str) else "",
                "type": source_type_name if isinstance(source_type_name, str) else "unknown",
                "stale": (not is_fresh) if is_fresh is not None else None,
                "drive_doc_id": source.get("drive_doc_id"),
            }
            drive_sources.append(drive_info)
        else:
            other_sources.append(source_info)

    return {
        "drive_sources": drive_sources,
        "other_sources": other_sources,
        "drive_count": len(drive_sources),
        "stale_count": sum(1 for s in drive_sources if s.get("stale")),
    }


def sync_drive_sources(
    client: NotebookLMClient,
    source_ids: list[str],
) -> list[SyncResult]:
    """Sync Drive sources with latest content.

    Args:
        client: Authenticated NotebookLM client
        source_ids: Source UUIDs to sync

    Returns:
        List of SyncResult per source

    Raises:
        ServiceError: If the sync operation fails entirely
    """
    if not source_ids:
        raise ValidationError("No source IDs provided for sync.")

    results: list[SyncResult] = []
    for source_id in source_ids:
        try:
            result = client.sync_drive_source(source_id)
            results.append({"source_id": source_id, "synced": bool(result), "error": None})
        except Exception as e:
            results.append({"source_id": source_id, "synced": False, "error": str(e)})

    return results


def rename_source(
    client: NotebookLMClient,
    notebook_id: str,
    source_id: str,
    new_title: str,
) -> RenameResult:
    """Rename a source in a notebook.

    NotebookLM internal 'Note' objects (generated_text source_type=8) require
    a different RPC than regular Sources. The source's type is looked up first
    and the call is routed accordingly (notes use update_note title-only).

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID containing the source
        source_id: Source UUID to rename
        new_title: New display title

    Returns:
        RenameResult with source_id and new title

    Raises:
        ValidationError: If new_title is empty
        ServiceError: If rename fails
    """
    if not new_title or not new_title.strip():
        raise ValidationError("new_title cannot be empty.")

    source_type = _resolve_source_type(client, notebook_id, source_id)

    try:
        result = client.rename_source(
            notebook_id, source_id, new_title.strip(), source_type=source_type
        )
        if not result:
            raise ServiceError(
                f"Rename returned no data for source {source_id}",
                user_message="Failed to rename source.",
            )
        return {
            "source_id": result["id"],
            "title": result["title"],
        }
    except (ValidationError, ServiceError):
        raise
    except Exception as e:
        raise ServiceError(
            f"Failed to rename source {source_id}: {e}",
            user_message="Failed to rename source.",
        ) from e


def _resolve_source_type(
    client: NotebookLMClient,
    notebook_id: str | None,
    source_id: str,
) -> int | None:
    """Resolve source type by list_notes membership only (v3 회귀 픽스, 세션310).

    NotebookLM stores Sources (external docs) and Notes (generated_text/mind_map)
    as separate object kinds with separate RPCs (tGMBJ vs AH0mwd). Callers that
    need type-aware routing pass the resolved type to the client method.

    회귀 배경: NLM 백엔드의 ``get_notebook`` 응답에서 모든 일반 text source의
    ``metadata[4] = 8``로 응답됨. 상수 ``SOURCE_TYPE_GENERATED_TEXT = 8``과
    값이 우연 일치하여, ``get_notebook_sources_with_types``의 ``source_type``
    필드를 신뢰하면 모든 일반 source가 Note로 잘못 분류되어 ``delete_note``
    RPC로 잘못 라우팅됨 (세션310 진단으로 확정).

    권위 기준: ``list_notes`` 멤버십만 사용. 진짜 Note 객체는 ``cFji9`` 응답
    에만 등장. ``content`` 키 존재로 mind_map JSON·deleted 항목 등을 추가
    필터링하여 false positive 0.

    Returns None when notebook_id is missing or list_notes 매칭 실패 — callers
    should treat this as "default Source routing" (regular tGMBJ RPC).
    """
    if not notebook_id:
        return None
    try:
        from ..core.constants import SOURCE_TYPE_GENERATED_TEXT

        notes = client.list_notes(notebook_id)
        for n in notes:
            if n.get("id") == source_id and n.get("content") is not None:
                return SOURCE_TYPE_GENERATED_TEXT
    except Exception:
        pass
    return None


_NOTE_HINT = (
    "If this is a generated_text (saved AI response or mind map) source, "
    "pass notebook_id parameter — type-aware routing requires it."
)


def delete_source(
    client: NotebookLMClient,
    source_id: str,
    notebook_id: str | None = None,
) -> None:
    """Delete a source permanently.

    NotebookLM internal 'Note' objects (generated_text source_type=8) require
    a different RPC than regular Sources. When `notebook_id` is provided, the
    source's type is looked up first and the call is routed accordingly.

    Args:
        client: Authenticated NotebookLM client
        source_id: Source UUID
        notebook_id: Optional notebook UUID — required to delete generated_text

    Raises:
        ServiceError: If deletion fails
    """
    source_type = _resolve_source_type(client, notebook_id, source_id)

    try:
        result = client.delete_source(
            source_id,
            notebook_id=notebook_id,
            source_type=source_type,
        )
        if not result:
            raise ServiceError(
                f"Delete returned falsy for source {source_id}",
                user_message="Failed to delete source.",
                hint=_NOTE_HINT if not notebook_id else None,
            )
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(
            f"Failed to delete source {source_id}: {e}",
            user_message="Failed to delete source.",
        ) from e


def delete_sources(
    client: NotebookLMClient,
    source_ids: list[str],
    notebook_id: str | None = None,
) -> None:
    """Delete multiple sources permanently in a single request.

    When `notebook_id` is provided, type-aware routing splits generated_text
    entries (Notes) from regular sources and uses the correct RPC for each.

    Args:
        client: Authenticated NotebookLM client
        source_ids: List of source UUIDs to delete
        notebook_id: Optional notebook UUID — enables type-aware routing

    Raises:
        ValidationError: If source_ids is empty
        ServiceError: If deletion fails
    """
    if not source_ids:
        raise ValidationError("No source IDs provided for bulk delete.")

    try:
        result = client.delete_sources(source_ids, notebook_id=notebook_id)
        if not result:
            raise ServiceError(
                f"Bulk delete returned falsy for {len(source_ids)} sources",
                user_message="Failed to delete sources.",
                hint=_NOTE_HINT if not notebook_id else None,
            )
    except (ValidationError, ServiceError):
        raise
    except Exception as e:
        raise ServiceError(
            f"Failed to delete {len(source_ids)} sources: {e}",
            user_message="Failed to delete sources.",
        ) from e


def describe_source(
    client: NotebookLMClient,
    source_id: str,
    notebook_id: str | None = None,
) -> DescribeResult:
    """Get AI-generated source summary with keywords.

    NotebookLM internal Note objects (generated_text) have no per-note summary
    RPC; their body is itself descriptive. When `notebook_id` is provided,
    the type is looked up; if it's a Note, the note's content is returned as
    the summary instead of calling the Source-only RPC.

    Args:
        client: Authenticated NotebookLM client
        source_id: Source UUID
        notebook_id: Optional notebook UUID — required for note routing

    Returns:
        DescribeResult with summary and keywords

    Raises:
        ServiceError: If describe fails
    """
    source_type = _resolve_source_type(client, notebook_id, source_id)

    try:
        result = client.get_source_guide(
            source_id, notebook_id=notebook_id, source_type=source_type
        )
        if not result:
            raise ServiceError(
                f"No description returned for source {source_id}",
                user_message="Failed to get source summary.",
                hint=_NOTE_HINT if not notebook_id else None,
            )
        return {
            "summary": result.get("summary", ""),
            "keywords": result.get("keywords", []),
        }
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(
            f"Failed to describe source {source_id}: {e}",
            user_message="Failed to get source summary.",
            hint=_NOTE_HINT if not notebook_id else None,
        ) from e


def get_source_content(
    client: NotebookLMClient,
    source_id: str,
    notebook_id: str | None = None,
) -> SourceContentResult:
    """Get raw text content of a source (no AI processing).

    NotebookLM internal Note objects (generated_text) have no per-note
    get_content RPC — their body is already returned by list_notes. When
    `notebook_id` is provided and the type is a Note, the note's content
    is returned directly instead of calling the Source-only RPC.

    Args:
        client: Authenticated NotebookLM client
        source_id: Source UUID
        notebook_id: Optional notebook UUID — required for note routing

    Returns:
        SourceContentResult with content, title, type, and char_count

    Raises:
        ServiceError: If content retrieval fails
    """
    source_type = _resolve_source_type(client, notebook_id, source_id)

    try:
        result = client.get_source_fulltext(
            source_id, notebook_id=notebook_id, source_type=source_type
        )
        if not result:
            raise ServiceError(
                f"No content returned for source {source_id}",
                user_message="Failed to get source content.",
                hint=_NOTE_HINT if not notebook_id else None,
            )
        content = result.get("content", "")
        return {
            "content": content,
            "title": result.get("title", ""),
            "source_type": result.get("source_type", "unknown"),
            "char_count": len(content),
        }
    except ServiceError:
        raise
    except Exception as e:
        raise ServiceError(
            f"Failed to get content for source {source_id}: {e}",
            user_message="Failed to get source content.",
            hint=_NOTE_HINT if not notebook_id else None,
        ) from e


def replace_source_file(
    client: NotebookLMClient,
    notebook_id: str,
    source_id: str,
    file_path: str,
) -> ReplaceSourceFileResult:
    """Replace an existing source by deleting it and uploading a new local file.

    Composition wrapper over ``delete_source`` + ``add_source`` (DRY — does
    not inline RPC calls). NLM has no in-place update RPC for file sources,
    so a delete + add transaction is required, which changes the source_id.

    Pre-check is intentionally redundant with ``core/sources.py:add_file``'s
    file validation — load-bearing safety to fail BEFORE the destructive
    delete step. Without it, a missing/invalid file would surface only after
    the delete succeeds, leaving the source permanently lost.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID containing the source
        source_id: Source UUID to replace
        file_path: Path to the local file to upload as the replacement

    Returns:
        ReplaceSourceFileResult with old/new source IDs, title, and path.

    Raises:
        ValidationError: If file_path is missing, not a file, empty, or has
            an unsupported extension (pre-check, before delete).
        ServiceError: If delete or add fails. If delete succeeded but add
            failed, the error message and ``user_message`` make this state
            explicit (the original source is gone).
    """
    # 1. Pre-check — MUST run before any destructive operation
    p = Path(file_path)
    if not p.exists():
        raise ValidationError(
            f"File not found: {file_path}",
            user_message=f"File does not exist: {file_path}",
        )
    if not p.is_file():
        raise ValidationError(
            f"Not a regular file: {file_path}",
            user_message=f"Path is not a regular file: {file_path}",
        )
    if p.stat().st_size == 0:
        raise ValidationError(
            f"File is empty: {file_path}",
            user_message=f"File is empty: {file_path}",
        )
    ext = p.suffix.lower()
    if ext not in SUPPORTED_FILE_EXTS:
        raise ValidationError(
            f"Unsupported file type: {ext}",
            user_message=f"Unsupported file type: {ext}",
            hint=f"Supported types: {', '.join(sorted(SUPPORTED_FILE_EXTS))}",
        )

    # 2. Title preservation (best-effort, non-fatal)
    preserved_title: str | None = None
    try:
        for src in client.get_notebook_sources_with_types(notebook_id):
            if src.get("id") == source_id:
                title_val = src.get("title")
                if isinstance(title_val, str) and title_val.strip():
                    preserved_title = title_val
                break
    except Exception:
        pass  # title preservation is optional; proceed without it

    # 3. Delete the existing source (Composition — propagates ServiceError)
    delete_source(client, source_id, notebook_id=notebook_id)

    # 4. Add the new file (Composition). On failure, the original source is
    # already gone — surface that explicitly so the user knows to re-add.
    try:
        add_res = add_source(
            client,
            notebook_id,
            "file",
            file_path=str(p),
            title=preserved_title,
        )
    except (ValidationError, ServiceError) as e:
        raise ServiceError(
            f"Replace failed: delete succeeded but add failed: {e}",
            user_message=(
                "Source was deleted but the replacement upload failed. "
                "The original source is gone; please re-add the file manually."
            ),
            hint="Verify the file path and retry add_source with source_type='file'.",
        ) from e

    return {
        "notebook_id": notebook_id,
        "old_source_id": source_id,
        "new_source_id": add_res["source_id"],
        "title": add_res["title"],
        "file_path": str(p),
        "message": f"Replaced source {source_id} with {add_res['source_id']}",
    }
