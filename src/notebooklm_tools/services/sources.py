"""Sources service — shared validation and logic for source management."""

import json
import logging
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from ..core.client import NotebookLMClient
from ..core.constants import SUPPORTED_FILE_EXTS
from .errors import ServiceError, ValidationError
from .sync_helpers import (
    _should_skip_bundle_upload,
    expand_bundle_files,
    get_vault_root,
    load_bundle_registry,
)

logger = logging.getLogger(__name__)

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

# SUPPORTED_FILE_EXTS는 core.constants SSOT에서 import (상단). replace_source_file의
# pre-check(파괴적 delete 전 확장자 검사로 orphan 방지)와 아래 자동 폴더명 박제가 공용.
# 세션79: 과거 이 자리에 있던 복붙 frozenset을 core.constants 단일 정의로 통합.

# 동명 파일 다폴더 자동 폴더명 박제 대상 (v7, 260528 ATOM-1)
# title 미지정 + 본 frozenset 매칭 시 add_source가 자동으로 `{basename} ({parent_folder})` 형태 박제.
# drift detect_drift ambiguous 차단 (sync_helpers._narrow_by_folder_hint와 짝).
DUP_FILENAMES_AUTO_FOLDER_TAG: frozenset[str] = frozenset({"SKILL.md", "nlm_seed.md"})


class AddSourceResult(TypedDict):
    """Result of adding a source."""

    source_type: str
    source_id: str
    title: str
    # Set True only when a best-effort title rename (file sources) failed —
    # optional so the required 3-field contract stays intact. Diagnostic only;
    # not propagated to the source_replace_file response dict.
    title_rename_failed: NotRequired[bool]


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
    mode: Literal["file", "text"]
    # 세션540 — best-effort rename 실패를 호출자(AI)에게 전파. 이전에는
    # AddSourceResult에만 실려 서버 logger.warning으로만 남았고, replace 응답에는
    # "not propagated"였다(L54-57 docstring 자백). 그 결과 rename이 튕기면 NLM에
    # bare 제목 소스가 조용히 생기고 → 다음 동기화에서 bare 하이재킹 지뢰가 된다
    # (층2 재개방 채널, 신드리 ●●○). 관측을 달아 무음 재생성을 끊는다.
    title_rename_failed: NotRequired[bool]


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


# rename 미반영 재시도 대기 (초). 테스트에서 monkeypatch로 0 주입 가능.
RENAME_VERIFY_RETRY_DELAY_SEC = 3.0


