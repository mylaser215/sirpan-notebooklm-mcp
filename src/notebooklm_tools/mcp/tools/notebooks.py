"""Notebook tools - Notebook management operations."""

from pathlib import Path

from ...services import ServiceError
from ...services import notebooks as notebooks_service
from ...services.sync_helpers import detect_drift as _detect_drift
from ...services.sync_helpers import format_drift_summary
from ._utils import ResultDict, error_result, get_client, logged_tool


@logged_tool()
def notebook_list(max_results: int = 100) -> ResultDict:
    """List all notebooks.

    Args:
        max_results: Maximum number of notebooks to return (default: 100)
    """
    try:
        client = get_client()
        result = notebooks_service.list_notebooks(client, max_results)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def notebook_get(notebook_id: str) -> ResultDict:
    """Get notebook details with sources.

    Args:
        notebook_id: Notebook UUID
    """
    try:
        client = get_client()
        result = notebooks_service.get_notebook(client, notebook_id)
        return {
            "status": "success",
            "notebook": {
                "id": result["notebook_id"],
                "title": result["title"],
                "source_count": result["source_count"],
                "url": result["url"],
            },
            "sources": result["sources"],
        }
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def notebook_describe(notebook_id: str) -> ResultDict:
    """Get AI-generated notebook summary with suggested topics.

    Args:
        notebook_id: Notebook UUID

    Returns: summary (markdown), suggested_topics list
    """
    try:
        client = get_client()
        result = notebooks_service.describe_notebook(client, notebook_id)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def notebook_create(title: str = "") -> ResultDict:
    """Create a new notebook.

    Args:
        title: Optional title for the notebook
    """
    try:
        client = get_client()
        result = notebooks_service.create_notebook(client, title)
        return {
            "status": "success",
            "notebook_id": result["notebook_id"],
            "notebook": {
                "id": result["notebook_id"],
                "title": result["title"],
                "url": result["url"],
            },
            "message": result["message"],
        }
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def notebook_rename(notebook_id: str, new_title: str) -> ResultDict:
    """Rename a notebook.

    Args:
        notebook_id: Notebook UUID
        new_title: New title
    """
    try:
        client = get_client()
        result = notebooks_service.rename_notebook(client, notebook_id, new_title)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def notebook_clone(
    notebook_id: str,
    new_title: str,
    exclude_types: list[str] | None = None,
) -> ResultDict:
    """Clone a notebook, preserving markdown fidelity.

    Uses ``get_source_fulltext(raw_markdown=True)`` to reconstruct headings,
    bullet depth, bold/italic/inline-code, and tables from the hizoJc RPC
    tree. For routine NLM sync from disk use ``source_replace_file``
    (no round-trip through NLM serialization).

    Args:
        notebook_id: UUID of the notebook to clone from.
        new_title: Title for the new notebook.
        exclude_types: Lowercased ``source_type_name`` values to skip
            (e.g., ["url", "note"]). ``None`` keeps the default binary exclude;
            ``[]`` attempts all types (binaries still skipped as irrecoverable).
    """
    try:
        client = get_client()
        result = notebooks_service.clone_notebook(
            client, notebook_id, new_title, exclude_types=exclude_types
        )
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def notebook_delete(notebook_id: str, confirm: bool = False) -> ResultDict:
    """Delete notebook permanently. IRREVERSIBLE. Requires confirm=True.

    Args:
        notebook_id: Notebook UUID
        confirm: Must be True after user approval
    """
    if not confirm:
        return {
            "status": "error",
            "error": "Deletion not confirmed. You must ask the user to confirm "
            "before deleting. Set confirm=True only after user approval.",
            "warning": "This action is IRREVERSIBLE. The notebook and all its contents will be permanently deleted.",
        }

    try:
        client = get_client()
        result = notebooks_service.delete_notebook(client, notebook_id)
        return {"status": "success", **result}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))


@logged_tool()
def detect_drift(notebook_id: str, vault_root: str | None = None) -> ResultDict:
    """Detect drift between NLM notebook sources and disk files.

    Maps each source title to a disk path under the vault root and classifies
    every source as matched / missing (NLM 잔재) / ambiguous (다중 매칭) /
    skip_type. Used as step ⑥ of the daily NLM sync routine — surfaces stale
    sources before they accumulate beyond NLM Pro quota.

    Args:
        notebook_id: Notebook UUID to inspect.
        vault_root: Vault root override. ``None`` (default) delegates to the
            ``SIRPAN_VAULT`` env var, then to the hard-coded fallback inside
            ``sync_helpers.get_vault_root``. Pass an explicit path only to
            override both.

    Returns:
        report — full DriftReport TypedDict (matched / matched_markdown /
            matched_non_markdown / missing / ambiguous / skip_type + total).
        summary — human-friendly one-line + detail string (the same output
            previously produced by the inline ``format_drift_summary`` call).
    """
    try:
        client = get_client()
        vault = Path(vault_root) if vault_root else None
        report = _detect_drift(
            client.get_notebook_sources_with_types,
            notebook_id,
            vault_root=vault,
        )
        summary = format_drift_summary(report)
        return {"status": "success", "report": report, "summary": summary}
    except ServiceError as e:
        return error_result(e.user_message, hint=e.hint)
    except Exception as e:
        return error_result(str(e))
