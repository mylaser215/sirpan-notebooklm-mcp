"""Notebooks service — shared business logic for notebook CRUD and metadata operations."""

import contextlib
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from ..core.client import NotebookLMClient
from ..utils.config import get_base_url
from .errors import CreationError, NotFoundError, ServiceError, ValidationError


class NotebookInfo(TypedDict):
    """Notebook summary info."""

    id: str
    title: str
    source_count: int
    url: str
    ownership: str
    is_shared: bool
    created_at: str | None
    modified_at: str | None


class NotebookListResult(TypedDict):
    """Result of listing notebooks."""

    notebooks: list[NotebookInfo]
    count: int
    owned_count: int
    shared_count: int
    shared_by_me_count: int


class SourceInfo(TypedDict):
    """Source summary in notebook details."""

    id: str
    title: str


class NotebookDetailResult(TypedDict):
    """Result of getting a single notebook's details."""

    notebook_id: str
    title: str
    source_count: int
    url: str
    sources: list[SourceInfo]


class NotebookSummaryResult(TypedDict):
    """Result of AI-generated notebook summary."""

    summary: str
    suggested_topics: list[str]


class NotebookCreateResult(TypedDict):
    """Result of creating a notebook."""

    notebook_id: str
    title: str
    url: str
    message: str


class NotebookRenameResult(TypedDict):
    """Result of renaming a notebook."""

    notebook_id: str
    new_title: str
    message: str


class NotebookDeleteResult(TypedDict):
    """Result of deleting a notebook."""

    message: str


class CloneNotebookResult(TypedDict):
    """Result of cloning a notebook."""

    new_notebook_id: str
    new_title: str
    cloned_sources: list[dict[str, Any]]
    cloned_notes: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    total_cloned: int


# Source types whose original binary cannot be re-uploaded by clone — NLM
# backend doesn't expose a download RPC for these. Default-excluded in
# clone_notebook; users may override via `exclude_types=[]` but binaries
# remain skipped (reason="binary_no_source_file").
_DEFAULT_BINARY_EXCLUDE = frozenset({"pdf", "uploaded_file", "audio", "image", "word_doc"})


def list_notebooks(
    client: NotebookLMClient,
    max_results: int = 100,
) -> NotebookListResult:
    """List all notebooks.

    Args:
        client: Authenticated NotebookLM client
        max_results: Maximum notebooks to return

    Returns:
        NotebookListResult with notebooks and counts

    Raises:
        ServiceError: If listing fails
    """
    try:
        notebooks = client.list_notebooks()
    except Exception as e:
        raise ServiceError(f"Failed to list notebooks: {e}") from e

    owned_count = sum(1 for nb in notebooks if nb.is_owned)
    shared_count = len(notebooks) - owned_count
    shared_by_me_count = sum(1 for nb in notebooks if nb.is_owned and nb.is_shared)

    return {
        "notebooks": [
            {
                "id": nb.id,
                "title": nb.title,
                "source_count": nb.source_count,
                "url": nb.url,
                "ownership": nb.ownership,
                "is_shared": nb.is_shared,
                "created_at": nb.created_at,
                "modified_at": nb.modified_at,
            }
            for nb in notebooks[:max_results]
        ],
        "count": len(notebooks),
        "owned_count": owned_count,
        "shared_count": shared_count,
        "shared_by_me_count": shared_by_me_count,
    }


