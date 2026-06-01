#!/usr/bin/env python3
"""Research mixin for NotebookLM client.

This module provides the ResearchMixin class which handles all research
operations (web search, Drive search, and source discovery).
"""

import logging
import time

from . import constants
from .base import BaseClient
from .errors import RPCError
from .sources import SOURCE_LIMIT_GUARD

logger = logging.getLogger(__name__)


class ResearchMixin(BaseClient):
    """Mixin providing research operations.

    Methods:
        - start_research: Start a research session (web/drive search)
        - poll_research: Poll for research results
        - import_research_sources: Import discovered sources into notebook
    """

    # =========================================================================
    # Research Operations
    # =========================================================================

    def start_research(
        self,
        notebook_id: str,
        query: str,
        source: str = "web",
        mode: str = "fast",
    ) -> dict | None:
        """Start a research session to discover sources.

        Args:
            notebook_id: The notebook UUID
            query: The search query
            source: 'web' or 'drive'
            mode: 'fast' (~30s, ~10 sources) or 'deep' (~5min, ~40 sources, web only)

        Returns:
            Dict with task_id, report_id, notebook_id, query, source, mode
        """
        # Validate inputs
        source_lower = source.lower()
        mode_lower = mode.lower()

        if source_lower not in ("web", "drive"):
            raise ValueError(f"Invalid source '{source}'. Use 'web' or 'drive'.")

        if mode_lower not in ("fast", "deep"):
            raise ValueError(f"Invalid mode '{mode}'. Use 'fast' or 'deep'.")

        if mode_lower == "deep" and source_lower == "drive":
            raise ValueError("Deep Research only supports Web sources. Use mode='fast' for Drive.")

        # Map to internal constants
        source_type = (
            self.RESEARCH_SOURCE_WEB if source_lower == "web" else self.RESEARCH_SOURCE_DRIVE
        )

        if mode_lower == "fast":
            # Fast Research: Ljjv0c
            # NLM 웹 baseline (260512 캡쳐): slot2 v4 nested
            # [[query, 1], [2, null, null, [1, null×10, [1]]], 1, notebook_id]
            params = [
                [query, source_type],
                [2, None, None, [1, None, None, None, None, None, None, None, None, None, None, [1]]],
                1,
                notebook_id,
            ]
            rpc_id = self.RPC_START_FAST_RESEARCH
        else:
            # Deep Research: QA9ei
            params = [None, [1], [query, source_type], 5, notebook_id]
            rpc_id = self.RPC_START_DEEP_RESEARCH

        result = self._call_rpc(rpc_id, params, path=f"/notebook/{notebook_id}")

        if result and isinstance(result, list) and len(result) > 0:
            task_id = result[0]
            report_id = result[1] if len(result) > 1 else None

            return {
                "task_id": task_id,
                "report_id": report_id,
                "notebook_id": notebook_id,
                "query": query,
                "source": source_lower,
                "mode": mode_lower,
            }
        return None

    def poll_research(
        self, notebook_id: str, target_task_id: str | None = None, target_query: str | None = None
    ) -> dict | None:
        """Poll for research results.

        Call this repeatedly until status is "completed".

        Args:
            notebook_id: The notebook UUID
            target_task_id: Optional specific task ID to poll for
            target_query: Optional query text for fallback matching when task_id
                changes (deep research may mutate task_id internally).
                Contributed by @saitrogen (PR #15).

        Returns:
            Dict with status, sources, and summary when complete
        """
        # Poll params: [null, null, "notebook_id"]
        params = [None, None, notebook_id]
        result = self._call_rpc(self.RPC_POLL_RESEARCH, params, f"/notebook/{notebook_id}")

        if not result or not isinstance(result, list) or len(result) == 0:
            return {"status": "no_research", "message": "No active research found"}

        # Unwrap the outer array to get [[task_id, task_info, status], [ts1], [ts2]]
        if isinstance(result[0], list) and len(result[0]) > 0 and isinstance(result[0][0], list):
            result = result[0]

        # Result may contain multiple research tasks - find the most recent/active one
        research_tasks = []

        for task_data in result:
            # task_data structure: [task_id, task_info] (only 2 elements for deep research)
            if not isinstance(task_data, list) or len(task_data) < 2:
                continue

            task_id = task_data[0]
            task_info = task_data[1] if len(task_data) > 1 else None

            # Skip timestamp arrays (task_id should be a UUID string, not an int)
            if not isinstance(task_id, str):
                continue

            if not task_info or not isinstance(task_info, list):
                continue

            # Parse task info structure:
            # Note: status is at task_info[4], NOT task_data[2] (which is a timestamp)
            query_info = task_info[1] if len(task_info) > 1 else None
            research_mode = task_info[2] if len(task_info) > 2 else None
            sources_and_summary = task_info[3] if len(task_info) > 3 else []
            status_code = task_info[4] if len(task_info) > 4 else None

            query_text = query_info[0] if query_info and len(query_info) > 0 else ""
            source_type = query_info[1] if query_info and len(query_info) > 1 else 1

            sources_data = []
            summary = ""
            report = ""

            # Handle different structures for fast vs deep research
            if isinstance(sources_and_summary, list) and len(sources_and_summary) >= 1:
                # sources_and_summary[0] is always the sources list
                sources_data = (
                    sources_and_summary[0] if isinstance(sources_and_summary[0], list) else []
                )
                # For fast research, summary may be at [1]
                if len(sources_and_summary) >= 2 and isinstance(sources_and_summary[1], str):
                    summary = sources_and_summary[1]

            # Parse sources - structure differs between fast and deep research
            sources = self._parse_research_sources(sources_data)

            # Extract report from deep research sources
            for src in sources_data:
                if (
                    isinstance(src, list)
                    and len(src) > 6
                    and isinstance(src[6], list)
                    and len(src[6]) > 0
                ) and isinstance(src[6][0], str):
                    report = src[6][0]
                    break

            # Inject report body into the first deep-report source row so the
            # importer can package it as a source (mirrors NLM browser behavior
            # — manual "Import" click sends the deep report itself as source 0).
            if report:
                for src_entry in sources:
                    if src_entry.get("result_type") in (3, 5) and not src_entry.get("body"):
                        src_entry["body"] = report
                        break

            # Determine status (1 = in_progress, 2 = completed, 6 = imported/completed)
            status = "completed" if status_code in (2, 6) else "in_progress"

            research_tasks.append(
                {
                    "task_id": task_id,
                    "status": status,
                    "query": query_text,
                    "source_type": "web" if source_type == 1 else "drive",
                    "mode": "deep" if research_mode == 5 else "fast",
                    "sources": sources,
                    "source_count": len(sources),
                    "summary": summary,
                    "report": report,  # Deep research report (markdown)
                }
            )

        if not research_tasks:
            return {"status": "no_research", "message": "No active research found"}

        # If target_task_id provided, find the specific task
        if target_task_id:
            for task in research_tasks:
                if task["task_id"] == target_task_id:
                    return task
            # Fallback to query matching (PR #15 - @saitrogen)
            # Deep research may mutate task_id internally
            if target_query:
                for task in research_tasks:
                    if task.get("query", "").lower() == target_query.lower():
                        return task
            # Fallback: deep research mutates task_id internally, so the
            # ID returned by start_research() won't match the polled ID.
            # If there's exactly one task, it's safe to return it. (Issue #69)
            if len(research_tasks) == 1:
                return research_tasks[0]
            # Multi-task notebooks: deep research may mutate task_id internally,
            # so ID returned by start_research() won't match the polled ID.
            # Best-effort: prefer any in-progress task, then most recent. (Issue #106)
            for task in research_tasks:
                if task.get("status") == "in_progress":
                    return task
            return research_tasks[0]

        # If only target_query provided (no task_id), match by query
        if target_query:
            for task in research_tasks:
                if task.get("query", "").lower() == target_query.lower():
                    return task

        # Return the most recent (first) task if no filters specified
        return research_tasks[0]

    def _parse_research_sources(self, sources_data: list) -> list[dict]:
        """Parse sources from research response.

        Handles both fast and deep research source formats.

        New NLM structure (260523 LBwxtb capture, deep mode):
            deep report: [None, [title, body], None, 3, None×6, 3]
            web source : [None, None, [url, title], None×7, 2]
        Legacy structures retained as fallback for fast mode and back-compat.
        """
        sources = []
        if not isinstance(sources_data, list) or len(sources_data) == 0:
            return sources

        for idx, src in enumerate(sources_data):
            if not isinstance(src, list) or len(src) < 2:
                continue

            # New NLM deep-report shape: src[0]=None, src[1]=[title, body]
            if (
                src[0] is None
                and isinstance(src[1], list)
                and len(src[1]) >= 2
                and isinstance(src[1][0], str)
                and isinstance(src[1][1], str)
            ):
                title = src[1][0]
                body = src[1][1]
                result_type = src[3] if len(src) > 3 and isinstance(src[3], int) else 3
                sources.append(
                    {
                        "index": idx,
                        "url": "",
                        "title": title,
                        "description": "",
                        "body": body,
                        "result_type": result_type,
                        "result_type_name": (
                            constants.RESULT_TYPES.get_name(result_type) or "deep_report"
                        ),
                    }
                )
                continue

            # New NLM web-source shape: src[0]=None, src[1]=None, src[2]=[url, title]
            if (
                src[0] is None
                and (len(src) < 2 or src[1] is None)
                and len(src) > 2
                and isinstance(src[2], list)
                and len(src[2]) >= 2
                and isinstance(src[2][0], str)
                and isinstance(src[2][1], str)
            ):
                url = src[2][0]
                title = src[2][1]
                result_type = src[-1] if isinstance(src[-1], int) else 1
                sources.append(
                    {
                        "index": idx,
                        "url": url,
                        "title": title,
                        "description": "",
                        "result_type": result_type,
                        "result_type_name": constants.RESULT_TYPES.get_name(result_type),
                    }
                )
                continue

            # Legacy deep research format (src[1] was the title string directly)
            if src[0] is None and len(src) > 1 and isinstance(src[1], str):
                title = src[1] if isinstance(src[1], str) else ""
                result_type = src[3] if len(src) > 3 and isinstance(src[3], int) else 5

                sources.append(
                    {
                        "index": idx,
                        "url": "",
                        "title": title,
                        "description": "",
                        "result_type": result_type,
                        "result_type_name": constants.RESULT_TYPES.get_name(result_type),
                    }
                )
            elif isinstance(src[0], str) or len(src) >= 3:
                # Legacy fast research format: [url, title, desc, type, ...]
                url = src[0] if isinstance(src[0], str) else ""
                title = src[1] if len(src) > 1 and isinstance(src[1], str) else ""
                desc = src[2] if len(src) > 2 and isinstance(src[2], str) else ""
                result_type = src[3] if len(src) > 3 and isinstance(src[3], int) else 1

                sources.append(
                    {
                        "index": idx,
                        "url": url,
                        "title": title,
                        "description": desc,
                        "result_type": result_type,
                        "result_type_name": constants.RESULT_TYPES.get_name(result_type),
                    }
                )

        return sources

    def import_research_sources(
        self,
        notebook_id: str,
        task_id: str,
        sources: list[dict],
        timeout: float = 300.0,
    ) -> list[dict]:
        """Import research sources into the notebook.

        Args:
            notebook_id: The notebook UUID
            task_id: The research task ID
            sources: List of source dicts with url, title, result_type
            timeout: HTTP timeout in seconds (default: 300s for large notebooks)

        Returns:
            List of imported sources with id and title
        """
        if not sources:
            return []

        # Build source array for import
        source_array = []

        for src in sources:
            url = src.get("url", "")
            title = src.get("title", "Untitled")
            body = src.get("body", "")
            result_type = src.get("result_type", 1)

            # Deep report (result_type=3 + body present, or legacy type=5 still
            # delivered with body): packages the markdown report itself as a
            # source. Real NLM payload (260523 capture): slot[1]=[title, body],
            # slot[3]=3, slot[10]=3.
            if body and result_type in (3, 5):
                source_data = [
                    None,
                    [title, body],
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
                source_array.append(source_data)
                continue

            # Skip purely-empty rows (legacy deep_report with no body, or
            # malformed entries with no URL).
            if not url:
                continue

            if result_type == 1:
                # Web source
                source_data = [
                    None,
                    None,
                    [url, title],
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    2,
                ]
            else:
                # Drive source - extract document ID from URL
                doc_id = None
                if "id=" in url:
                    doc_id = url.split("id=")[-1].split("&")[0]

                if doc_id:
                    mime_types = {
                        2: "application/vnd.google-apps.document",
                        3: "application/vnd.google-apps.presentation",
                        8: "application/vnd.google-apps.spreadsheet",
                    }
                    mime_type = mime_types.get(result_type, "application/vnd.google-apps.document")
                    source_data = [
                        [doc_id, mime_type, 1, title],
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        2,
                    ]
                else:
                    # Fallback to web-style import
                    source_data = [
                        None,
                        None,
                        [url, title],
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        2,
                    ]

            source_array.append(source_data)

        # Slot 0: research-mode config envelope. Captured 260523 from real NLM
        # browser client for a Deep Research import. Matches the inner shape
        # NLM sends with start_research; previous None caused import to drop.
        # 세션46 LBwxtb slot 0 envelope — 절대 변경 금지 (배치3 회귀 가드 #17).
        slot_0 = [2, None, None, [1, None, None, None, None, None, None, None, None, None, [1]]]
        params = [slot_0, [1], task_id, notebook_id, source_array]

        # 배치3 ATOM-5 (upstream 31df628): false-negative reconcile pre-snapshot.
        # NLM이 code 3/9를 accepted-pending / genuine reject 구분 없이 응답 → 사후
        # 폴링으로 신규 source 감지. 세션342 가드: 한도 임계 노트북은 reconcile 스킵.
        pre_sources: list = []
        pre_ids: set = set()
        try:
            pre_sources = self.get_notebook_sources_with_types(notebook_id)  # type: ignore[attr-defined]
            pre_ids = {s["id"] for s in pre_sources if s.get("id")}
        except Exception:
            pass

        try:
            result = self._call_rpc(
                self.RPC_IMPORT_RESEARCH, params, f"/notebook/{notebook_id}", timeout=timeout
            )
        except RPCError as e:
            if e.error_code not in (3, 9):
                raise
            # 세션342 가드: NLM Pro 한도 임계 노트북 reconcile 스킵
            if len(pre_sources) >= SOURCE_LIMIT_GUARD:
                logger.warning(
                    "Source limit guard hit (%d >= %d) for research import: skipping reconcile",
                    len(pre_sources),
                    SOURCE_LIMIT_GUARD,
                )
                raise
            # Exp backoff polling — 신규 source 검출
            for attempt in range(3):
                time.sleep(min(1.5 * (2 ** attempt), 6.0))
                try:
                    post_sources = self.get_notebook_sources_with_types(notebook_id)  # type: ignore[attr-defined]
                except Exception:
                    continue
                new_sources = [
                    s for s in post_sources if s.get("id") and s["id"] not in pre_ids
                ]
                if new_sources:
                    return [
                        {"id": s["id"], "title": s.get("title", "Untitled")}
                        for s in new_sources
                    ]
            raise

        imported_sources = []
        if result and isinstance(result, list):
            # Response is wrapped: [[source1, source2, ...]]
            if (
                len(result) > 0
                and isinstance(result[0], list)
                and len(result[0]) > 0
                and isinstance(result[0][0], list)
            ):
                result = result[0]

            for src_data in result:
                if isinstance(src_data, list) and len(src_data) >= 2:
                    src_id = (
                        src_data[0][0] if src_data[0] and isinstance(src_data[0], list) else None
                    )
                    src_title = src_data[1] if len(src_data) > 1 else "Untitled"
                    if src_id:
                        imported_sources.append({"id": src_id, "title": src_title})

        return imported_sources
