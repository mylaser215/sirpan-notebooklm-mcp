"""SourceMixin - Source management operations.

This mixin provides source-related operations:
- check_source_freshness: Check if Drive source is up-to-date
- sync_drive_source: Sync a Drive source with latest content
- delete_source: Delete a source permanently
- get_notebook_sources_with_types: Get sources with type info
- add_url_source: Add URL/YouTube as source
- add_text_source: Add pasted text as source
- add_drive_source: Add Google Drive document as source
- upload_file: Upload local file via Chrome automation
- get_source_guide: Get AI-generated summary and keywords
- get_source_fulltext: Get raw text content of a source

HTTP resumable upload implementation adapted from notebooklm-py.
"""

import logging
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol, cast

import httpx

from . import constants
from .base import SOURCE_ADD_TIMEOUT, BaseClient
from .errors import RPCError
from .exceptions import FileUploadError, FileValidationError
from .retry import execute_with_retry

logger = logging.getLogger(__name__)


class _NotebookLookupProtocol(Protocol):
    def get_notebook(self, notebook_id: str) -> Any: ...


def _is_note_type(source_type: int | None) -> bool:
    """Return True for source_type codes that are backed by Note RPCs.

    NotebookLM backend stores generated_text (saved AI responses, mind maps)
    as 'Note' objects accessed via Note-specific RPCs (cFji9, cYAfTb, AH0mwd)
    rather than the Source RPCs (hizoJc, b7Wfje, tGMBJ, tr032e). Centralized
    here so future Note types (e.g. mind_map subtype) can be added in one place.
    """
    return source_type == constants.SOURCE_TYPE_GENERATED_TEXT