def get_notebook(
    client: NotebookLMClient,
    notebook_id: str,
) -> NotebookDetailResult:
    """Get notebook details including source list.

    Handles raw RPC list responses from the API, normalising them into a
    clean typed dict.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID

    Returns:
        NotebookDetailResult with title, sources, etc.

    Raises:
        NotFoundError: If notebook not found
        ServiceError: If the API call fails
    """
    try:
        nb = client.get_notebook(notebook_id)
    except Exception as e:
        raise ServiceError(f"Failed to get notebook: {e}") from e

    if not nb:
        raise NotFoundError(
            f"Notebook {notebook_id} not found",
            user_message=f"Notebook {notebook_id} not found.",
        )

    # The client may return raw RPC data (nested list) instead of a Notebook object.
    # Normalise that into a consistent result.
    if isinstance(nb, list):
        data = nb[0] if nb and isinstance(nb[0], list) else nb
        if isinstance(data, list) and len(data) >= 3:
            title = data[0] if isinstance(data[0], str) else "Untitled"
            sources_data = data[1] if len(data) > 1 and isinstance(data[1], list) else []
            nb_id = data[2] if len(data) > 2 else notebook_id

            sources: list[SourceInfo] = []
            for src in sources_data:
                if isinstance(src, list) and len(src) >= 2:
                    src_id = src[0][0] if isinstance(src[0], list) and src[0] else src[0]
                    src_title = src[1] if len(src) > 1 else "Untitled"
                    sources.append({"id": src_id, "title": src_title})

            return {
                "notebook_id": nb_id,
                "title": title,
                "source_count": len(sources),
                "url": f"{get_base_url()}/notebook/{nb_id}",
                "sources": sources,
            }

    # Fallback: if nb is a dataclass-like object with attrs (e.g. from list_notebooks)
    if hasattr(nb, "id"):
        return {
            "notebook_id": nb.id,
            "title": getattr(nb, "title", "Untitled"),
            "source_count": getattr(nb, "source_count", 0),
            "url": getattr(nb, "url", f"{get_base_url()}/notebook/{nb.id}"),
            "sources": [],
        }

    # Last-resort fallback
    raise ServiceError(
        f"Unexpected notebook data format: {str(nb)[:200]}",
        user_message="Received unexpected data format from the API.",
    )


def describe_notebook(
    client: NotebookLMClient,
    notebook_id: str,
) -> NotebookSummaryResult:
    """Get AI-generated notebook summary with suggested topics.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID

    Returns:
        NotebookSummaryResult with summary and topics

    Raises:
        ServiceError: If the summary call fails
    """
    try:
        result = client.get_notebook_summary(notebook_id)
    except Exception as e:
        raise ServiceError(f"Failed to get notebook summary: {e}") from e

    if result:
        return {
            "summary": result.get("summary", ""),
            "suggested_topics": result.get("suggested_topics", []),
        }

    raise ServiceError(
        "Notebook summary returned no data",
        user_message="Failed to get notebook summary — no data returned.",
    )


def create_notebook(
    client: NotebookLMClient,
    title: str = "",
) -> NotebookCreateResult:
    """Create a new notebook.

    Args:
        client: Authenticated NotebookLM client
        title: Notebook title (optional)

    Returns:
        NotebookCreateResult with notebook ID and URL

    Raises:
        CreationError: If creation fails
    """
    try:
        nb = client.create_notebook(title)
    except Exception as e:
        raise CreationError(f"Failed to create notebook: {e}") from e

    if nb and hasattr(nb, "id"):
        return {
            "notebook_id": nb.id,
            "title": nb.title,
            "url": nb.url,
            "message": f"Created notebook: {nb.title}",
        }

    raise CreationError(
        "Notebook creation returned no data",
        user_message="Failed to create notebook — no confirmation from API.",
    )


def rename_notebook(
    client: NotebookLMClient,
    notebook_id: str,
    new_title: str,
) -> NotebookRenameResult:
    """Rename a notebook.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID
        new_title: New title

    Returns:
        NotebookRenameResult

    Raises:
        ValidationError: If title is empty
        ServiceError: If rename fails
    """
    if not new_title or not new_title.strip():
        raise ValidationError(
            "New title is required.",
            user_message="Notebook title cannot be empty.",
        )

    try:
        result = client.rename_notebook(notebook_id, new_title)
    except Exception as e:
        raise ServiceError(f"Failed to rename notebook: {e}") from e

    if result:
        return {
            "notebook_id": notebook_id,
            "new_title": new_title,
            "message": f"Renamed notebook to: {new_title}",
        }

    raise ServiceError(
        "Rename returned falsy result",
        user_message="Rename may have failed — no confirmation from API.",
    )


def delete_notebook(
    client: NotebookLMClient,
    notebook_id: str,
) -> NotebookDeleteResult:
    """Delete a notebook permanently.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID

    Returns:
        NotebookDeleteResult

    Raises:
        ServiceError: If deletion fails
    """
    try:
        result = client.delete_notebook(notebook_id)
    except Exception as e:
        raise ServiceError(f"Failed to delete notebook: {e}") from e

    if result:
        return {
            "message": f"Notebook {notebook_id} has been permanently deleted.",
        }

    raise ServiceError(
        "Notebook deletion returned falsy result",
        user_message="Failed to delete notebook — no confirmation from API.",
    )


