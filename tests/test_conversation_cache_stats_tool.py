"""세션76: conversation_cache_stats MCP tool.

The tool introspects the running server's in-memory conversation cache
WITHOUT creating a client or triggering auth (peek_client, not get_client).
"""

from unittest.mock import patch

from notebooklm_tools.mcp.tools.server import conversation_cache_stats


def test_returns_inactive_when_no_client():
    """No client instance yet → cache_active False, never creates a client."""
    with patch(
        "notebooklm_tools.mcp.tools.server.peek_client", return_value=None
    ) as peek:
        result = conversation_cache_stats()
    peek.assert_called_once()
    assert result["status"] == "success"
    assert result["cache_active"] is False
    assert "message" in result


def test_merges_stats_when_client_active():
    """Active client → cache_active True + the core cache stats merged in."""

    class FakeClient:
        def get_conversation_cache_stats(self):
            return {
                "conversations": 2,
                "total_turns": 5,
                "max_turns_per_conversation": 50,
                "max_conversations": 500,
                "max_chars_per_turn": 100_000,
                "cache_created_at": 1234567890,
                "cache_age_seconds": 42,
            }

    with patch(
        "notebooklm_tools.mcp.tools.server.peek_client", return_value=FakeClient()
    ):
        result = conversation_cache_stats()
    assert result["status"] == "success"
    assert result["cache_active"] is True
    assert result["conversations"] == 2
    assert result["total_turns"] == 5
    assert result["cache_age_seconds"] == 42
    assert result["cache_created_at"] == 1234567890