class SourceMixin(BaseClient):
    """Mixin for source management operations.

    This class inherits from BaseClient and provides all source-related
    operations. It is designed to be composed with other mixins via
    multiple inheritance in the final NotebookLMClient class.
    """

    # Source processing status codes
    SOURCE_STATUS_PROCESSING = 1
    SOURCE_STATUS_READY = 2
    SOURCE_STATUS_ERROR = 3
    SOURCE_STATUS_PREPARING = 5

    # Source types that NotebookLM consistently surfaces as "ready" via
    # status 2. For these, status 3 is a hard processing failure.
    # Audio (10) and unknown/transient (None, 0) types may pass through
    # status 3 on their way to status 2, so we do not raise on 3 for them.
    _NON_AUDIO_TERMINAL_TYPES = frozenset(
        {
            constants.SOURCE_TYPE_PDF,
            constants.SOURCE_TYPE_PASTED_TEXT,
            constants.SOURCE_TYPE_WEB_PAGE,
            constants.SOURCE_TYPE_GENERATED_TEXT,
            constants.SOURCE_TYPE_YOUTUBE,
            constants.SOURCE_TYPE_UPLOADED_FILE,
            constants.SOURCE_TYPE_IMAGE,
            constants.SOURCE_TYPE_WORD_DOC,
        }
    )

    def wait_for_source_ready(
        self,
        notebook_id: str,
        source_id: str,
        timeout: float = 120.0,
        poll_interval: float = 3.0,
    ) -> dict[str, Any]:
        """Wait for a source to finish processing.

        Polls the source status until it becomes READY or times out.

        Note on AUDIO sources (source_type 10): NotebookLM transcribes
        audio in the cloud, and the source moves through several
        intermediate states (5 PREPARING → 1 PROCESSING → 2 READY).
        Empirically, source_type for an uploaded file is also reported
        as 0 ("unknown / not yet classified") for the first few polls
        before settling at 10 (audio) or another type. During those
        early polls the status can briefly read 3 even on a successful
        path. We therefore only raise on status 3 when source_type is
        already a *known terminal* non-audio type (PDF, text, url, etc.)
        — for audio and as-yet-unclassified sources we keep polling and
        let the timeout surface genuine hangs.

        Args:
            notebook_id: Notebook containing the source
            source_id: Source to wait for
            timeout: Max seconds to wait (default 120; for audio
                sources callers typically need to pass a larger value
                — the CLI's `--wait-timeout` flag defaults to 600s)
            poll_interval: Seconds between status checks (default 3)

        Returns:
            The source dict with status='ready'

        Raises:
            TimeoutError: If source doesn't become ready within timeout
            RuntimeError: If source processing fails
        """
        start = time.time()

        while time.time() - start < timeout:
            sources = self.get_notebook_sources_with_types(notebook_id)
            for src in sources:
                if src.get("id") == source_id:
                    status = src.get("status")
                    source_type = src.get("source_type")
                    if status == self.SOURCE_STATUS_READY:
                        return src
                    # Only treat status 3 as a hard failure when the
                    # source has already settled into a known terminal
                    # non-audio type. Audio (10) and not-yet-classified
                    # sources (None / 0) may pass through 3 transiently.
                    if (
                        status == self.SOURCE_STATUS_ERROR
                        and source_type in self._NON_AUDIO_TERMINAL_TYPES
                    ):
                        raise RuntimeError(f"Source {source_id} failed to process")
                    break
            time.sleep(poll_interval)

        raise TimeoutError(f"Source {source_id} not ready after {timeout}s")

    def check_source_freshness(self, source_id: str) -> bool | None:
        """Check if a Drive source is fresh (up-to-date with Google Drive)."""
        params = [None, [source_id], [2]]

        result = self._call_rpc(self.RPC_CHECK_FRESHNESS, params)

        # true = fresh, false = stale
        if result and isinstance(result, list) and len(result) > 0:
            inner = result[0] if result else []
            if isinstance(inner, list) and len(inner) >= 2:
                freshness = inner[1]
                if isinstance(freshness, bool):
                    return freshness
        return None

    def sync_drive_source(self, source_id: str) -> dict[str, Any] | None:
        """Sync a Drive source with the latest content from Google Drive."""
        # Sync params: [null, ["source_id"], [2]]
        params = [None, [source_id], [2]]

        result = self._call_rpc(self.RPC_SYNC_DRIVE, params)

        if result and isinstance(result, list) and len(result) > 0:
            source_data = result[0] if result else []
            if isinstance(source_data, list) and len(source_data) >= 3:
                source_id_result = source_data[0][0] if source_data[0] else None
                title = source_data[1] if len(source_data) > 1 else "Unknown"
                metadata = source_data[2] if len(source_data) > 2 else []

                synced_at = None
                if isinstance(metadata, list) and len(metadata) > 3:
                    sync_info = metadata[3]
                    if isinstance(sync_info, list) and len(sync_info) > 1:
                        ts = sync_info[1]
                        if isinstance(ts, list) and len(ts) > 0:
                            synced_at = ts[0]

                return {
                    "id": source_id_result,
                    "title": title,
                    "synced_at": synced_at,
                }
        return None

    def rename_source(
        self,
        notebook_id: str,
        source_id: str,
        new_title: str,
        *,
        source_type: int | None = None,
    ) -> dict[str, Any] | None:
        """Rename a source in a notebook.

        NotebookLM backend manages 'Source' (external) and 'Note' (internal
        generated_text/mind_map) as separate objects with separate RPCs.
        Renaming uses `b7Wfje` for Source vs `cYAfTb` (update_note) for Note.
        When `source_type` is SOURCE_TYPE_GENERATED_TEXT (=8), this method
        delegates to `update_note` (title-only) so the correct RPC is used.

        Args:
            notebook_id: The notebook containing the source
            source_id: The source UUID to rename
            new_title: The new display title
            source_type: Optional source type code — when 8 (generated_text),
                routes to update_note RPC

        Returns:
            Dict with source_id and title on success, None on failure
        """
        # Route generated_text to the Note update RPC (cYAfTb, title-only)
        if _is_note_type(source_type):
            updated = self.update_note(source_id, title=new_title, notebook_id=notebook_id)
            if updated:
                return {"id": updated["id"], "title": updated["title"]}
            return None

        params = [None, [source_id], [[[new_title]]]]
        path = f"/notebook/{notebook_id}"
        result = self._call_rpc(self.RPC_RENAME_SOURCE, params, path)

        if result and isinstance(result, list) and len(result) > 0:
            source_data = result[0]
            if isinstance(source_data, list) and len(source_data) >= 2:
                returned_id = source_data[0][0] if source_data[0] else source_id
                returned_title = source_data[1] if len(source_data) > 1 else new_title
                return {"id": returned_id, "title": returned_title}
        return None

    def delete_source(
        self,
        source_id: str,
        *,
        notebook_id: str | None = None,
        source_type: int | None = None,
    ) -> bool:
        """Delete a source from a notebook permanently.

        WARNING: This action is IRREVERSIBLE. The source will be permanently
        deleted from the notebook.

        NotebookLM backend manages two distinct object kinds: external 'Source'
        (text/pdf/url/audio/...) and internal 'Note' (generated_text/mind_map).
        Deletion uses different RPCs (tGMBJ vs AH0mwd). When `source_type` is
        SOURCE_TYPE_GENERATED_TEXT (=8) and `notebook_id` is provided, this
        method delegates to `delete_note` so the correct RPC is used.

        Args:
            source_id: The source UUID to delete
            notebook_id: Optional notebook UUID — required for generated_text
                routing
            source_type: Optional source type code — when 8 (generated_text),
                routes to delete_note RPC

        Returns:
            True on success, False on failure
        """
        # Route generated_text to the Note deletion RPC (AH0mwd)
        if _is_note_type(source_type) and notebook_id:
            return self.delete_note(source_id, notebook_id)

        # Standard source deletion via tGMBJ
        # Delete source params: [[["source_id"]], [2]]
        # Note: Extra nesting compared to delete_notebook
        params = [[[source_id]], [2]]

        result = self._call_rpc(self.RPC_DELETE_SOURCE, params)

        # Response is typically [] on success
        return result is not None

    def delete_sources(
        self,
        source_ids: list[str],
        *,
        notebook_id: str | None = None,
    ) -> bool:
        """Delete multiple sources from a notebook in a single request.

        WARNING: This action is IRREVERSIBLE. All specified sources will be
        permanently deleted.

        When `notebook_id` is provided, source types are looked up first and
        generated_text entries are routed to `delete_note` individually while
        regular sources go through the batch tGMBJ RPC.

        Args:
            source_ids: List of source UUIDs to delete
            notebook_id: Optional notebook UUID — enables type-aware routing

        Returns:
            True on success (all deletions succeeded), False otherwise
        """
        if notebook_id:
            # v3 회귀 픽스 (세션310): get_notebook의 metadata[4]가 모든 text source에서 8로
            # 응답되어 SOURCE_TYPE_GENERATED_TEXT 상수와 우연 일치 → sources_meta source_type
            # 신뢰 시 모든 일반 source가 Note로 오분류. list_notes 멤버십을 단일 권위 기준으로
            # 사용 (services/sources.py:_resolve_source_type 참조).
            try:
                note_obj_ids = {
                    n.get("id")
                    for n in self.list_notes(notebook_id)
                    if n.get("id") and n.get("content") is not None
                }
            except Exception:
                note_obj_ids = set()
            note_ids = [sid for sid in source_ids if sid in note_obj_ids]
            regular_ids = [sid for sid in source_ids if sid not in note_obj_ids]

            ok = True
            for nid in note_ids:
                ok = self.delete_note(nid, notebook_id) and ok
            if regular_ids:
                params = [[[sid] for sid in regular_ids], [2]]
                result = self._call_rpc(self.RPC_DELETE_SOURCE, params)
                ok = (result is not None) and ok
            return ok

        # Batch delete params: [[["id1"], ["id2"], ...], [2]]
        params = [[[sid] for sid in source_ids], [2]]

        result = self._call_rpc(self.RPC_DELETE_SOURCE, params)

        # Response is typically [] on success
        return result is not None

    def get_notebook_sources_with_types(self, notebook_id: str) -> list[dict[str, Any]]:
        """Get all sources from a notebook with their type information."""
        notebook_client = cast(_NotebookLookupProtocol, self)
        result = notebook_client.get_notebook(notebook_id)

        sources = []
        # The notebook data is wrapped in an outer array
        if result and isinstance(result, list) and len(result) >= 1:
            notebook_data = result[0] if isinstance(result[0], list) else result
            # Sources are in notebook_data[1]
            sources_data = notebook_data[1] if len(notebook_data) > 1 else []

            if isinstance(sources_data, list):
                for src in sources_data:
                    if isinstance(src, list) and len(src) >= 3:
                        # Source structure: [[id], title, [metadata...], [null, 2]]
                        source_id = src[0][0] if src[0] and isinstance(src[0], list) else None
                        title = src[1] if len(src) > 1 else "Untitled"
                        metadata = src[2] if len(src) > 2 else []

                        source_type = None
                        drive_doc_id = None
                        if isinstance(metadata, list):
                            if len(metadata) > 4:
                                # WARNING (세션310 v3 회귀): NLM 백엔드가 모든 일반 text source의
                                # metadata[4]를 8(SOURCE_TYPE_GENERATED_TEXT 상수와 동일 값)로 응답.
                                # 이 값은 더 이상 라우팅 권위 기준으로 신뢰할 수 없음.
                                # Note vs Source 분기는 services/sources.py:_resolve_source_type
                                # (list_notes 멤버십 + content 교차검증)에서 결정.
                                source_type = metadata[4]
                            # Drive doc info at metadata[0]
                            if len(metadata) > 0 and isinstance(metadata[0], list):
                                drive_doc_id = metadata[0][0] if metadata[0] else None

                        # Google Docs (type 1) and Slides/Sheets (type 2) are stored in Drive
                        # and can be synced if they have a drive_doc_id
                        can_sync = drive_doc_id is not None and source_type in (
                            self.SOURCE_TYPE_GOOGLE_DOCS,
                            self.SOURCE_TYPE_GOOGLE_OTHER,
                        )

                        # Extract URL if available (position 7)
                        url = None
                        if isinstance(metadata, list) and len(metadata) > 7:
                            url_info = metadata[7]
                            if isinstance(url_info, list) and len(url_info) > 0:
                                url = url_info[0]

                        # Extract processing status from src[3][1]
                        # 1=processing, 2=ready, 3=error/done(audio),
                        # 5=preparing. For audio sources (source_type 10)
                        # status 3 is not a hard failure — see
                        # wait_for_source_ready for details.
                        status = self.SOURCE_STATUS_READY  # Default
                        if len(src) > 3 and isinstance(src[3], list) and len(src[3]) > 1:
                            status = src[3][1] if isinstance(src[3][1], int) else status

                        sources.append(
                            {
                                "id": source_id,
                                "title": title,
                                "source_type": source_type,
                                "source_type_name": constants.SOURCE_TYPES.get_name(source_type),
                                "url": url,
                                "drive_doc_id": drive_doc_id,
                                "can_sync": can_sync,
                                "status": status,
                            }
                        )

        return sources

    def add_url_source(
        self,
        notebook_id: str,
        url: str,
        wait: bool = False,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any] | None:
        """Add a URL (website or YouTube) as a source to a notebook.

        Supports automatic fallback between legacy (izAoDd) and new (ozz5Z)
        RPC endpoints. Google is gradually rolling out the new endpoint;
        the first call detects which works and caches the result for the session.

        Args:
            notebook_id: Target notebook ID
            url: URL to add
            wait: If True, block until source is ready
            wait_timeout: Seconds to wait if wait=True (default 120)

        Returns:
            Source dict with id and title, or None on failure
        """
        source_path = f"/notebook/{notebook_id}"

        try:
            # Use cached RPC version if already resolved
            with self._state_lock:
                version = self._source_rpc_version
            if version == "v2":
                result = self._add_url_source_v2(notebook_id, url, source_path)
            elif version == "v1":
                result = self._add_url_source_v1(notebook_id, url, source_path)
            else:
                # First call — try v1, fallback to v2 on INVALID_ARGUMENT
                try:
                    result = self._add_url_source_v1(notebook_id, url, source_path)
                    with self._state_lock:
                        if self._source_rpc_version is None:
                            self._source_rpc_version = "v1"
                except RPCError as e:
                    if e.error_code == 3:
                        # Legacy RPC rejected — try the new endpoint
                        result = self._add_url_source_v2(notebook_id, url, source_path)
                        with self._state_lock:
                            if self._source_rpc_version is None:
                                self._source_rpc_version = "v2"
                    else:
                        raise
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "message": f"Operation timed out after {SOURCE_ADD_TIMEOUT}s but may have succeeded.",
            }

        source_result = self._parse_source_result(result)

        if source_result and wait:
            return self.wait_for_source_ready(notebook_id, source_result["id"], wait_timeout)

        return source_result

    def _add_url_source_v1(self, notebook_id: str, url: str, source_path: str) -> Any:
        """Legacy izAoDd RPC for adding a URL source.

        YouTube and regular URLs use different positions in the params array.
        """
        is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()

        if is_youtube:
            source_data = [None, None, None, None, None, None, None, [url], None, None, 1]
        else:
            source_data = [None, None, [url], None, None, None, None, None, None, None, 1]

        params = [
            [source_data],
            notebook_id,
            [2],
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ]

        return self._call_rpc(
            self.RPC_ADD_SOURCE, params, path=source_path, timeout=SOURCE_ADD_TIMEOUT
        )

    def _add_url_source_v2(self, notebook_id: str, url: str, source_path: str) -> Any:
        """New ozz5Z RPC for adding a URL source (issue #121).

        Google is rolling out this new endpoint which uses a simplified,
        unified structure for all URL types (no YouTube distinction).
        The notebook_id is only passed in the source-path query param,
        not in the request body.

        Payload structure captured from reporter's browser (issue #121):
            [[[null, "<url>", 627], [null*9, [null, null, 1]], 1]]
        The 627 value appears to be a source type code.
        """
        source_data = [
            [None, url, 627],
            [None, None, None, None, None, None, None, None, None, [None, None, 1]],
            1,
        ]
        params = [[source_data]]

        return self._call_rpc(
            self.RPC_ADD_SOURCE_V2, params, path=source_path, timeout=SOURCE_ADD_TIMEOUT
        )

    @staticmethod
    def _parse_source_result(result: Any) -> dict[str, Any] | None:
        """Parse the source creation result from either v1 or v2 RPC response."""
        if result and isinstance(result, list) and len(result) > 0:
            source_list = result[0] if result else []
            if source_list and len(source_list) > 0:
                source_data = source_list[0]
                if not isinstance(source_data, list) or len(source_data) < 1:
                    return None
                source_id = source_data[0][0] if source_data[0] else None
                source_title = source_data[1] if len(source_data) > 1 else "Untitled"
                return {"id": source_id, "title": source_title}
        return None

    def add_url_sources(
        self,
        notebook_id: str,
        urls: list[str],
        wait: bool = False,
        wait_timeout: float = 120.0,
    ) -> list[dict[str, Any]]:
        """Add multiple URLs as sources to a notebook in a single request.

        Supports automatic fallback between legacy (izAoDd) and new (ozz5Z)
        RPC endpoints, using the same try-then-cache pattern as add_url_source.

        Args:
            notebook_id: Target notebook ID
            urls: List of URLs to add
            wait: If True, block until all sources are ready
            wait_timeout: Seconds to wait per source if wait=True (default 120)

        Returns:
            List of source dicts with id and title, or empty list on failure
        """
        source_path = f"/notebook/{notebook_id}"

        try:
            with self._state_lock:
                version = self._source_rpc_version
            if version == "v2":
                result = self._add_url_sources_v2(notebook_id, urls, source_path)
            elif version == "v1":
                result = self._add_url_sources_v1(notebook_id, urls, source_path)
            else:
                # First call — try v1, fallback to v2 on INVALID_ARGUMENT
                try:
                    result = self._add_url_sources_v1(notebook_id, urls, source_path)
                    with self._state_lock:
                        if self._source_rpc_version is None:
                            self._source_rpc_version = "v1"
                except RPCError as e:
                    if e.error_code == 3:
                        result = self._add_url_sources_v2(notebook_id, urls, source_path)
                        with self._state_lock:
                            if self._source_rpc_version is None:
                                self._source_rpc_version = "v2"
                    else:
                        raise
        except httpx.TimeoutException:
            return [
                {
                    "status": "timeout",
                    "message": f"Operation timed out after {SOURCE_ADD_TIMEOUT}s but may have succeeded.",
                }
            ]

        source_results = self._parse_source_results(result)

        if source_results and wait:
            waited_results = []
            for sr in source_results:
                if sr.get("id"):
                    waited = self.wait_for_source_ready(notebook_id, sr["id"], wait_timeout)
                    waited_results.append(waited or sr)
                else:
                    waited_results.append(sr)
            return waited_results

        return source_results

    def _add_url_sources_v1(self, notebook_id: str, urls: list[str], source_path: str) -> Any:
        """Legacy izAoDd RPC for adding multiple URL sources."""
        source_data_list = []
        for url in urls:
            is_youtube = "youtube.com" in url.lower() or "youtu.be" in url.lower()
            if is_youtube:
                source_data = [None, None, None, None, None, None, None, [url], None, None, 1]
            else:
                source_data = [None, None, [url], None, None, None, None, None, None, None, 1]
            source_data_list.append(source_data)

        params = [
            source_data_list,
            notebook_id,
            [2],
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ]

        return self._call_rpc(
            self.RPC_ADD_SOURCE, params, path=source_path, timeout=SOURCE_ADD_TIMEOUT
        )

    def _add_url_sources_v2(self, notebook_id: str, urls: list[str], source_path: str) -> Any:
        """New ozz5Z RPC for adding multiple URL sources (issue #121)."""
        source_data_list = []
        for url in urls:
            source_data = [
                [None, url, 627],
                [None, None, None, None, None, None, None, None, None, [None, None, 1]],
                1,
            ]
            source_data_list.append(source_data)

        params = [source_data_list]

        return self._call_rpc(
            self.RPC_ADD_SOURCE_V2, params, path=source_path, timeout=SOURCE_ADD_TIMEOUT
        )

    @staticmethod
    def _parse_source_results(result: Any) -> list[dict[str, Any]]:
        """Parse multiple source creation results from either v1 or v2 RPC response."""
        source_results: list[dict[str, Any]] = []
        if result and isinstance(result, list) and len(result) > 0:
            source_list = result[0] if result else []
            if isinstance(source_list, list):
                for source_data in source_list:
                    if isinstance(source_data, list) and len(source_data) > 1:
                        source_id = source_data[0][0] if source_data[0] else None
                        source_title = source_data[1] if len(source_data) > 1 else "Untitled"
                        source_results.append({"id": source_id, "title": source_title})
        return source_results

    def add_text_source(
        self,
        notebook_id: str,
        text: str,
        title: str = "Pasted Text",
        wait: bool = False,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any] | None:
        """Add pasted text as a source to a notebook.

        Args:
            notebook_id: Target notebook ID
            text: Text content to add
            title: Title for the source
            wait: If True, block until source is ready
            wait_timeout: Seconds to wait if wait=True (default 120)
        """
        source_path = f"/notebook/{notebook_id}"
        normalized_text = textwrap.dedent(text).strip()
        text_variants = [text]
        if normalized_text and normalized_text != text:
            text_variants.append(normalized_text)

        result = None
        for text_payload in text_variants:
            source_data = [
                None,
                [title, text_payload],
                None,
                2,
                None,
                None,
                None,
                None,
                None,
                None,
                1,
            ]
            params = [
                [source_data],
                notebook_id,
                [2],
                [1, None, None, None, None, None, None, None, None, None, [1]],
            ]
            try:
                result = self._call_rpc(
                    self.RPC_ADD_SOURCE, params, path=source_path, timeout=SOURCE_ADD_TIMEOUT
                )
                break
            except httpx.TimeoutException:
                return {
                    "status": "timeout",
                    "message": f"Operation timed out after {SOURCE_ADD_TIMEOUT}s.",
                }
            except RPCError as e:
                if e.error_code == 9 and text_payload != normalized_text:
                    time.sleep(0.25)
                    continue
                raise

        source_result = None
        if result and isinstance(result, list) and len(result) > 0:
            source_list = result[0] if result else []
            if source_list and len(source_list) > 0:
                source_data = source_list[0]
                source_id = source_data[0][0] if source_data[0] else None
                source_title = source_data[1] if len(source_data) > 1 else title
                source_result = {"id": source_id, "title": source_title}

        if source_result and wait:
            source_id = source_result.get("id")
            if isinstance(source_id, str):
                return self.wait_for_source_ready(notebook_id, source_id, wait_timeout)

        return source_result

    def add_drive_source(
        self,
        notebook_id: str,
        document_id: str,
        title: str,
        mime_type: str = "application/vnd.google-apps.document",
        wait: bool = False,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any] | None:
        """Add a Google Drive document as a source to a notebook.

        Args:
            notebook_id: Target notebook ID
            document_id: Google Drive document ID
            title: Title for the source
            mime_type: MIME type of the Drive doc
            wait: If True, block until source is ready
            wait_timeout: Seconds to wait if wait=True (default 120)
        """
        source_data = [
            [document_id, mime_type, 1, title],
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            1,
        ]
        params = [
            [source_data],
            notebook_id,
            [2],
            [1, None, None, None, None, None, None, None, None, None, [1]],
        ]
        source_path = f"/notebook/{notebook_id}"

        try:
            result = self._call_rpc(
                self.RPC_ADD_SOURCE, params, path=source_path, timeout=SOURCE_ADD_TIMEOUT
            )
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "message": f"Operation timed out after {SOURCE_ADD_TIMEOUT}s.",
            }

        source_result = None
        if result and isinstance(result, list) and len(result) > 0:
            source_list = result[0] if result else []
            if source_list and len(source_list) > 0:
                source_data = source_list[0]
                source_id = source_data[0][0] if source_data[0] else None
                source_title = source_data[1] if len(source_data) > 1 else title
                source_result = {"id": source_id, "title": source_title}

        if source_result and wait:
            source_id = source_result.get("id")
            if isinstance(source_id, str):
                return self.wait_for_source_ready(notebook_id, source_id, wait_timeout)

        return source_result

    def _register_file_source(self, notebook_id: str, filename: str) -> str:
        """Register a file source intent and get SOURCE_ID.

        Step 1 of the resumable upload protocol.

        Args:
            notebook_id: The notebook to add the source to
            filename: The name of the file being uploaded

        Returns:
            The SOURCE_ID for the upload session

        Raises:
            FileUploadError: If registration fails
        """
        # Params: [[filename]], notebook_id, [2, None, None, [options]]
        # NLM 웹의 o4cbdc RPC payload 구조와 1:1 일치 (v4 결함 픽스 검증):
        # 3 top-level slots, 마지막은 nested array로 [2, null, null, [1, null×10, [1]]].
        # 이전 4-slot 분리 구조는 markdown 파서 라우팅 실패의 원인 후보.
        params = [
            [[filename]],
            notebook_id,
            [
                2,
                None,
                None,
                [1, None, None, None, None, None, None, None, None, None, None, [1]],
            ],
        ]

        source_path = f"/notebook/{notebook_id}"
        result = self._call_rpc(self.RPC_ADD_SOURCE_FILE, params, path=source_path, timeout=60.0)

        # Extract SOURCE_ID from nested response
        def extract_id(data: Any) -> str | None:
            if isinstance(data, str):
                return data
            if isinstance(data, list) and len(data) > 0:
                return extract_id(data[0])
            return None

        if result and isinstance(result, list):
            source_id = extract_id(result)
            if source_id:
                return source_id

        raise FileUploadError(filename, "Failed to get SOURCE_ID from registration response")

    def _start_resumable_upload(
        self,
        notebook_id: str,
        filename: str,
        file_size: int,
        source_id: str,
    ) -> str:
        """Start a resumable upload session and get the upload URL.

        Step 2 of the resumable upload protocol.

        Args:
            notebook_id: The notebook ID
            filename: The filename
            file_size: Size of file in bytes
            source_id: The SOURCE_ID from step 1

        Returns:
            The upload URL for step 3

        Raises:
            FileUploadError: If starting the upload session fails
        """
        import json

        url = f"{self._get_upload_url()}?authuser=0"
        cookies = self._get_httpx_cookies()

        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Origin": self._get_base_url(),
            "Referer": f"{self._get_base_url()}/",
            "x-goog-authuser": "0",
            "x-goog-upload-command": "start",
            "x-goog-upload-header-content-length": str(file_size),
            "x-goog-upload-protocol": "resumable",
        }

        body = json.dumps(
            {
                "PROJECT_ID": notebook_id,
                "SOURCE_NAME": filename,
                "SOURCE_ID": source_id,
            },
            ensure_ascii=False,
        )

        with httpx.Client(timeout=60.0, cookies=cookies) as client:

            def _do_request() -> httpx.Response:
                resp = client.post(url, headers=headers, content=body)
                resp.raise_for_status()
                return resp

            response = execute_with_retry(_do_request)

            upload_url = response.headers.get("x-goog-upload-url")
            if not upload_url:
                raise FileUploadError(filename, "Failed to get upload URL from response headers")

            return cast(str, upload_url)

    def _upload_file_streaming(self, upload_url: str, file_path: Path) -> None:
        """Stream upload file content to the resumable upload URL.

        Step 3 of the resumable upload protocol. Uses streaming to
        avoid loading the entire file into memory.

        Args:
            upload_url: The upload URL from step 2
            file_path: Path to the file to upload

        Raises:
            FileUploadError: If the upload fails
        """
        cookies = self._get_httpx_cookies()

        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Origin": self._get_base_url(),
            "Referer": f"{self._get_base_url()}/",
            "x-goog-authuser": "0",
            "x-goog-upload-command": "upload, finalize",
            "x-goog-upload-offset": "0",
        }

        # Generator for streaming file content
        def file_stream() -> Iterator[bytes]:
            with open(file_path, "rb") as f:
                while chunk := f.read(65536):  # 64KB chunks
                    yield chunk

        with httpx.Client(timeout=300.0, cookies=cookies) as client:

            def _do_upload() -> httpx.Response:
                resp = client.post(upload_url, headers=headers, content=file_stream())
                resp.raise_for_status()
                return resp

            execute_with_retry(_do_upload)

    def add_file(
        self,
        notebook_id: str,
        file_path: str | Path,
        wait: bool = False,
        wait_timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Add a local file as a source using resumable upload.

        Uses Google's resumable upload protocol:
        1. Register source intent with RPC → get SOURCE_ID
        2. Start upload session with SOURCE_ID → get upload URL
        3. Stream upload file content (memory-efficient for large files)

        Supported file types: PDF, TXT, MD, DOCX, CSV, MP3, M4A, WAV, AAC, OGG, OPUS, MP4, JPG, PNG, GIF, WEBP

        Args:
            notebook_id: The notebook ID to add the source to
            file_path: Path to the local file to upload
            wait: If True, poll until source is processed (default: False)
            wait_timeout: Max seconds to wait if wait=True (default 120;
                audio file uploads typically need a larger value — the
                CLI's `--wait-timeout` flag defaults to 600s)

        Returns:
            dict with 'id' and 'title' of the created source

        Raises:
            FileValidationError: If file doesn't exist or is invalid
            FileUploadError: If upload fails
        """
        file_path = Path(file_path)

        # Validate file
        if not file_path.exists():
            raise FileValidationError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise FileValidationError(f"Not a regular file: {file_path}")

        filename = file_path.name
        file_size = file_path.stat().st_size

        if file_size == 0:
            raise FileValidationError(f"File is empty: {file_path}")

        # Validate file type — NLM 웹 dialog의 공식 지원 목록 (사용자 캡쳐 Image #43, 260512).
        # 코드/구조화 데이터(.py/.json/.ts 등)는 NLM 미지원. markdown 파서는 .md에만 의미
        # (v4 결함 후속 학습 — 추측 사고 3 박제 → 허브 운영메모 참조).
        supported_extensions = {
            # Documents (NLM 공식)
            ".pdf",
            ".txt",
            ".md",
            ".docx",
            ".csv",
            ".pptx",
            ".epub",
            # Audio (NLM 공식)
            ".3g2",
            ".3gp",
            ".aac",
            ".aif",
            ".aifc",
            ".aiff",
            ".amr",
            ".au",
            ".cda",
            ".m4a",
            ".mid",
            ".mp3",
            ".mpeg",
            ".ogg",
            ".opus",
            ".ra",
            ".ram",
            ".snd",
            ".wav",
            ".wma",
            # Video (NLM 공식)
            ".avi",
            ".mp4",
            # Images (NLM 공식)
            ".avif",
            ".bmp",
            ".gif",
            ".heic",
            ".heif",
            ".ico",
            ".jp2",
            ".jpe",
            ".jpeg",
            ".jpg",
            ".png",
            ".tif",
            ".tiff",
            ".webp",
        }
        file_extension = file_path.suffix.lower()
        if file_extension not in supported_extensions:
            raise FileValidationError(
                f"Unsupported file type: {file_extension}\n"
                f"Supported types: {', '.join(sorted(supported_extensions))}"
            )

        # Step 1: Register source intent → get SOURCE_ID
        source_id = self._register_file_source(notebook_id, filename)

        # Step 2: Start resumable upload → get upload URL
        upload_url = self._start_resumable_upload(notebook_id, filename, file_size, source_id)

        # Step 3: Stream upload file content
        self._upload_file_streaming(upload_url, file_path)

        result = {"id": source_id, "title": filename}

        if wait:
            return self.wait_for_source_ready(notebook_id, source_id, wait_timeout)

        return result

    def get_source_guide(
        self,
        source_id: str,
        *,
        notebook_id: str | None = None,
        source_type: int | None = None,
    ) -> dict[str, Any]:
        """Get AI-generated summary and keywords for a source.

        Source/Note backend split: regular Sources use RPC `tr032e`; Notes
        (generated_text) have no per-note summary RPC. When `source_type`
        is SOURCE_TYPE_GENERATED_TEXT (=8) and `notebook_id` is provided,
        this method falls back to `list_notes` content (the Note's body
        is its summary in NLM's mental model).

        Args:
            source_id: The source UUID
            notebook_id: Optional notebook UUID — required for note routing
            source_type: Optional source type code — when 8, uses note fallback

        Returns:
            Dict with summary and keywords
        """
        # Note fallback: use list_notes content as the "summary" (no per-note
        # summary RPC exists; Note body itself serves as the descriptive text)
        if _is_note_type(source_type) and notebook_id:
            for note in self.list_notes(notebook_id):
                if note.get("id") == source_id:
                    return {
                        "summary": note.get("content", "") or note.get("preview", ""),
                        "keywords": [],
                    }
            return {"summary": "", "keywords": []}

        result = self._call_rpc(self.RPC_GET_SOURCE_GUIDE, [[[[source_id]]]], "/")
        summary = ""
        keywords = []

        if result and isinstance(result, list):  # noqa: SIM102
            if len(result) > 0 and isinstance(result[0], list):  # noqa: SIM102
                if len(result[0]) > 0 and isinstance(result[0][0], list):
                    inner = result[0][0]

                    if len(inner) > 1 and isinstance(inner[1], list) and len(inner[1]) > 0:
                        summary = inner[1][0]

                    if len(inner) > 2 and isinstance(inner[2], list) and len(inner[2]) > 0:
                        keywords = inner[2][0] if isinstance(inner[2][0], list) else []

        return {
            "summary": summary,
            "keywords": keywords,
        }

    def get_source_fulltext(
        self,
        source_id: str,
        *,
        notebook_id: str | None = None,
        source_type: int | None = None,
        raw_markdown: bool = False,
    ) -> dict[str, Any]:
        """Get the full text content of a source.

        Returns the raw text content that was indexed from the source,
        along with metadata like title and source type.

        Source/Note backend split: regular Sources use RPC `hizoJc`; Notes
        (generated_text) have no per-note get_content RPC — their body is
        already returned by `list_notes` (cFji9). When `source_type` is
        SOURCE_TYPE_GENERATED_TEXT (=8) and `notebook_id` is provided, this
        method falls back to extracting content from `list_notes`.

        Args:
            source_id: The source UUID
            notebook_id: Optional notebook UUID — required for note routing
            source_type: Optional source type code — when 8, uses note fallback
            raw_markdown: When True, reconstruct markdown from the hizoJc tree
                (paragraph flags 4/5/6 → H1~H3, bullet meta → dynamic indent,
                segment format flags → bold/italic/inline code, tables).
                When False (default), return plain text concatenation for
                backwards compatibility with embedding/search callers.
                Use True only for callers that need markdown fidelity
                (notebook_clone). Note fallback (generated_text) is unaffected.

        Returns:
            Dict with content, title, source_type, and char_count
        """
        # Note fallback: list_notes already returns the note body
        if _is_note_type(source_type) and notebook_id:
            for note in self.list_notes(notebook_id):
                if note.get("id") == source_id:
                    content = note.get("content", "") or ""
                    return {
                        "content": content,
                        "title": note.get("title", ""),
                        "source_type": "generated_text",
                        "url": None,
                        "char_count": len(content),
                    }
            return {
                "content": "",
                "title": "",
                "source_type": "generated_text",
                "url": None,
                "char_count": 0,
            }

        # The hizoJc RPC returns source details including full text
        params = [[source_id], [2], [2]]
        result = self._call_rpc(self.RPC_GET_SOURCE, params, "/")

        content = ""
        title = ""
        source_type = ""
        url = None

        if result and isinstance(result, list):
            # Response structure:
            # result[0] = [[source_id], title, metadata, ...]
            # result[1] = null
            # result[2] = null
            # result[3] = [[content_blocks]]
            #
            # Each content block: [start_pos, end_pos, content_data, ...]

            # Extract from result[0] which contains source metadata
            if len(result) > 0 and isinstance(result[0], list):
                source_meta = result[0]

                # Title is at position 1
                if len(source_meta) > 1 and isinstance(source_meta[1], str):
                    title = source_meta[1]

                # Metadata is at position 2
                if len(source_meta) > 2 and isinstance(source_meta[2], list):
                    metadata = source_meta[2]
                    # Source type code is at position 4
                    if len(metadata) > 4:
                        type_code = metadata[4]
                        source_type = constants.SOURCE_TYPES.get_name(type_code)

                    # URL might be at position 7 for web sources
                    if len(metadata) > 7 and isinstance(metadata[7], list):
                        url_info = metadata[7]
                        if len(url_info) > 0 and isinstance(url_info[0], str):
                            url = url_info[0]

            # Extract content from result[3][0] - array of content blocks
            if len(result) > 3 and isinstance(result[3], list):
                content_wrapper = result[3]
                if len(content_wrapper) > 0 and isinstance(content_wrapper[0], list):
                    if raw_markdown:
                        # Reconstruct markdown preserving paragraph flags,
                        # bullet depth, format flags, and tables. The helper
                        # auto-unwraps wrapper lists to reach the real blocks.
                        content = _render_markdown_from_blocks(content_wrapper)
                    else:
                        content_blocks = content_wrapper[0]
                        # Collect all text from content blocks (plain text fallback)
                        text_parts = []
                        for block in content_blocks:
                            if isinstance(block, list):
                                # Each block is [start, end, content_data, ...]
                                # Extract all text strings recursively
                                texts = self._extract_all_text(block)
                                text_parts.extend(texts)
                        content = "\n\n".join(text_parts)

        return {
            "content": content,
            "title": title,
            "source_type": source_type,
            "url": url,
            "char_count": len(content),
        }

    def _extract_all_text(self, data: list[Any]) -> list[str]:
        """Recursively extract all text strings from nested arrays."""
        texts = []
        for item in data:
            if isinstance(item, str) and len(item) > 0:
                texts.append(item)
            elif isinstance(item, list):
                texts.extend(self._extract_all_text(item))
        return texts


# ---------------------------------------------------------------------------
# hizoJc RPC tree → markdown parser helpers (module-level, pure)
# ---------------------------------------------------------------------------
#
# Reconstructs markdown from the raw hizoJc response tree, preserving
# paragraph flags (4/5/6 → H1/H2/H3), bullet metadata ("104":depth →
# "  "*depth indent), segment format flags ([true]=bold,
# [null,true]=italic, 8th-true=inline code), and tables.
#
# NOT wired into get_source_fulltext() yet — that hook lands in Batch 2
# via the raw_markdown=True parameter. Pure functions so tests exercise
# them without instantiating NotebookLMClient.


_ITALIC = "*"  # Obsidian _-conflict avoidance — never use underscore for italic


def _extract_text_recursive(data: Any) -> str:
    """Module-level plain-text fallback for Graceful Degradation.

    Mirrors SourceMixin._extract_all_text but module-level so the parser
    helpers (also module-level) can fall back without a client instance.
    """
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return " ".join(
            _extract_text_recursive(item) for item in data if item is not None
        ).strip()
    return ""


def _parse_segment(seg: list) -> str:
    """One segment ``[seg_start, seg_end, [text, ?format_flags]]`` → markdown inline.

    Format flag positions: 0=bold, 1=italic, 7=inline code. Combinations
    nest as ``**`bold inline`**``. Italic uses ``*`` (asterisk) only.
    """
    try:
        if not isinstance(seg, list) or len(seg) < 3:
            return _extract_text_recursive(seg)
        content = seg[2]
        if not isinstance(content, list) or len(content) == 0:
            return ""
        text = content[0] if isinstance(content[0], str) else ""
        flags = content[1] if len(content) > 1 and isinstance(content[1], list) else []

        is_bold = len(flags) > 0 and flags[0] is True
        is_italic = len(flags) > 1 and flags[1] is True
        is_code = len(flags) > 7 and flags[7] is True

        result = text
        if is_code:
            result = f"`{result}`"
        if is_italic:
            result = f"{_ITALIC}{result}{_ITALIC}"
        if is_bold:
            result = f"**{result}**"
        return result
    except Exception as e:  # noqa: BLE001 — Graceful Degradation
        logger.warning("parser segment: %s @ %r", e, str(seg)[:80])
        return _extract_text_recursive(seg)


def _parse_paragraph(para: list) -> str:
    """One paragraph block → markdown block.

    Layout: ``[start, end, paragraph_data]`` where
    ``paragraph_data = [segments, [null, kind], ?, ?bullet_wrapper]``.
    kind: 4/5/6=H1~H3, 1=normal/bullet (bullet_wrapper present iff bullet).
    bullet_wrapper inner dict keys: "101"=marker, "103"=item_idx, "104"=depth.
    """
    try:
        if not isinstance(para, list) or len(para) < 3:
            return _extract_text_recursive(para)
        paragraph_data = para[2]
        if not isinstance(paragraph_data, list) or len(paragraph_data) < 2:
            return _extract_text_recursive(para)

        segments = paragraph_data[0] if isinstance(paragraph_data[0], list) else []
        flags = paragraph_data[1] if isinstance(paragraph_data[1], list) else [None, 1]

        joined = "".join(_parse_segment(seg) for seg in segments)

        kind = flags[1] if len(flags) > 1 else 1
        if kind == 4:
            return f"# {joined}"
        if kind == 5:
            return f"## {joined}"
        if kind == 6:
            return f"### {joined}"
        if kind == 1:
            bullet_meta = None
            if len(paragraph_data) > 3 and isinstance(paragraph_data[3], list):
                wrapper = paragraph_data[3]
                if len(wrapper) > 3 and isinstance(wrapper[3], dict):
                    bullet_meta = wrapper[3]
            if bullet_meta:
                marker = bullet_meta.get("101", "•")
                depth = bullet_meta.get("104", 0)
                if not isinstance(depth, int) or depth < 0:
                    depth = 0
                indent = "  " * depth
                if marker == "1.":
                    item_idx = bullet_meta.get("103", 1)
                    return f"{indent}{item_idx}. {joined}"
                return f"{indent}- {joined}"
            return joined  # normal paragraph
        # Unknown flag → plain text fallback + warning
        logger.warning("unknown paragraph flag: %s @ %r", kind, str(para)[:80])
        return joined
    except Exception as e:  # noqa: BLE001
        logger.warning("parser paragraph: %s @ %r", e, str(para)[:80])
        return _extract_text_recursive(para)


def _parse_table(table_data: list) -> str:
    """Table inner tuple ``[cols, rows, cells]`` → markdown table.

    cells: ``[row0_cells, row1_cells, ...]`` where each cell is
    ``[start, end, [[text]]]``. First row treated as header.
    """
    try:
        if not isinstance(table_data, list) or len(table_data) < 3:
            return _extract_text_recursive(table_data)
        cols = table_data[0]
        rows = table_data[1]
        cells = table_data[2]
        if (
            not isinstance(cols, int)
            or not isinstance(rows, int)
            or not isinstance(cells, list)
        ):
            return _extract_text_recursive(table_data)

        def cell_text(cell: Any) -> str:
            if not isinstance(cell, list) or len(cell) < 3:
                return ""
            return _extract_text_recursive(cell[2]).strip()

        lines: list[str] = []
        if len(cells) > 0:
            header = cells[0]
            if isinstance(header, list):
                header_strs = [cell_text(c) for c in header]
                lines.append("| " + " | ".join(header_strs) + " |")
                lines.append("|" + "|".join("---" for _ in header_strs) + "|")
            for row in cells[1:]:
                if isinstance(row, list):
                    row_strs = [cell_text(c) for c in row]
                    lines.append("| " + " | ".join(row_strs) + " |")
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001
        logger.warning("parser table: %s @ %r", e, str(table_data)[:80])
        return _extract_text_recursive(table_data)


def _parse_content_block(block: list) -> str:
    """Dispatch one content block → markdown.

    Table heuristic: ``len(block)==5`` with ``block[2]==block[3]==None``
    and ``block[4]`` a list. Otherwise treat as paragraph.
    """
    try:
        if not isinstance(block, list):
            return _extract_text_recursive(block)
        if (
            len(block) >= 5
            and block[2] is None
            and block[3] is None
            and isinstance(block[4], list)
        ):
            return _parse_table(block[4])
        return _parse_paragraph(block)
    except Exception as e:  # noqa: BLE001
        logger.warning("parser block: %s @ %r", e, str(block)[:80])
        return _extract_text_recursive(block)


def _is_bullet_rendered(rendered: str) -> bool:
    """Heuristic: rendered block is a bullet (after leading indent)."""
    stripped = rendered.lstrip(" ")
    if stripped.startswith("- "):
        return True
    head = stripped.split(" ", 1)[0] if " " in stripped else ""
    return head.endswith(".") and head[:-1].isdigit()


def _unwrap_content_blocks(blocks: Any, _max_depth: int = 5) -> list:
    """Auto-unwrap nested wrapper lists until we reach the real blocks array.

    The hizoJc response wraps content blocks at varying depths: ``result[3]``
    might be ``[[blocks]]`` (the live RPC shape) or already ``[blocks]``
    (manually-trimmed fixtures). A real block is ``[start, end, ...]`` so
    ``blocks[0][0]`` is an int — that's the unwrap stop signal.
    """
    for _ in range(_max_depth):
        if not isinstance(blocks, list) or len(blocks) != 1:
            break
        inner = blocks[0]
        if not isinstance(inner, list) or len(inner) == 0:
            break
        first = inner[0]
        # Real block: [start, end, ...] → first is int. Stop here.
        if isinstance(first, int):
            break
        blocks = inner
    return blocks if isinstance(blocks, list) else []


def _render_markdown_from_blocks(blocks: list) -> str:
    """Top-level entry: content blocks → full markdown.

    Auto-unwraps wrapper lists (raw hizoJc ``result[3]`` is ``[[blocks]]``).
    Separator: consecutive bullet blocks join with ``\\n`` (list continuity);
    otherwise paragraph break ``\\n\\n``.
    """
    try:
        if not isinstance(blocks, list):
            return _extract_text_recursive(blocks)
        blocks = _unwrap_content_blocks(blocks)
        parts: list[str] = []
        prev_is_bullet = False
        for block in blocks:
            rendered = _parse_content_block(block)
            is_bullet = _is_bullet_rendered(rendered)
            if parts:
                sep = "\n" if (prev_is_bullet and is_bullet) else "\n\n"
                parts.append(sep)
            parts.append(rendered)
            prev_is_bullet = is_bullet
        return "".join(parts)
    except Exception as e:  # noqa: BLE001
        logger.warning("parser render: %s @ %r", e, str(blocks)[:80])
        return _extract_text_recursive(blocks)