def clone_notebook(
    client: NotebookLMClient,
    source_notebook_id: str,
    new_title: str,
    exclude_types: list[str] | None = None,
) -> CloneNotebookResult:
    """Clone a notebook by replicating all sources and notes into a new notebook.

    Binary source types (PDF/audio/image/uploaded_file/word_doc) are skipped by
    default because NLM's backend does not return the original uploaded file —
    only AI-extracted text. Pass ``exclude_types=[]`` to override the default
    exclude list, but binaries will still be reported in ``skipped`` with
    reason ``"binary_no_source_file"`` (the original file is irrecoverable).

    Drive Slides and Sheets share ``source_type=2`` in NLM metadata and cannot
    be distinguished without an extra Drive API call. This clone defaults to
    the presentation MIME for type 2; NLM accepts both interchangeably for the
    Drive add RPC.

    Notes (``generated_text``) are cloned via ``create_note``. Mind maps are
    filtered out by ``list_notes`` itself (they store JSON in the content
    field) so they never reach this function.

    Fail-close: if any clone step raises, the new notebook is best-effort
    deleted and the original exception is wrapped in ``ServiceError``.

    Concurrency intentionally omitted — the services layer is synchronous by
    convention and rate-limiting policy is uncertain. For future parallelism
    add a wrapper in ``services/batch.py``, not a kwarg here.

    Args:
        client: Authenticated NotebookLM client
        source_notebook_id: UUID of the notebook to clone from
        new_title: Title for the new notebook
        exclude_types: Lowercased ``source_type_name`` values to skip
            (e.g., ``["url", "note"]``). Pass ``None`` to use the default
            binary-exclude set; pass ``[]`` to attempt all types.

    Returns:
        CloneNotebookResult with new notebook id/title, cloned source and
        note lists, skipped list, and total cloned count.

    Raises:
        NotFoundError: If source notebook is not found.
        CreationError: If new notebook creation fails.
        ServiceError: If a clone step fails (new notebook is rolled back).
    """
    if not new_title or not new_title.strip():
        raise ValidationError(
            "new_title is required.",
            user_message="New notebook title cannot be empty.",
        )

    if exclude_types is None:
        exclude = set(_DEFAULT_BINARY_EXCLUDE)
    else:
        exclude = {e.lower() for e in exclude_types}

    # 1. Verify source notebook exists
    try:
        src_meta = client.get_notebook(source_notebook_id)
    except Exception as e:
        raise ServiceError(
            f"Failed to read source notebook {source_notebook_id}: {e}",
            user_message="Could not read source notebook.",
        ) from e
    if not src_meta:
        raise NotFoundError(
            f"Source notebook {source_notebook_id} not found",
            user_message=f"Source notebook {source_notebook_id} not found.",
            resource_type="notebook",
        )

    # 2. Enumerate sources and notes
    try:
        sources = client.get_notebook_sources_with_types(source_notebook_id)
    except Exception as e:
        raise ServiceError(
            f"Failed to enumerate sources for {source_notebook_id}: {e}",
            user_message="Could not list source notebook contents.",
        ) from e

    try:
        notes = [
            n for n in client.list_notes(source_notebook_id) if n.get("content") is not None
        ]
    except Exception:
        notes = []  # best-effort: notes are optional

    # 3. Create new notebook (CreationError propagates)
    create_res = create_notebook(client, new_title)
    new_id = create_res["notebook_id"]

    cloned_sources: list[dict[str, Any]] = []
    cloned_notes: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    # Pre-index notes by id for O(1) lookup when reconciling Source-area
    # generated_text entries (some notebooks register generated_text in the
    # Source area only; list_notes returns empty for them).
    notes_by_id = {n["id"]: n for n in notes if n.get("id")}
    consumed_note_ids: set[str] = set()

    try:
        # 4. Clone each source serially
        for s in sources:
            type_name = (s.get("source_type_name") or "").lower()
            title = s.get("title") or "Untitled"

            if type_name == "generated_text":
                # NLM stores both real Notes and ordinary text Sources with
                # metadata[4]=8; only list_notes membership distinguishes
                # them (session 310 regression). For list_notes members we
                # call create_note; otherwise we treat it as a Source-area
                # text upload and use add_text_source so the UI shows it in
                # the Sources panel exactly like the original.
                if "note" in exclude or "generated_text" in exclude:
                    skipped.append(
                        {"title": title, "type": "generated_text", "reason": "excluded"}
                    )
                    continue
                src_id = s.get("id") or ""
                is_real_note = bool(src_id and src_id in notes_by_id)

                if is_real_note:
                    content = notes_by_id[src_id].get("content") or ""
                    consumed_note_ids.add(src_id)
                else:
                    # Source-area text/markdown: fetch via default Source RPC.
                    # raw_markdown=True preserves heading/bullet/format metadata
                    # so the cloned note keeps original markdown fidelity.
                    content = ""
                    if src_id:
                        try:
                            fetched = client.get_source_fulltext(
                                src_id,
                                notebook_id=source_notebook_id,
                                raw_markdown=True,
                            )
                            if isinstance(fetched, dict):
                                content = fetched.get("content") or ""
                        except Exception:
                            content = ""

                if not content:
                    skipped.append(
                        {
                            "title": title,
                            "type": "generated_text",
                            "reason": "empty_text_content",
                        }
                    )
                    continue

                if is_real_note:
                    nr = client.create_note(new_id, content=content, title=title)
                    if nr and nr.get("id"):
                        cloned_notes.append(
                            {"note_id": nr["id"], "title": nr.get("title", title)}
                        )
                    else:
                        skipped.append(
                            {
                                "title": title,
                                "type": "generated_text",
                                "reason": "create_returned_none",
                            }
                        )
                else:
                    # NLM's add_text_source stores content as flat plain text
                    # (markdown headings/bullets/bold render literally). Writing
                    # the content to a temp .md file and uploading via add_file
                    # triggers NLM's markdown parser so the cloned source renders
                    # the same way the original .md did.
                    add_res = _clone_text_as_md_file(client, new_id, content, title)
                    if add_res and add_res.get("id"):
                        cloned_sources.append(
                            {
                                "source_type": "generated_text",
                                "source_id": add_res["id"],
                                "title": add_res.get("title", title),
                            }
                        )
                    else:
                        skipped.append(
                            {
                                "title": title,
                                "type": "generated_text",
                                "reason": "add_file_no_id",
                            }
                        )
                continue

            if type_name in _DEFAULT_BINARY_EXCLUDE:
                # Binaries are unrecoverable regardless of override
                skipped.append(
                    {"title": title, "type": type_name, "reason": "binary_no_source_file"}
                )
                continue

            if type_name in exclude:
                skipped.append({"title": title, "type": type_name, "reason": "excluded"})
                continue

            result = _clone_one_source(client, new_id, s, source_notebook_id)
            if result.get("status") == "skipped":
                skipped.append(
                    {
                        "title": title,
                        "type": type_name,
                        "reason": result.get("reason", "unknown"),
                    }
                )
            elif result.get("status") == "cloned":
                cloned_sources.append(
                    {
                        "source_type": type_name,
                        "source_id": result["source_id"],
                        "title": result["title"],
                    }
                )

        # 5. Clone Note-area generated_text not already consumed by the
        # Source-area pass above. This catches the rare case where a note
        # appears only in list_notes (not in get_notebook_sources_with_types).
        if "note" not in exclude and "generated_text" not in exclude:
            for n in notes:
                if n.get("id") in consumed_note_ids:
                    continue
                note_title = n.get("title") or "Note"
                try:
                    nr = client.create_note(
                        new_id, content=n.get("content", ""), title=note_title
                    )
                except Exception as e:
                    raise ServiceError(
                        f"Note clone failed for '{note_title}': {e}",
                        user_message=f"Failed to clone note '{note_title}'.",
                    ) from e
                if nr and nr.get("id"):
                    cloned_notes.append({"note_id": nr["id"], "title": nr.get("title", note_title)})
                else:
                    skipped.append(
                        {"title": note_title, "type": "note", "reason": "create_returned_none"}
                    )
        else:
            for n in notes:
                if n.get("id") in consumed_note_ids:
                    continue
                skipped.append(
                    {"title": n.get("title") or "Note", "type": "note", "reason": "excluded"}
                )
    except Exception as e:
        # Fail-close rollback — delete the new notebook best-effort
        # (original error is what matters; rollback failure is suppressed).
        with contextlib.suppress(Exception):
            client.delete_notebook(new_id)
        if isinstance(e, ServiceError):
            raise
        raise ServiceError(
            f"Clone failed, rolled back new notebook {new_id}: {e}",
            user_message="Notebook clone failed and the new notebook was deleted.",
        ) from e

    return {
        "new_notebook_id": new_id,
        "new_title": create_res["title"],
        "cloned_sources": cloned_sources,
        "cloned_notes": cloned_notes,
        "skipped": skipped,
        "total_cloned": len(cloned_sources) + len(cloned_notes),
    }


