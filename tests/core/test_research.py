#!/usr/bin/env python3
"""Tests for ResearchMixin."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from notebooklm_tools.core.base import BaseClient
from notebooklm_tools.core.research import ResearchMixin

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TestResearchMixinImport:
    """Test that ResearchMixin can be imported correctly."""

    def test_research_mixin_import(self):
        """Test that ResearchMixin can be imported."""
        assert ResearchMixin is not None

    def test_research_mixin_inherits_base(self):
        """Test that ResearchMixin inherits from BaseClient."""
        assert issubclass(ResearchMixin, BaseClient)

    def test_research_mixin_has_methods(self):
        """Test that ResearchMixin has expected methods."""
        expected_methods = [
            "start_research",
            "poll_research",
            "import_research_sources",
            "_parse_research_sources",
        ]
        for method in expected_methods:
            assert hasattr(ResearchMixin, method), f"Missing method: {method}"


class TestResearchMixinMethods:
    """Test ResearchMixin method behavior."""

    def test_start_research_validates_source(self):
        """Test that start_research validates source parameter."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")

        with pytest.raises(ValueError, match="Invalid source"):
            mixin.start_research("notebook-id", "query", source="invalid")

    def test_start_research_validates_mode(self):
        """Test that start_research validates mode parameter."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")

        with pytest.raises(ValueError, match="Invalid mode"):
            mixin.start_research("notebook-id", "query", mode="invalid")

    def test_start_research_validates_deep_with_drive(self):
        """Test that start_research rejects deep mode with drive source."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")

        with pytest.raises(ValueError, match="Deep Research only supports Web"):
            mixin.start_research("notebook-id", "query", source="drive", mode="deep")

    def test_parse_research_sources_handles_empty(self):
        """Test that _parse_research_sources handles empty input."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")

        result = mixin._parse_research_sources([])

        assert result == []

    def test_parse_research_sources_handles_none_input(self):
        """Test that _parse_research_sources handles non-list input."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")

        result = mixin._parse_research_sources(None)

        assert result == []

    def test_import_research_sources_returns_empty_for_no_sources(self):
        """Test that import_research_sources returns empty for no sources."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")

        result = mixin.import_research_sources("notebook-id", "task-id", [])

        assert result == []


class TestNewNLMSourceShape:
    """Regression — 260523 capture: NLM deep import payload (RPC LBwxtb).

    Captured live from Brave DevTools after clicking the Import button on
    notebook d1675c65. The browser frontend uses a 5-slot LBwxtb param array
    where slot 0 is a research-mode config envelope and source_array contains
    a deep-report entry at index 0 followed by web sources. See
    tests/fixtures/research_import_lbwxtb_deep_260523.json.
    """

    def _load_fixture(self):
        path = FIXTURE_DIR / "research_import_lbwxtb_deep_260523.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_parse_new_deep_report_shape_extracts_body(self):
        """src[1] is [title, body] → parser extracts both, not str title."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        # Real NLM shape (260523): deep report packaged as one source row.
        deep_report = [
            None,
            ["Report Title", "# Markdown body\n\nFull report content here."],
            None,
            3,
            None,
            None,
            None,
            None,
            None,
            None,
            3,
        ]

        parsed = mixin._parse_research_sources([deep_report])

        assert len(parsed) == 1
        assert parsed[0]["title"] == "Report Title"
        assert parsed[0]["body"] == "# Markdown body\n\nFull report content here."
        assert parsed[0]["result_type"] == 3
        assert parsed[0]["url"] == ""

    def test_parse_new_web_source_shape(self):
        """src[2] is [url, title] → parser extracts cleanly."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        web_src = [None, None, ["https://example.com/a", "Article A"]] + [None] * 7 + [2]

        parsed = mixin._parse_research_sources([web_src])

        assert len(parsed) == 1
        assert parsed[0]["url"] == "https://example.com/a"
        assert parsed[0]["title"] == "Article A"
        assert parsed[0]["result_type"] == 2

    def test_parse_handles_mixed_deep_plus_web_sources(self):
        """Real fixture: deep_report at idx 0 + web sources following."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        fixture = self._load_fixture()
        source_rows = fixture["params"][4]

        parsed = mixin._parse_research_sources(source_rows)

        assert len(parsed) == len(source_rows)
        # First row: deep report with body
        assert parsed[0].get("body"), "deep report body must be extracted"
        assert parsed[0]["result_type"] == 3
        # Remaining: web sources with URLs
        for entry in parsed[1:]:
            assert entry["url"].startswith("https://"), entry
            assert entry["result_type"] == 2

    def test_import_builds_slot_0_envelope(self):
        """params slot 0 must be the captured deep-config envelope, not None."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        captured_params = None

        def capture_rpc(rpc_id, params, *args, **kwargs):
            nonlocal captured_params
            captured_params = params
            return None

        sources = [
            {
                "url": "https://example.com/x",
                "title": "X",
                "result_type": 1,
            }
        ]

        with patch.object(mixin, "_call_rpc", side_effect=capture_rpc):
            mixin.import_research_sources("nb-id", "task-id", sources)

        assert captured_params is not None
        # 5 slots: [config, [1], task_id, notebook_id, source_array]
        assert len(captured_params) == 5
        assert captured_params[0] == [
            2,
            None,
            None,
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ], "slot 0 must match captured deep-config envelope"
        assert captured_params[1] == [1]
        assert captured_params[2] == "task-id"
        assert captured_params[3] == "nb-id"

    def test_import_deep_report_with_body_emits_report_source_row(self):
        """Deep report (result_type=3 + body) must build the [title, body] row."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        captured = {}

        def capture(rpc_id, params, *args, **kwargs):
            captured["params"] = params
            return None

        sources = [
            {
                "url": "",
                "title": "Report Title",
                "body": "# Body content",
                "result_type": 3,
            },
            {"url": "https://ex.com/a", "title": "A", "result_type": 1},
        ]
        with patch.object(mixin, "_call_rpc", side_effect=capture):
            mixin.import_research_sources("nb", "task", sources)

        source_array = captured["params"][4]
        assert len(source_array) == 2
        # First row: deep report shape with body
        deep_row = source_array[0]
        assert deep_row[0] is None
        assert deep_row[1] == ["Report Title", "# Body content"]
        assert deep_row[3] == 3
        assert deep_row[10] == 3
        # Second row: web source
        web_row = source_array[1]
        assert web_row[2] == ["https://ex.com/a", "A"]
        assert web_row[10] == 2

    def test_poll_injects_report_body_into_first_deep_report_source(self):
        """When NLM returns body in separate report field, inject it into
        the first deep-report source so import can package it. Legacy
        deep-research format keeps title at src[1] (str), so the parsed
        entry has no body until poll_research injects it from the
        out-of-band report field."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        # Legacy deep format: title-only at src[1], report body buried at src[6][0].
        report_md = "# Deep Report\n\nFull markdown body content."
        sources_data = [
            [
                None,                 # 0
                "Report Title",       # 1: title string only (legacy shape)
                None,                 # 2
                5,                    # 3: result_type=5
                None, None,           # 4-5
                [report_md, "extra"], # 6: report body lives here in legacy format
            ],
            [None, None, ["https://ex.com/a", "Article A"]] + [None] * 7 + [2],
        ]

        # Build the response shape poll_research expects
        task_info = [None, ["query", 1], 5, [sources_data, ""], 2]
        api_response = [[["task-id", task_info]]]

        with patch.object(mixin, "_call_rpc", return_value=api_response):
            result = mixin.poll_research("nb-id", target_task_id="task-id")

        assert result is not None
        assert result["status"] == "completed"
        assert result["report"] == report_md
        # First entry should have body injected from the report field
        deep_entry = result["sources"][0]
        assert deep_entry["result_type"] == 5
        assert deep_entry["body"] == report_md

    def test_import_skips_legacy_deep_report_without_body(self):
        """Legacy deep_report (type=5) without body has nothing to send → skip."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        captured = {}

        def capture(rpc_id, params, *args, **kwargs):
            captured["params"] = params
            return None

        sources = [
            {"url": "", "title": "Empty", "result_type": 5},
            {"url": "https://ex.com/a", "title": "A", "result_type": 1},
        ]
        with patch.object(mixin, "_call_rpc", side_effect=capture):
            mixin.import_research_sources("nb", "task", sources)

        source_array = captured["params"][4]
        # Only the web source survives
        assert len(source_array) == 1
        assert source_array[0][2] == ["https://ex.com/a", "A"]


