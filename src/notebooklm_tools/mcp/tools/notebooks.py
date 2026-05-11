"""Notebook tools - Notebook management operations."""

from ...services import ServiceError
from ...services import notebooks as notebooks_service
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
    acknowledge_quality_loss: bool = False,
) -> ResultDict:
    """Clone a notebook (gated — quality inferior to Agent full-clone).

    ⚠️ Quality gate: NLM's ``get_source_fulltext`` returns markdown sources as
    already-flattened plain text (broken newlines, missing **bold**, no code
    blocks). Cloning round-trips that lossy text back into NLM, so the cloned
    notebook renders worse than a clone made by reading the original .md files
    from disk (e.g., the Agent full-clone workflow).

    Until a raw-content RPC is discovered (todo 260512-053000), this tool is
    disabled by default. For high-quality clones use Agent full-clone; for
    routine NLM sync use ``source_replace_file`` (which uploads from disk and
    preserves quality completely).

    Args:
        notebook_id: UUID of the notebook to clone from.
        new_title: Title for the new notebook.
        exclude_types: Lowercased ``source_type_name`` values to skip
            (e.g., ["url", "note"]). ``None`` keeps the default binary exclude;
            ``[]`` attempts all types (binaries still skipped as irrecoverable).
        acknowledge_quality_loss: Must be ``True`` to proceed. Forces the caller
            to acknowledge that this clone is lower-quality than Agent full-clone.
    """
    if not acknowledge_quality_loss:
        return error_result(
            "notebook_clone is gated. NLM's get_source_fulltext loses raw markdown "
            "(broken newlines, missing bold/codeblock). Use Agent full-clone for "
            "high-quality clones, or source_replace_file for routine sync. "
            "Pass acknowledge_quality_loss=True to proceed anyway.",
            hint="See todo 260512-053000 for the raw-content RPC discovery task.",
        )
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