_FORBIDDEN_FILENAME_CHARS = '<>:"/\\|?*'


def _safe_md_filename(title: str) -> str:
    """Convert a source title to a filesystem-safe `.md` filename.

    NLM uses the uploaded file's basename as the new source's title, so the
    sanitized name doubles as title preservation. Windows-forbidden chars are
    replaced; trailing dots/spaces are stripped (Windows forbids them).
    """
    safe = "".join("_" if c in _FORBIDDEN_FILENAME_CHARS else c for c in title)
    safe = safe.strip().strip(".")
    if not safe:
        safe = "cloned_text"
    if not safe.lower().endswith(".md"):
        safe = f"{safe}.md"
    # Windows path component limit safety
    return safe[:200]


def _clone_text_as_md_file(
    client: NotebookLMClient,
    notebook_id: str,
    content: str,
    title: str,
) -> dict[str, Any] | None:
    """Upload text content as a temp `.md` file so NLM parses it as markdown.

    Workaround for the loss-of-formatting behaviour of `add_text_source` plus
    `get_source_fulltext` round-tripping: NLM's add_file path runs the markdown
    parser on `.md` uploads, restoring heading/bullet rendering in the UI.
    """
    filename = _safe_md_filename(title)
    tmpdir = Path(tempfile.mkdtemp(prefix="nlm_clone_md_"))
    try:
        path = tmpdir / filename
        path.write_text(content, encoding="utf-8")
        return client.add_file(notebook_id, str(path))
    finally:
        with contextlib.suppress(Exception):
            for f in tmpdir.iterdir():
                f.unlink()
            tmpdir.rmdir()


