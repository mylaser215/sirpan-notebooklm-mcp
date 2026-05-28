"""NLM source ↔ vault disk 매핑 + drift 감지 헬퍼.

NLM 동기화 본 흐름의 *영구 라이브러리*. ``force_v4_resync.py``의 1회성
매핑 알고리즘을 일반화하여 다음 두 곳에서 재사용:

1. 1회성 강제 재 동기화 스크립트 (``_temp_bin/force_v4_resync.py``)
2. 매일 NLM 동기화 본 흐름 — drift 감지 + 보고 (CLAUDE.md NLM동기화 절 ⑥)

환경 의존성은 ``SIRPAN_VAULT`` 환경변수로 override 가능.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

# 기본값: 현 사용자 환경. 다른 사용자는 SIRPAN_VAULT 환경변수로 override.
_DEFAULT_VAULT = Path("C:/Users/Administrator/ObsidianVault_FLAT")


def get_vault_root() -> Path:
    """SIRPAN_VAULT 환경변수 우선, 없으면 기본값."""
    env = os.environ.get("SIRPAN_VAULT")
    return Path(env) if env else _DEFAULT_VAULT


SKIP_DIRS: frozenset[str] = frozenset(
    {".obsidian", ".smart-env", ".trash", "_archive", ".git"}
)

EXTERNAL_FILE_MAP: dict[str, Path] = {
    "CLAUDE.md": Path.home() / ".claude" / "CLAUDE.md",
    "settings.json": Path.home() / ".claude" / "settings.json",
    "mcp_launcher.py": Path.home() / "bin" / "mcp_launcher.py",
    "sirpan-sidebar_main.ts": Path(
        "C:/Users/Administrator/Documents/_work/260203_claude/260407_sirpan-agent/src/sirpan-sidebar_main.ts"
    ),
}

PRIORITY_FOLDERS: tuple[str, ...] = (
    "000-시스템/050-Docs",
    "000-시스템/060-Automations/sirpan-tools",
    "000-시스템/070-세션로그",
    "000-시스템",
    "300-작업중",
    "500-지식정원",
    "100-인박스",
)

NLM_SEED_SKILL_KEYWORDS: dict[str, str] = {
    "단교차": "cross_3step_solver",
    "배치교차": "batch_cross_3step_solver",
    "시스템정비": "system_maintenance",
}

_VERSION_SUFFIX_RE = re.compile(r"_v\d+(?:\.\d+)*(?=\.\w+$)")
_KNOWN_EXTS: tuple[str, ...] = (".md", ".py", ".json", ".tsx", ".ts", ".js", ".txt")


def extract_filename(title: str) -> str:
    """title 에서 첫 *.md/*.py/*.json/*.ts(x)/*.js/*.txt 토큰 추출.

    예: 'CC 프로젝트.md (세션289 ...)' -> 'CC 프로젝트.md'
        'guard_fm_edit.py (9차정비 ...)' -> 'guard_fm_edit.py'
    매칭 실패 시 원본 그대로 반환.
    """
    s = title.strip()
    for ext in _KNOWN_EXTS:
        idx = s.find(ext)
        if idx != -1:
            return s[: idx + len(ext)]
    return s


def extract_skill_name(title: str) -> str | None:
    """SKILL.md (skill_name, ...) -> skill_name."""
    s = title.strip()
    if not s.startswith("SKILL.md"):
        return None
    m = re.search(r"SKILL\.md\s*\(([^,)]+)", s)
    if m:
        return m.group(1).strip()
    return None


def _glob_vault(filename: str, vault_root: Path) -> list[Path]:
    seen: set[Path] = set()
    matches: list[Path] = []
    for p in vault_root.rglob(filename):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p not in seen:
            seen.add(p)
            matches.append(p)
    return matches


def _narrow_by_priority(matches: list[Path], vault_root: Path) -> list[Path]:
    """다중 매칭 시 PRIORITY_FOLDERS 순서대로 좁히기."""
    if len(matches) <= 1:
        return matches
    for prio in PRIORITY_FOLDERS:
        prio_path = vault_root / prio
        prio_matches = [p for p in matches if str(p).startswith(str(prio_path))]
        if len(prio_matches) == 1:
            return prio_matches
    return matches


def _narrow_by_folder_hint(title: str, matches: list[Path]) -> list[Path]:
    """title 안 폴더 hint로 다중 매칭 좁히기.

    호환 (NLM_SEED_SKILL_KEYWORDS): 한글 메타 키워드(`단교차`/`배치교차`/`시스템정비`)가
    title에 있으면 매핑 폴더로 좁힘. nlm_seed.md 기존 호출자 자연 흡수.

    신규 (v7, 260528 ATOM-2): 모든 파일에 `{filename} ({folder})` 패턴 영문 폴더명
    직접 매칭 적용. 동명 다폴더 ambiguous → matched 결정론 전환.

    parent 폴더명이 *정확히* hint와 일치하는지 검사
    (substring 매칭은 cross_3step_solver ⊂ batch_cross_3step_solver 충돌).
    """
    if len(matches) <= 1:
        return matches
    # 호환: 한글 키워드 매핑 (nlm_seed.md 기존 호출자)
    for keyword, skill in NLM_SEED_SKILL_KEYWORDS.items():
        if keyword in title:
            narrowed = [p for p in matches if p.parent.name == skill]
            if len(narrowed) == 1:
                return narrowed
    # 신규: 영문 폴더명 직접 매칭 (`{filename} ({folder})` 패턴)
    m = re.search(r"\(([^,)]+)\)", title)
    if m:
        folder_name = m.group(1).strip()
        narrowed = [p for p in matches if p.parent.name == folder_name]
        if len(narrowed) == 1:
            return narrowed
    return matches


def find_disk_path(title: str, *, vault_root: Path | None = None) -> list[Path]:
    """NLM source title → 디스크 경로 매핑. 0개(NLM 잔재) / 1개(매핑 OK) / 2+개(모호)."""
    root = vault_root or get_vault_root()
    fname = extract_filename(title)

    # 1. 외부 파일 매핑
    if fname in EXTERNAL_FILE_MAP:
        ext_path = EXTERNAL_FILE_MAP[fname]
        return [ext_path] if ext_path.exists() else []

    # 2. SKILL.md 특수 처리
    skill = extract_skill_name(title)
    if skill:
        skill_path = Path.home() / ".claude" / "skills" / skill / "SKILL.md"
        return [skill_path] if skill_path.exists() else []

    # 3. 볼트 글로브
    matches = _glob_vault(fname, root)

    # 4. 폴더 hint로 좁히기 (우선순위 폴더보다 먼저)
    #    호환: nlm_seed.md NLM_SEED_SKILL_KEYWORDS 매핑 + 신규: 모든 파일 `{name} ({folder})` 패턴
    narrowed = _narrow_by_folder_hint(title, matches)
    if len(narrowed) == 1:
        return narrowed

    matches = _narrow_by_priority(narrowed, root)
    if len(matches) == 1:
        return matches

    # 5. 폴백 변이
    if not matches:
        if not fname.lower().endswith(".md"):
            matches = _glob_vault(f"{fname}.md", root)
            if matches:
                return _narrow_by_priority(matches, root)
        if "." not in fname:
            matches = _glob_vault(f"{fname}.py", root)
            if matches:
                return _narrow_by_priority(matches, root)
        stripped = _VERSION_SUFFIX_RE.sub("", fname)
        if stripped != fname:
            matches = _glob_vault(stripped, root)
            if matches:
                return _narrow_by_priority(matches, root)

    return matches


class DriftEntry(TypedDict):
    source_id: str
    title: str
    type_name: str
    status: str  # "matched" | "missing" | "ambiguous" | "skip_type"
    disk_path: str | None
    candidates: list[str]
    markdown_relevant: bool  # True 면 .md → markdown 파서 라우팅 적용 대상 (v4 결함 학습)


class DriftReport(TypedDict):
    notebook_id: str
    total: int
    matched: list[DriftEntry]
    matched_markdown: list[DriftEntry]  # matched 중 .md 확장자만 — 진짜 markdown 라우팅 후보
    matched_non_markdown: list[DriftEntry]  # matched 중 .py/.json/.ts 등 — plain text 정상
    missing: list[DriftEntry]
    ambiguous: list[DriftEntry]
    skip_type: list[DriftEntry]


def detect_drift(
    sources_fetcher: Callable[[str], list[dict[str, Any]]],
    notebook_id: str,
    *,
    vault_root: Path | None = None,
    relevant_types: tuple[str, ...] = ("generated_text", "pasted_text"),
) -> DriftReport:
    """NLM 노트북의 source 전체를 디스크와 매핑하여 drift 분류.

    Args:
        sources_fetcher: 호출 시 ``[{"id", "title", "source_type_name"}, ...]`` 반환.
            보통 ``client.get_notebook_sources_with_types`` 를 직접 전달.
        notebook_id: 점검 대상 노트북 UUID.
        vault_root: 볼트 루트 override (기본은 ``SIRPAN_VAULT`` 또는 hard-coded).
        relevant_types: drift 검사 대상 source type. 외 type은 ``skip_type`` 분류.

    Returns:
        DriftReport — matched/missing/ambiguous/skip_type 분류 + 카운트.
    """
    sources = sources_fetcher(notebook_id)
    matched: list[DriftEntry] = []
    missing: list[DriftEntry] = []
    ambiguous: list[DriftEntry] = []
    skip_type: list[DriftEntry] = []

    for s in sources:
        title = (s.get("title") or "").strip()
        sid = s.get("id") or ""
        type_name = (s.get("source_type_name") or "").lower()

        if type_name not in relevant_types:
            skip_type.append(
                {
                    "source_id": sid,
                    "title": title,
                    "type_name": type_name,
                    "status": "skip_type",
                    "disk_path": None,
                    "candidates": [],
                    "markdown_relevant": False,
                }
            )
            continue

        candidates = find_disk_path(title, vault_root=vault_root)
        # markdown_relevant 판정: 디스크 파일명이 .md 확장자 (v4 결함 학습 — markdown 파서는 .md만)
        is_md = (
            len(candidates) == 1
            and candidates[0].suffix.lower() == ".md"
        )
        if len(candidates) == 1:
            matched.append(
                {
                    "source_id": sid,
                    "title": title,
                    "type_name": type_name,
                    "status": "matched",
                    "disk_path": str(candidates[0]),
                    "candidates": [],
                    "markdown_relevant": is_md,
                }
            )
        elif len(candidates) == 0:
            missing.append(
                {
                    "source_id": sid,
                    "title": title,
                    "type_name": type_name,
                    "status": "missing",
                    "disk_path": None,
                    "candidates": [],
                    "markdown_relevant": False,
                }
            )
        else:
            ambiguous.append(
                {
                    "source_id": sid,
                    "title": title,
                    "type_name": type_name,
                    "status": "ambiguous",
                    "disk_path": None,
                    "candidates": [str(p) for p in candidates],
                    "markdown_relevant": False,
                }
            )

    matched_markdown = [m for m in matched if m["markdown_relevant"]]
    matched_non_markdown = [m for m in matched if not m["markdown_relevant"]]

    return {
        "notebook_id": notebook_id,
        "total": len(sources),
        "matched": matched,
        "matched_markdown": matched_markdown,
        "matched_non_markdown": matched_non_markdown,
        "missing": missing,
        "ambiguous": ambiguous,
        "skip_type": skip_type,
    }


def format_drift_summary(report: DriftReport) -> str:
    """drift 보고를 한 줄 요약 + 상세 list로 포매팅.

    NLM동기화 본 흐름 끝에 출력하는 형식 (v4 결함 학습 반영 — markdown_relevant 분리):
        📊 drift 점검: 53 markdown(.md) / 23 non-md(plain text 정상) / 8 NLM 잔재 / 1 모호
    """
    mm = len(report["matched_markdown"])
    mn = len(report["matched_non_markdown"])
    ms = len(report["missing"])
    a = len(report["ambiguous"])
    st = len(report["skip_type"])
    parts = [
        f"📊 drift 점검: {mm} markdown(.md) / {mn} non-md(plain text 정상)"
        f" / {ms} NLM 잔재 / {a} 모호 / {st} type-skip"
    ]
    if ms > 0 or a > 0:
        parts.append(" — 청소·매핑 보강 권고")
    summary = "".join(parts)
    if ms > 0:
        summary += "\n  NLM 잔재 (디스크 원본 없음):"
        for entry in report["missing"][:10]:
            summary += f"\n    - [{entry['source_id'][:8]}] {entry['title'][:60]}"
        if ms > 10:
            summary += f"\n    ... +{ms - 10} more"
    if a > 0:
        summary += "\n  모호 (다중 매칭):"
        for entry in report["ambiguous"][:5]:
            summary += (
                f"\n    - [{entry['source_id'][:8]}] {entry['title'][:60]}"
                f" → {len(entry['candidates'])} candidates"
            )
        if a > 5:
            summary += f"\n    ... +{a - 5} more"
    return summary