def _rename_source_verified(
    client: NotebookLMClient,
    notebook_id: str,
    source_id: str,
    title: str,
) -> bool:
    """제목 rename + **read-back 검증** + 1회 재시도 (세션540 신설).

    왜 검증이 필요한가 — 세션540 라이브 실측:
        `client.rename_source`가 **성공을 반환하고도 NLM이 제목을 버린다.** add 직후
        (1~2초) 호출하면 RPC는 정상 응답하고 서버 로그에 경고 하나 남지 않는데,
        13분 뒤 소스 목록을 조회하면 제목이 bare 파일명 그대로다. 같은 소스에 몇 분
        뒤 `source_rename`을 명시 호출하면 즉시 반영된다 — 즉 add 직후의 eventual
        consistency 창에서 rename이 조용히 유실된다.

    이것이 세션525·529가 매 동기화마다 수동 `source_rename`을 반복해야 했던 현상의
    정체다. 지금까지의 진단은 *"best-effort rename이 실패하는데 무음"*이었고 세션540의
    1차 처방도 `title_rename_failed` 전파였으나 — **실패가 아니라 거짓 성공**이라
    그 처방으로는 원천적으로 못 잡는다. 반환값을 믿지 않고 read-back으로 확인한다
    (헌법 §세션 관리 *박제 직후 read-back* 원칙과 동형).

    비용 억제: NLM이 add 시 부여하는 기본 제목은 파일 basename이므로, 요청 제목이
    basename과 같으면 rename 자체가 무변경이라 검증을 건너뛴다. 실제 검증 비용은
    폴더태그처럼 *제목을 진짜 바꾸는* 경우에만 발생한다.

    Returns:
        True — 반영 확인됨(또는 검증 불가라 best-effort로 수용).
        False — 조회 결과 제목이 여전히 다름(재시도 후에도). 호출자는
        ``title_rename_failed``로 전파해 운영자가 수동 복원하게 한다.
    """

    def _observed_title() -> str | None:
        """소스 목록에서 이 source_id의 현재 제목. 조회 불가·미발견이면 None."""
        try:
            for src in client.get_notebook_sources_with_types(notebook_id):
                if src.get("id") == source_id:
                    observed = src.get("title")
                    return observed if isinstance(observed, str) else ""
        except Exception:  # noqa: BLE001 — 검증은 best-effort
            return None
        return None

    def _attempt() -> bool | None:
        """rename 1회 + 검증. True=반영 / False=미반영 / None=판정 보류."""
        try:
            renamed = client.rename_source(notebook_id, source_id, title)
        except Exception:  # noqa: BLE001 — best-effort
            logger.warning(
                "rename_source raised for source %s (title=%r)",
                source_id,
                title,
                exc_info=True,
            )
            return False
        observed = _observed_title()
        if observed is None:
            # 조회 실패·목록 미등재라 read-back으로 판정할 수 없다. 이때는 RPC
            # 반환값이 유일한 신호이므로 그것을 따른다 — 세션486의 falsy 계약 보존
            # (read-back은 반환값을 *대체*하는 게 아니라 상위 권위로 추가된 것).
            return True if renamed else False
        # 관측된 제목이 최종 권위 — truthy 반환이어도 미반영이면 실패로 본다.
        return observed.strip() == title.strip()

    first = _attempt()
    if first is not False:
        return True

    logger.warning(
        "rename_source reported success but the title did not stick for source "
        "%s (wanted %r) — retrying after %.1fs (session 540: NLM drops renames "
        "issued inside the post-add consistency window).",
        source_id,
        title,
        RENAME_VERIFY_RETRY_DELAY_SEC,
    )
    if RENAME_VERIFY_RETRY_DELAY_SEC > 0:
        time.sleep(RENAME_VERIFY_RETRY_DELAY_SEC)
    second = _attempt()
    if second is False:
        logger.warning(
            "rename_source still not reflected for source %s (wanted %r). The "
            "NLM title is left bare — run source_rename manually.",
            source_id,
            title,
        )
        return False
    return True


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
    auto_wrap_to_md: bool = False,
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
        auto_wrap_to_md: For source_type=file only — wrap unsupported
            extensions (.py/.ts/.json/...) in a markdown code fence and
            upload as ``{stem}{ext}.md`` so NLM's markdown parser activates.
            Default ``False`` preserves strict-extension behavior.

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
            result = client.add_file(
                notebook_id,
                file_path,
                wait=wait,
                wait_timeout=wait_timeout,
                auto_wrap_to_md=auto_wrap_to_md,
            )
            _p = Path(file_path)
            fallback_title = _p.name
            # 동명 파일 자동 폴더명 박제 (v7, 260528 ATOM-1 — drift ambiguous 차단)
            # title 미지정 *또는* bare 파일명 고착(`title == basename`) + DUP 매칭 시
            # `{basename} ({parent})` 재생성. bare 감지 절(세션486)은 replace 경로에서
            # `_do_add`가 넘긴 bare preserved_title(예: "SKILL.md")이 truthy라 옛 `if not
            # title:` 관문을 우회해 영구 고착하던 회로를 끊는다. 폴더태그 title
            # (`SKILL.md (cross_3step_solver)`)은 `.strip() != _p.name`이라 스킵→preserve.
            if _p.name in DUP_FILENAMES_AUTO_FOLDER_TAG and (
                not title or title.strip() == _p.name
            ):
                title = f"{_p.name} ({_p.parent.name})"
                fallback_title = title
            # title preservation (v5 결함 픽스, 260512): NLM은 add_file 시 filename을 title로 사용.
            # 사용자 지정 title 있으면 별도 rename RPC (b7Wfje) 호출. add_file은 항상 *Source-area*
            # 등록이므로 source_type 인자 생략 (None) — 일반 Source RPC 라우팅. Real Note(list_notes
            # 멤버)는 add_file로 안 들어오므로 update_note 분기 불필요. best-effort — 실패 시 main 계속.
            # rename 실패(예외/falsy 반환)는 무음 삼키지 않고 logger.warning + 반환 dict에
            # title_rename_failed 플래그로 관측 (세션486, dead-field 회피 위해 추출 후 주입).
            rename_failed = False
            if title and isinstance(result, dict) and result.get("id"):
                if title.strip() == _p.name:
                    # NLM이 add 시 basename을 기본 제목으로 부여하므로 무변경 —
                    # RPC도 read-back도 불필요 (검증 비용 억제).
                    result["title"] = title
                else:
                    if _rename_source_verified(
                        client, notebook_id, result["id"], title
                    ):
                        result["title"] = title
                    else:
                        rename_failed = True
            extracted = _extract_result(result, "file", title or fallback_title)
            if rename_failed:
                extracted["title_rename_failed"] = True
            return extracted

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
    file_path: str,
    *,
    source_id: str | None = None,
    fallback_to_text: bool = False,
    atomic: bool = True,
) -> ReplaceSourceFileResult:
    """Replace an existing source by deleting it and uploading a new local file.

    Composition wrapper over ``delete_source`` + ``add_source`` (DRY — does
    not inline RPC calls). NLM has no in-place update RPC for file sources,
    so a delete + add transaction is required, which changes the source_id.

    Pre-check is intentionally redundant with ``core/sources.py:add_file``'s
    file validation — load-bearing safety to fail BEFORE the destructive
    delete step. Without it, a missing/invalid file would surface only after
    the delete succeeds, leaving the source permanently lost.

    When ``fallback_to_text=True``, unsupported extensions (e.g. ``.json``,
    ``.py``) are routed to a text-mode upload: the file contents are read as
    UTF-8 and uploaded via ``add_source(source_type="text")``. UTF-8 decode
    failure surfaces as ``ValidationError`` *before* the delete step (pre-delete
    safety). Default ``False`` preserves the original strict-extension behavior.

    ``atomic=True`` (default) uses ADD-first ordering: ADD first, and only on
    success is the old source DELETED. ADD failure leaves the original source
    intact, closing the "delete succeeded but add failed" data-loss window
    observed in session 330 (``~/.claude/CLAUDE.md`` source 분실 사고) and
    session 393 (``__시스템맵.md`` 일시 분실). Promoted to default in the v10
    track — the session 37 Ghost ID / Eventual Consistency concern was ruled a
    theoretical non-issue (그것은 병렬 ADD 폭격 시에만 발생; atomic replace is
    synchronous serial). Pass ``atomic=False`` for the legacy delete-first
    behavior (not recommended — an ADD failure permanently loses the source).

    ``source_id`` is optional (keyword-only). When omitted, it is auto-resolved
    from ``Path(file_path).name`` against the notebook's source list — which the
    function already fetches for title preservation, so auto-match adds zero
    network I/O. This removes the AI-facing UUID entirely from the common path,
    eliminating the transcription-error class (sessions 317/400/412/418). The
    match is deterministic 3-tier (exact title → prefix title → Fail-close on
    0/2+ candidates); see ``_match_source_by_basename``. Pass ``source_id``
    explicitly only to override or when auto-match reports ambiguity.

    Args:
        client: Authenticated NotebookLM client
        notebook_id: Notebook UUID containing the source
        file_path: Path to the local file to upload as the replacement
        source_id: Source UUID to replace (keyword-only). Leave ``None`` to
            auto-match by basename (recommended — no UUID handling). Raises
            ValidationError on ambiguous/no match; raises ServiceError if the
            source list cannot be fetched for auto-match.
        fallback_to_text: Opt-in — route unsupported extensions to a text
            upload (UTF-8 only). Default ``False``.
        atomic: Opt-in — perform ADD before DELETE so an ADD failure preserves
            the original source. Default ``False`` (legacy delete-first).

    Returns:
        ReplaceSourceFileResult with old/new source IDs, title, path, and
        ``mode`` (``"file"`` for the standard path, ``"text"`` when the
        fallback fired).

    Raises:
        ValidationError: If file_path is missing, not a file, empty, has
            an unsupported extension (and ``fallback_to_text=False``), or
            cannot be decoded as UTF-8 (with ``fallback_to_text=True``).
            All raised BEFORE any delete.
        ServiceError: If delete or add fails. The error message and
            ``user_message`` make the resulting state explicit:
            - legacy mode (``atomic=False``): "delete succeeded but add
              failed" → original source is gone, please re-add.
            - atomic mode (``atomic=True``): either "add failed; original
              preserved" (no DELETE fired) or "add succeeded but delete of
              old source failed" (notebook now contains both — manual
              cleanup required).
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
    use_text_fallback = False
    text_content: str | None = None
    if ext not in SUPPORTED_FILE_EXTS:
        if not fallback_to_text:
            raise ValidationError(
                f"Unsupported file type: {ext}",
                user_message=f"Unsupported file type: {ext}",
                hint=f"Supported types: {', '.join(sorted(SUPPORTED_FILE_EXTS))}",
            )
        try:
            text_content = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ValidationError(
                f"Cannot decode as UTF-8 for text fallback: {file_path}",
                user_message="File contents are not valid UTF-8 text.",
                hint="fallback_to_text requires a text-decodable file.",
            ) from e
        use_text_fallback = True

    # 2. Resolve source_id + preserve title (single source-list fetch).
    #    - source_id is None → auto-match by basename; the fetch is MANDATORY.
    #      A silent pass here would hide a match failure and let the destructive
    #      path proceed with an unresolved source (session 418 함정1).
    #    - source_id given   → best-effort title preservation (fetch failure
    #      is non-fatal; the replacement still works without a preserved title).
    preserved_title: str | None = None
    if source_id is None:
        try:
            sources = client.get_notebook_sources_with_types(notebook_id)
        except Exception as e:
            raise ServiceError(
                f"Cannot fetch sources for source_id auto-match: {e}",
                user_message=(
                    "source_id 미지정 자동매칭 실패 — NLM 소스 목록을 "
                    "조회할 수 없습니다."
                ),
                hint="source_id를 명시하거나 네트워크·인증을 확인하세요.",
            ) from e
        source_id, preserved_title = _match_source_by_basename(
            sources, p.name, p.parent.name
        )
    else:
        try:
            for src in client.get_notebook_sources_with_types(notebook_id):
                if src.get("id") == source_id:
                    title_val = src.get("title")
                    if isinstance(title_val, str) and title_val.strip():
                        preserved_title = title_val
                    break
        except Exception:
            pass  # title preservation is optional; proceed without it

    # 3 + 4. Apply add+delete in the order dictated by the ``atomic`` flag.
    if atomic:
        # ADD first — if ADD fails the original source is still intact.
        try:
            add_res = _do_add(
                client,
                notebook_id,
                p,
                use_text_fallback,
                text_content,
                preserved_title,
            )
        except (ValidationError, ServiceError) as e:
            raise ServiceError(
                f"Replace failed (atomic): add failed; original source preserved: {e}",
                user_message=(
                    "Replacement upload failed. The original source is still "
                    "present in the notebook — no data loss."
                ),
                hint="Verify the file path and retry; no cleanup needed.",
            ) from e

        # ADD succeeded → DELETE old source. If DELETE fails the notebook
        # transiently contains both sources; surface that state explicitly
        # so the caller can decide whether to retry the delete.
        try:
            delete_source(client, source_id, notebook_id=notebook_id)
        except (ValidationError, ServiceError) as e:
            raise ServiceError(
                f"Replace failed (atomic): add succeeded but delete failed: {e}",
                user_message=(
                    f"New source {add_res['source_id']} uploaded successfully, "
                    f"but deleting the old source {source_id} failed. The "
                    "notebook now contains both — please retry deletion manually."
                ),
                hint=f"Retry: source_delete(source_id='{source_id}').",
            ) from e
    else:
        # Legacy delete-first (default). Pre-checks above ensure the destructive
        # step is preceded by all recoverable failure modes.
        delete_source(client, source_id, notebook_id=notebook_id)

        # On ADD failure the original source is already gone — surface that
        # explicitly so the user knows to re-add.
        try:
            add_res = _do_add(
                client,
                notebook_id,
                p,
                use_text_fallback,
                text_content,
                preserved_title,
            )
        except (ValidationError, ServiceError) as e:
            raise ServiceError(
                f"Replace failed: delete succeeded but add failed: {e}",
                user_message=(
                    "Source was deleted but the replacement upload failed. "
                    "The original source is gone; please re-add the file manually."
                ),
                hint="Verify the file path and retry add_source.",
            ) from e

    mode: Literal["file", "text"] = "text" if use_text_fallback else "file"
    fallback_suffix = " (fallback to text mode)" if use_text_fallback else ""
    atomic_suffix = " (atomic)" if atomic else ""
    # rename 실패 시 메시지에도 명시 — 응답 dict의 필드만으로는 아무도 안 본다는 것이
    # 세션538~540에서 반복 확인된 실패 모드라, 사람이 읽는 문면에 함께 싣는다.
    rename_failed = bool(add_res.get("title_rename_failed"))
    rename_suffix = (
        " ⚠ 제목 rename 실패 — NLM 제목이 bare 파일명으로 남았을 수 있습니다."
        " source_rename으로 폴더태그형 제목을 복원하십시오."
        if rename_failed
        else ""
    )
    result: ReplaceSourceFileResult = {
        "notebook_id": notebook_id,
        "old_source_id": source_id,
        "new_source_id": add_res["source_id"],
        "title": add_res["title"],
        "file_path": str(p),
        "message": (
            f"Replaced source {source_id} with {add_res['source_id']}"
            f"{fallback_suffix}{atomic_suffix}{rename_suffix}"
        ),
        "mode": mode,
    }
    if rename_failed:
        result["title_rename_failed"] = True
    return result


def _match_source_by_basename(
    sources: list[dict[str, Any]],
    basename: str,
    folder_hint: str | None = None,
) -> tuple[str, str | None]:
    """Resolve a unique source_id from a file basename against the source list.

    Deterministic match (NLM ●●● conv 803fdca1, session 418; tier 1.5 session 520):
      1. Exact  — source title == ``basename``.
      1.5. Folder-tag exact — title == ``f"{basename} ({folder_hint})"`` when a
         folder hint is supplied. Disambiguates the N same-basename auto-folder-tag
         titles (e.g. ``SKILL.md (brokk-debate)`` vs ``SKILL.md (suno-lyric-roulette)``)
         that the prefix tier alone leaves ambiguous. Mirrors detect_drift's folder
         narrowing — the missing replace↔drift symmetry was the real root cause
         of the SKILL.md deadlock (session 520 신드리 실측).
      2. Prefix — source title startswith ``f"{basename} ("`` — defends the
         auto-folder-tag titles NLM mints for duplicate filenames, e.g.
         ``SKILL.md (two_step_solver)`` / ``nlm_seed.md (cross_3step_solver)``.
      3. Fail-close — 0 or 2+ candidates raise ``ValidationError`` carrying the
         candidate list, so the caller supplies an explicit ``source_id``.

    Precedence: exact → folder-tag exact → prefix. A non-empty higher tier is
    used even if lower tiers also match. Returns ``(source_id, title)`` on a
    unique match. Raised BEFORE any destructive delete (pre-check safety, same
    contract as the file pre-checks in ``replace_source_file``).

    **Tier 1 demotion (session 540)**: when ``basename`` is in
    ``DUP_FILENAMES_AUTO_FOLDER_TAG`` *and* a folder-tag match exists for this
    file, the bare exact match is a foreign residual (convention violation) and
    tier 1.5 wins instead. Without this, a single bare residual silently
    hijacks *every* same-basename replace as a confident unique match — not an
    ambiguity, so fail-close never fires. Session 486's self-healing (adopt the
    bare source and regenerate its folder tag) is preserved for the case where
    no folder-tag source exists; both adoption and blocking are logged.
    """
    exact = [s for s in sources if (s.get("title") or "").strip() == basename]
    # Tier 1.5 — folder-tag exact (session 520): disambiguates auto-folder-tag
    # titles when N skills share a basename (SKILL.md ×N). Without it the prefix
    # tier below matches all N → ambiguous → SKILL.md deadlock (28~520 밀림).
    folder_exact: list[dict[str, Any]] = []
    if folder_hint:
        _target = f"{basename} ({folder_hint})"
        folder_exact = [
            s for s in sources if (s.get("title") or "").strip() == _target
        ]
    prefix = [
        s for s in sources
        if (s.get("title") or "").strip().startswith(f"{basename} (")
    ]
    # 세션540 — bare-exact 하이재킹 차단: DUP 화이트리스트 파일에 한해 folder_exact를
    # bare-exact보다 **우선**한다 (신드리 ●●●, 선순위 역전안 채택).
    #
    # 문제: `DUP_FILENAMES_AUTO_FOLDER_TAG` 등재 파일은 폴더태그가 규약이라 bare 제목
    # 소스는 규약 위반 잔재인데, 원래 순서 `exact or folder_exact or prefix`는 bare를
    # 1순위로 신뢰한다. 잔재 1건이 노트북에 있으면 *어느 스킬의* SKILL.md를 replace하든
    # len(candidates)==1로 그 잔재에 매칭된다 — 모호가 아니라 "확신에 찬 오매칭"이라
    # fail-close도 안 걸린다. 세션540 실측: 본관에 bare `SKILL.md`(brokk-debate 구버전)가
    # 잔존해 SKILL 동기화 전체가 지뢰 위에 있었고, 중복 2쌍이 그 화석이었다.
    #
    # 왜 bare 전면 배제가 아닌 선순위 역전인가: 전면 배제는 세션486의 *자가 치유* 계약
    # (bare 고착 소스를 replace하면 폴더태그가 재생성되어 스스로 낫는다,
    # `test_replace_bare_stuck_source_regenerates_folder_tag`)을 파괴한다. 회귀가 이를
    # 반증했다. 이 파일이 *이미 제대로 태그된 소스를 갖고 있다면*(folder_exact 존재)
    # bare는 명백히 남의 것이므로 배제하고, 태그된 소스가 없으면 종전대로 bare를 흡수해
    # 치유한다 — 단 그 흡수는 provenance를 증명할 수 없으므로 warning으로 관측한다
    # (뿌리3 교훈: 발견을 무음으로 흘려보내지 말 것).
    dup_managed = basename in DUP_FILENAMES_AUTO_FOLDER_TAG
    bare_residuals = exact if dup_managed else []
    if dup_managed and exact and folder_exact:
        logger.warning(
            "bare-exact hijack blocked for %r: %d bare residual(s) bypassed in "
            "favour of folder-tag match (residuals: %s). Rename or delete them.",
            basename,
            len(exact),
            [s.get("id") for s in exact],
        )
        candidates = folder_exact
    else:
        if dup_managed and exact:
            logger.warning(
                "adopting bare-titled source %s for %r — no folder-tag source "
                "exists for this file, so provenance is unverified. Confirm the "
                "source content belongs to %r.",
                [s.get("id") for s in exact],
                basename,
                str(folder_hint),
            )
        candidates = exact or folder_exact or prefix
    if len(candidates) == 1:
        c = candidates[0]
        sid = c.get("id") or ""
        title_val = c.get("title")
        title = title_val if isinstance(title_val, str) and title_val.strip() else None
        return sid, title

    cand_repr = (
        ", ".join(
            f"{{id: {s.get('id')}, title: {s.get('title')!r}}}" for s in candidates
        )
        or "(none)"
    )
    # bare 잔재를 제외한 결과로 실패한 경우, 그 잔재가 진짜 원인이므로 hint에 지목한다
    # (세션540 — 침묵 하이재킹을 시끄러운 정지로 전환한 대가로 원인 안내가 필수).
    residual_hint = ""
    if bare_residuals:
        residual_repr = ", ".join(
            f"{{id: {s.get('id')}, title: {s.get('title')!r}}}" for s in bare_residuals
        )
        residual_hint = (
            f" ⚠ 규약 위반 bare 제목 잔재 {len(bare_residuals)}건을 매칭에서 제외했습니다"
            f" — [{residual_repr}]. 폴더태그형 '{basename} (폴더명)'으로 source_rename"
            f" 하거나, 중복 구버전이면 source_delete 하십시오."
        )
    raise ValidationError(
        f"Cannot auto-match source_id for basename {basename!r}: "
        f"{len(candidates)} candidate(s).",
        user_message=(
            f"파일명 '{basename}'으로 source_id 자동매칭 실패 "
            f"({len(candidates)}개 후보). source_id를 명시하세요."
        ),
        hint=f"후보: [{cand_repr}]{residual_hint}",
    )


def _do_add(
    client: NotebookLMClient,
    notebook_id: str,
    p: Path,
    use_text_fallback: bool,
    text_content: str | None,
    preserved_title: str | None,
) -> AddSourceResult:
    """Internal helper — dispatch the ADD half of replace_source_file.

    Extracted so legacy and atomic modes share identical add semantics
    (no drift in title preservation or text-fallback handling).
    """
    if use_text_fallback:
        assert text_content is not None  # narrowed by use_text_fallback branch
        return add_source(
            client,
            notebook_id,
            "text",
            text=text_content,
            title=preserved_title or p.name,
        )
    return add_source(
        client,
        notebook_id,
        "file",
        file_path=str(p),
        title=preserved_title,
    )


# ---------------------------------------------------------------------------
# Tier 2 N:1 번들 동기화 (Batch 3 ATOM-3, 세션368)
# ---------------------------------------------------------------------------


class SyncBundleResult(TypedDict):
    """Result of sync_bundle: build local N-file bundle(s) + Full-Sync to NLM.

    ``source_ids`` holds every resulting part source (length 1 when unsplit);
    ``source_id`` is the first for back-compat. ``parts`` is the rendered part
    count. ``mode`` reflects the first part's dispatch (add/replace).
    """

    notebook_id: str
    bundle_name: str
    source_id: str
    source_ids: list[str]
    title: str
    mode: Literal["add", "replace", "skip"]
    parts: int
    bundled_count: int
    message: str


# generate_bundle_md.py lives inside the package (src/notebooklm_tools/scripts/)
# so it ships in the wheel and resolves under any install layout (no editable
# fallback). parents[1] == notebooklm_tools/ from services/sources.py.
_BUNDLE_TOOL_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "generate_bundle_md.py"
)

# Default chunking threshold (words) — mirrors DEFAULT_BUNDLE_MAX_WORDS in
# scripts/generate_bundle_md.py. Parser-timeout defense, not a hard NLM cap.
# A registry entry may override via its ``max_words`` key.
# v10: 200k→100k — 234초 spike(마크다운 파서 timeout) 이중 방어 (conv 803fdca1).
_DEFAULT_BUNDLE_MAX_WORDS = 100_000


def _bundle_source_exists(
    client: NotebookLMClient, notebook_id: str, bundle_name: str
) -> bool:
    """NLM 노트북에 이 번들의 소스(``{name}.md`` 또는 ``{name}_partN``)가
    실존하는지 확인 (세션493).

    조회 실패 시 ``False`` 반환 — fail-safe: 부재로 간주해 업로드 진행(불확실
    → 업로드). ``_should_skip_bundle_upload``(git 무변경)와 AND 결합되어,
    신규 번들 첫 생성(원본이 앵커보다 오래됨)이 origin diff 0으로 영영 skip되던
    엣지케이스를 막는다.
    """
    stub = f"{bundle_name}.md"
    part_prefix = f"{bundle_name}_part"
    try:
        for src in client.get_notebook_sources_with_types(notebook_id):
            t = src.get("title")
            if isinstance(t, str) and (t == stub or t.startswith(part_prefix)):
                return True
    except Exception:
        return False
    return False


def sync_bundle(
    client: NotebookLMClient,
    notebook_id: str,
    bundle_name: str,
    *,
    registry_path: Path | None = None,
    bundle_tool_script: Path | None = None,
    python_executable: str | None = None,
) -> SyncBundleResult:
    """Build a Tier 2 N:1 bundle locally and sync to NLM as one source.

    Reads the bundle definition from ``nlm_bundle_registry.json``, invokes
    ``scripts/generate_bundle_md.py`` in a temp dir to render the bundle
    markdown, then either *replaces* the existing ``{bundle_name}.md`` source
    via :func:`replace_source_file` (``atomic=True``) or *adds* a new one.

    Idempotent — repeated calls converge on the latest origin contents and
    reuse the existing NLM source_id (subject to delete+add ID rotation in
    the atomic-replace branch). Fail-close: every recoverable failure
    (missing registry entry, missing origin files, bundle build error) is
    raised *before* any destructive NLM call so the previous bundle source
    (if any) remains intact.

    Args:
        client: Authenticated NotebookLM client.
        notebook_id: Notebook UUID hosting the bundle source.
        bundle_name: Logical bundle name — must match a key under
            ``bundles`` in ``nlm_bundle_registry.json``.
        registry_path: Optional override for the bundle registry JSON.
        bundle_tool_script: Optional override for the bundle builder script
            path (test seam — defaults to the repo-relative path).
        python_executable: Optional override for the Python used to invoke
            the builder (test seam — defaults to ``sys.executable``).

    Returns:
        SyncBundleResult with mode ``"add"`` or ``"replace"`` and the
        resulting source_id / title.

    Raises:
        ValidationError: bundle name unknown, files list empty, or any
            origin file missing on disk (all surfaced *before* the
            NLM call).
        ServiceError: bundle builder failed, bundle tool missing, or the
            NLM add/replace failed.
    """
    # 1. Registry lookup
    registry = load_bundle_registry(registry_path)
    bundle = registry.get(bundle_name)
    if not bundle or not isinstance(bundle, dict):
        raise ValidationError(
            f"Bundle '{bundle_name}' not registered",
            user_message=f"Unknown bundle: {bundle_name}",
            hint="Add the bundle under `bundles` in nlm_bundle_registry.json",
        )
    files = bundle.get("files")
    if not isinstance(files, list) or not files:
        raise ValidationError(
            f"Bundle '{bundle_name}' has empty file list",
            user_message=f"Bundle '{bundle_name}' has no files",
        )

    # 2. Pre-flight origin existence (fail-close before NLM is touched).
    #    glob 지원 (세션493): registry `files` 항목의 `*` 확장 → 폴더 전체 자동
    #    편입 (예: `회차아카이브/*.md` 1줄로 신규 회차 무편집 편입). glob 확장분은
    #    실존 파일만 산출하므로 missing_origins는 리터럴 경로만 잡는다.
    abs_files = [p.resolve() for p in expand_bundle_files([str(f) for f in files])]
    if not abs_files:
        raise ValidationError(
            f"Bundle '{bundle_name}' expanded to zero files",
            user_message=f"Bundle '{bundle_name}' has no matching files on disk.",
            hint="glob 패턴이 아무 파일도 매칭하지 못했을 수 있음 (registry files 확인).",
        )
    missing_origins = [str(p) for p in abs_files if not p.exists()]
    if missing_origins:
        raise ValidationError(
            f"Bundle '{bundle_name}' has missing origins: {missing_origins}",
            user_message=(
                f"Bundle '{bundle_name}' references files that no longer exist on disk."
            ),
            hint=f"First missing: {missing_origins[0]}",
        )

    # 2.5 git churn skip (v10 I/O 병목) — 원본이 앵커 이후 변경 없으면 가장 무거운
    #     bundle 렌더(subprocess) + NLM 조회/업로드를 원천 회피. origin 존재
    #     확인(fail-close) *뒤*에 두어 깨진 경로 은폐를 막는다 (NLM Q1 ●●●).
    #     단, git 무변경이어도 **NLM에 번들 소스가 실존할 때만** skip한다 —
    #     신규 번들 첫 생성(원본이 앵커보다 오래됨)은 origin diff가 0이라 영영
    #     skip되던 엣지케이스 방어 (세션493 신드리 ●●●). fail-safe: 소스 조회
    #     실패·부재 시 build 진행(불확실 → 업로드), 이 함수의 fail-safe 헌장 정합.
    if _should_skip_bundle_upload(get_vault_root(), abs_files) and _bundle_source_exists(
        client, notebook_id, bundle_name
    ):
        return {
            "notebook_id": notebook_id,
            "bundle_name": bundle_name,
            "source_id": "",
            "source_ids": [],
            "title": f"{bundle_name}.md",
            "mode": "skip",
            "parts": 0,
            "bundled_count": len(abs_files),
            "message": (
                f"Bundle '{bundle_name}' skipped — "
                "no origin changes since last NLM sync anchor."
            ),
        }

    # 3. Bundle build (temp dir; auto-cleanup on exit) — 1:N chunking Full-Sync.
    script = bundle_tool_script or _BUNDLE_TOOL_SCRIPT
    if not script.exists():
        raise ServiceError(
            f"Bundle tool not found at {script}",
            user_message="Bundle generator script missing.",
            hint="Verify the sirpan-notebooklm-mcp repo layout (src/notebooklm_tools/scripts/generate_bundle_md.py).",
        )
    py = python_executable or sys.executable
    max_words = bundle.get("max_words")
    if not isinstance(max_words, int) or max_words <= 0:
        max_words = _DEFAULT_BUNDLE_MAX_WORDS
    output_stub = f"{bundle_name}.md"

    with tempfile.TemporaryDirectory(prefix="nlm-sync-bundle-") as tmpdir:
        cmd = [
            py,
            str(script),
            "--files",
            *[str(p) for p in abs_files],
            "--output",
            str(Path(tmpdir) / output_stub),
            "--bundle-name",
            bundle_name,
            "--max-words",
            str(max_words),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            raise ServiceError(
                f"Bundle build failed (exit {proc.returncode}): {proc.stderr.strip()}",
                user_message="Bundle generation failed; original NLM source unchanged.",
            )
        # Parse the JSON part manifest (single-line stdout contract, --max-words).
        try:
            payload = json.loads(proc.stdout.strip())
            part_paths = [Path(p) for p in payload["parts"]]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ServiceError(
                f"Bundle tool returned malformed output: {proc.stdout!r}",
                user_message="Bundle generation output could not be parsed.",
            ) from e
        if not part_paths:
            raise ServiceError(
                "Bundle tool produced no parts",
                user_message="Bundle generation yielded nothing.",
            )
        generated_titles = {p.name for p in part_paths}

        # 4. Snapshot existing NLM sources for this bundle name — the single
        #    `{name}.md` and every `{name}_part…`. Best-effort (fresh-add on error).
        existing: dict[str, str] = {}  # title -> source_id
        try:
            for src in client.get_notebook_sources_with_types(notebook_id):
                t = src.get("title")
                sid = src.get("id")
                if not isinstance(t, str) or not isinstance(sid, str):
                    continue
                if t == output_stub or t.startswith(f"{bundle_name}_part"):
                    existing[t] = sid
        except Exception:
            existing = {}

        # 5. ADD/REPLACE every generated part FIRST (knowledge secured),
        #    then DELETE stale parts LAST — zero knowledge gap (NLM 반론2).
        source_ids: list[str] = []
        first_mode: Literal["add", "replace"] = "add"
        for i, part_path in enumerate(part_paths):
            part_title = part_path.name
            if part_title in existing:
                res = replace_source_file(
                    client,
                    notebook_id,
                    str(part_path),
                    source_id=existing[part_title],
                    atomic=True,
                )
                sid = res["new_source_id"]
                mode: Literal["add", "replace"] = "replace"
            else:
                res = add_source(
                    client,
                    notebook_id,
                    "file",
                    file_path=str(part_path),
                    title=part_title,
                )
                sid = res["source_id"]
                mode = "add"
            source_ids.append(sid)
            if i == 0:
                first_mode = mode

        # 6. Delete stale parts no longer produced (Full-Sync, DELETE-last).
        stale = [(t, sid) for t, sid in existing.items() if t not in generated_titles]
        for _t, sid in stale:
            delete_source(client, sid, notebook_id=notebook_id)

        parts = len(part_paths)
        return {
            "notebook_id": notebook_id,
            "bundle_name": bundle_name,
            "source_id": source_ids[0],
            "source_ids": source_ids,
            "title": output_stub if parts == 1 else f"{bundle_name}_part1.md",
            "mode": first_mode,
            "parts": parts,
            "bundled_count": len(abs_files),
            "message": (
                f"Synced bundle '{bundle_name}' ({len(abs_files)} files → {parts} part(s)): "
                f"{len(source_ids)} source(s), {len(stale)} stale removed"
            ),
        }