def _clone_one_source(
    client: NotebookLMClient,
    new_notebook_id: str,
    source: dict[str, Any],
    source_notebook_id: str,
) -> dict[str, Any]:
    """Dispatch one source clone by its source_type_name.

    Returns a dict with status ``cloned`` (plus source_id, title) or
    ``skipped`` (plus reason). Exceptions propagate to the caller for
    Fail-close rollback.
    """
    type_name = (source.get("source_type_name") or "").lower()
    source_type_code = source.get("source_type")
    title = source.get("title") or "Untitled"

    if type_name in ("web_page", "youtube"):
        url = source.get("url")
        if not url:
            return {"status": "skipped", "reason": "missing_url"}
        result = client.add_url_source(new_notebook_id, url)
        if not result or not result.get("id"):
            return {"status": "skipped", "reason": "add_url_no_id"}
        return {"status": "cloned", "source_id": result["id"], "title": result.get("title", title)}

    if type_name == "pasted_text":
        # raw_markdown=True preserves heading/bullet/format metadata so the
        # cloned source keeps original markdown fidelity.
        fulltext = client.get_source_fulltext(
            source["id"],
            notebook_id=source_notebook_id,
            raw_markdown=True,
        )
        content = (fulltext or {}).get("content", "") if isinstance(fulltext, dict) else ""
        if not content:
            return {"status": "skipped", "reason": "empty_text_content"}
        result = client.add_text_source(new_notebook_id, content, title)
        if not result or not result.get("id"):
            return {"status": "skipped", "reason": "add_text_no_id"}
        return {"status": "cloned", "source_id": result["id"], "title": result.get("title", title)}

    if type_name in ("google_docs", "google_slides_sheets"):
        doc_id = source.get("drive_doc_id")
        if not doc_id:
            return {"status": "skipped", "reason": "missing_drive_doc_id"}
        # Slides/Sheets share source_type=2; default to presentation MIME
        # (NLM accepts both interchangeably for the Drive RPC).
        if source_type_code == 1:
            mime = "application/vnd.google-apps.document"
        else:
            mime = "application/vnd.google-apps.presentation"
        result = client.add_drive_source(new_notebook_id, doc_id, title, mime)
        if not result or not result.get("id"):
            return {"status": "skipped", "reason": "add_drive_no_id"}
        return {"status": "cloned", "source_id": result["id"], "title": result.get("title", title)}

    return {"status": "skipped", "reason": "unsupported_type"}
