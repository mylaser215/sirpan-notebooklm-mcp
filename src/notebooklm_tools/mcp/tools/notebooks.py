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
) -> ResultDict:
    """Clone a notebook by replicating all sources and notes into a new notebook.

    Binary source types (PDF/audio/image/uploaded_file/word_doc) are skipped
    by default because NLM does not return original uploaded files — only
    AI-extracted text. Pass ``exclude_types=[]`` to override the default
    binary-exclude set, but binaries remain skipped (reason
    ``binary_no_source_file``) since their original file is irrecoverable.

    Use this instead of round-tripping every source through Claude when
    duplicating system notebooks or scratch copies — the MCP server replicates
    via direct NLM HTTP calls.

    Args:
        notebook_id: UUID of the notebook to clone from
        new_title: Title for the new notebook
        exclude_types: Lowercased ``source_type_name`` values to skip
            (e.g., ["url", "note"]). Pass ``None`` for default binary exclude;
            ``[]`` to attempt all types.
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