class TestPollResearchMultiTaskFallback:
    """Test Issue #106: poll_research should not return None for multi-task notebooks."""

    def _build_task_data(self, task_id, query, status_code=2, mode=1):
        """Build a mock task_data list as returned by the API.

        status_code: 1=in_progress, 2=completed, 6=imported
        mode: 1=fast, 5=deep
        """
        return [
            task_id,
            [None, [query, 1], mode, [[], "summary"], status_code],
        ]

    @patch.object(ResearchMixin, "_get_client")
    @patch.object(ResearchMixin, "_build_request_body", return_value="body")
    @patch.object(ResearchMixin, "_build_url", return_value="http://test")
    @patch.object(ResearchMixin, "_parse_response")
    @patch.object(ResearchMixin, "_extract_rpc_result")
    def test_multi_task_mutated_id_returns_most_recent(
        self, mock_extract, mock_parse, mock_url, mock_body, mock_get_client
    ):
        """When target_task_id doesn't match any task in a multi-task notebook,
        poll_research should return the most recent task, not None."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_get_client.return_value.post.return_value = mock_response

        # Simulate 2 tasks: old fast + mutated deep
        mock_extract.return_value = [
            self._build_task_data("fast-task-id", "fast query", status_code=2),
            self._build_task_data("mutated-deep-id", "deep query", status_code=2, mode=5),
        ]

        result = mixin.poll_research("nb-1", target_task_id="original-deep-id")

        # Should NOT return None — should fall back to the most recent task
        assert result is not None
        assert result["task_id"] == "fast-task-id"

    @patch.object(ResearchMixin, "_get_client")
    @patch.object(ResearchMixin, "_build_request_body", return_value="body")
    @patch.object(ResearchMixin, "_build_url", return_value="http://test")
    @patch.object(ResearchMixin, "_parse_response")
    @patch.object(ResearchMixin, "_extract_rpc_result")
    def test_multi_task_prefers_in_progress(
        self, mock_extract, mock_parse, mock_url, mock_body, mock_get_client
    ):
        """When multiple tasks exist and target_task_id doesn't match,
        an in-progress task should be preferred over a completed one."""
        mixin = ResearchMixin(cookies={"test": "cookie"}, csrf_token="test")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_get_client.return_value.post.return_value = mock_response

        # Simulate: completed fast task + in-progress deep task
        mock_extract.return_value = [
            self._build_task_data("fast-task-id", "fast query", status_code=2),
            self._build_task_data("deep-task-id", "deep query", status_code=1, mode=5),
        ]

        result = mixin.poll_research("nb-1", target_task_id="original-deep-id")

        assert result is not None
        assert result["task_id"] == "deep-task-id"
        assert result["status"] == "in_progress"
