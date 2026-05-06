"""1회성 진단 — v3 회귀 원인 캡처. 결과 확인 후 _temp_bin/ 삭제 가능.

증상: source_get_content/source_describe(notebook_id 포함)가 모든 source를
  source_type=generated_text + content="" 응답. source_delete(notebook_id)는
  delete_note RPC로 잘못 라우팅 → 실패. notebook_id 빼면 일반 RPC tGMBJ 정상.
가설:
  H1) get_notebook_sources_with_types의 metadata[4] 파싱 오류 (백엔드 응답 변경)
  H2) _resolve_source_type fallback의 list_notes가 일반 source까지 note로 반환
  H3) NLM 백엔드 변경 — get_notebook 응답에서 source_type 위치 이동
"""
from __future__ import annotations

import json
import sys
from typing import Any

from notebooklm_tools.core.auth import load_cached_tokens
from notebooklm_tools.core.client import NotebookLMClient

NOTEBOOK_ID = "1ffa3a16-f609-4221-8040-da02f2f78158"
SOURCE_ID_TEXT = "4455b0f4-4c75-43e3-8d9b-39da2b3cfcc8"


def _truncate_json(obj: Any, limit: int = 4000) -> str:
    s = json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n... (truncated, total {len(s)} chars)"


def main() -> int:
    tokens = load_cached_tokens()
    if not tokens:
        print("ERROR: No cached tokens. Run `nlm login` first.", file=sys.stderr)
        return 1

    client = NotebookLMClient(cookies=tokens.cookies)

    print("=" * 60)
    print("[1] get_notebook 원시 응답 (raw payload)")
    print("=" * 60)
    raw = client.get_notebook(NOTEBOOK_ID)
    print(f"type: {type(raw).__name__}")
    if hasattr(raw, "__len__"):
        print(f"top-level len: {len(raw)}")
    print(_truncate_json(raw, limit=4000))

    print()
    print("=" * 60)
    print("[2] get_notebook_sources_with_types — 클라이언트 파싱 결과")
    print("=" * 60)
    sources = client.get_notebook_sources_with_types(NOTEBOOK_ID)
    print(f"sources count: {len(sources)}")
    for i, s in enumerate(sources[:10]):
        sid = (s.get("id") or "")[:8]
        title = (s.get("title") or "")[:30]
        st = s.get("source_type")
        drive = s.get("drive_doc_id")
        print(f"  [{i}] id={sid}... source_type={st!r} title={title!r} drive={drive}")

    print()
    print("=" * 60)
    print("[3] list_notes 응답")
    print("=" * 60)
    notes = []
    try:
        notes = client.list_notes(NOTEBOOK_ID)
        print(f"notes count: {len(notes)}")
        for i, n in enumerate(notes[:10]):
            nid = (n.get("id") or "")[:8]
            title = (n.get("title") or "")[:30]
            content_len = len(n.get("content") or "")
            print(f"  [{i}] id={nid}... title={title!r} content_len={content_len}")
    except Exception as e:
        print(f"list_notes ERROR: {e}")

    print()
    print("=" * 60)
    print(f"[4] H1/H2 검증 — source_id={SOURCE_ID_TEXT[:8]}... (file 타입 일반 source)")
    print("=" * 60)
    in_sources = any(s.get("id") == SOURCE_ID_TEXT for s in sources)
    in_notes = any(n.get("id") == SOURCE_ID_TEXT for n in notes)
    print(f"  in get_notebook_sources_with_types: {in_sources}")
    print(f"  in list_notes: {in_notes}")
    matched_source = next((s for s in sources if s.get("id") == SOURCE_ID_TEXT), None)
    if matched_source:
        print(f"  matched source: {matched_source}")
    matched_note = next((n for n in notes if n.get("id") == SOURCE_ID_TEXT), None)
    if matched_note:
        print(f"  matched note (잘못 매칭): keys={list(matched_note.keys())}")

    print()
    print("=" * 60)
    print("[5] H1 보강 — 임의 source 1건 metadata 배열 전체 dump (인덱스 위치 확인)")
    print("=" * 60)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        notebook_data = raw[0]
        sources_data = notebook_data[1] if len(notebook_data) > 1 else []
        if isinstance(sources_data, list) and sources_data:
            first_src = sources_data[0]
            print(f"first src structure (len={len(first_src)}):")
            print(_truncate_json(first_src, limit=2000))
            if len(first_src) > 2 and isinstance(first_src[2], list):
                metadata = first_src[2]
                print(f"\nmetadata len: {len(metadata)}")
                for i, m in enumerate(metadata):
                    typ = type(m).__name__
                    val = repr(m)[:80]
                    print(f"  metadata[{i}] type={typ} value={val}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
