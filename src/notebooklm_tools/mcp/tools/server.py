"""Server tools - Server info and version checking."""

import json
import urllib.request
from typing import Any, cast

from notebooklm_tools import __version__

from ._utils import logged_tool, peek_client


def _get_latest_pypi_version() -> str | None:
    """Fetch the latest version from PyPI.

    Returns:
        Latest version string or None if fetch fails.
    """
    try:
        url = "https://pypi.org/pypi/notebooklm-mcp-cli/json"
        req = urllib.request.Request(url, headers={"User-Agent": "notebooklm-mcp-cli"})
        with urllib.request.urlopen(req, timeout=2) as response:
            data = cast(dict[str, Any], json.loads(response.read().decode()))
            info = data.get("info")
            if isinstance(info, dict):
                version = info.get("version")
                if isinstance(version, str):
                    return version
    except Exception:
        return None
    return None


def _compare_versions(current: str, latest: str) -> bool:
    """Compare version strings to determine if an update is available.

    Returns:
        True if latest is greater than current.
    """
    try:
        # Simple comparison: split by dots and compare numerically
        current_parts = [int(x) for x in current.split(".")]
        latest_parts = [int(x) for x in latest.split(".")]
        return latest_parts > current_parts
    except (ValueError, AttributeError):
        return False


@logged_tool()
def server_info() -> dict[str, Any]:
    """Get server version and check for updates.

    AI assistants: If update_available is True, inform the user that a new
    version is available and suggest updating with the provided command.

    Returns:
        dict with version info:
        - version: Current installed version
        - latest_version: Latest version on PyPI (or None if check failed)
        - update_available: True if a newer version exists
        - update_command: Command to run to update
    """
    latest = _get_latest_pypi_version()
    update_available = False

    if latest:
        update_available = _compare_versions(__version__, latest)

    return {
        "status": "success",
        "version": __version__,
        "latest_version": latest,
        "update_available": update_available,
        "update_command": "uv tool upgrade notebooklm-mcp-cli",
        "pip_update_command": "pip install --upgrade notebooklm-mcp-cli",
    }


@logged_tool()
def conversation_cache_stats() -> dict[str, Any]:
    """Introspect the running MCP server's in-memory conversation cache.

    Reports live usage of the bounded follow-up-query cache and its caps
    (NOTEBOOKLM_CONVERSATION_MAX_TURNS / _MAX_CONVS / _MAX_CHARS_PER_TURN),
    plus cache_age_seconds — how long the current client instance (and thus
    its cache) has lived. reset_client() drops the client only when the
    refresh_auth tool succeeds or the profile switches; in-place Layer 2/3
    (401 reactive) recovery preserves the cache. So a small age means a recent
    explicit reset, not mere idleness.

    Side-effect-free: never creates a client or triggers authentication.
    If no query has run since server start / last auth refresh, returns
    cache_active=False.

    Returns:
        dict with cache_active plus (when active) conversations, total_turns,
        the three cap values, cache_created_at (epoch) and cache_age_seconds.
    """
    client = peek_client()
    if client is None:
        return {
            "status": "success",
            "cache_active": False,
            "message": (
                "No client instance yet — no query has run since server start "
                "or the last auth refresh, so the conversation cache is empty."
            ),
        }
    return {
        "status": "success",
        "cache_active": True,
        **client.get_conversation_cache_stats(),
    }
