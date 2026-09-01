"""NLM source ↔ vault disk 매핑 + drift 감지 헬퍼.

NLM 동기화 본 흐름의 *영구 라이브러리*. ``force_v4_resync.py``의 1회성
매핑 알고리즘을 일반화하여 다음 두 곳에서 재사용:

1. 1회성 강제 재 동기화 스크립트 (``_temp_bin/force_v4_resync.py``)
2. 매일 NLM 동기화 본 흐름 — drift 감지 + 보고 (CLAUDE.md NLM동기화 절 ⑥)

환경 의존성은 ``SIRPAN_VAULT`` 환경변수로 override 가능.
"""

from __future__ import annotations

import glob as _glob
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

# 기본값: 현 사용자 환경. 다른 사용자는 SIRPAN_VAULT 환경변수로 override.
_DEFAULT_VAULT = Path("C:/Users/Administrator/ObsidianVault_FLAT")


def get_vault_root() -> Path:
    """SIRPAN_VAULT 환경변수 우선, 없으면 기본값."""
    env = os.environ.get("SIRPAN_VAULT")
    return Path(env) if env else _DEFAULT_VAULT


# NLM동기화 앵커 (커밋 해시). CLAUDE.md NLM동기화 절 ⑤와 동일 경로 SSOT.
_NLM_SYNC_ANCHOR_REL = "000-시스템/050-Docs/.last_nlm_sync"


def _should_skip_bundle_upload(vault_root: Path, bundle_files: list[Path]) -> bool:
    """번들 원본이 마지막 NLM동기화 앵커 이후 git 변경이 없으면 True(업로드 skip).

    v10 I/O 병목 최적화 — 변경 없는 Tier 2 번들은 무거운 bundle 렌더(subprocess)
    + NLM source 조회/업로드를 원천 회피. 호출자(``sync_bundle``)는 Pre-flight
    origin 존재 확인 *직후*, bundle build *직전*에 호출한다.

    **Fail-safe 우선** — 아래 모든 불확실 상황은 ``False`` (변경 있다고 간주 =
    업로드) 반환:
    - ``bundle_files`` 빈 리스트 → ``git diff … --`` 뒤 경로 없으면 볼트 전체
      스캔 (Empty List 덫, 세션409 NLM 7차 ●●●).
    - 앵커 파일 부재/빈값 (첫 동기화 등).
    - git 실행 실패 또는 ``returncode != 0`` (무효 앵커 등).

    경로는 ``os.path.relpath``로 볼트 상대경로 변환 (절대경로면 git 0건 반환).
    Windows 백슬래시 relpath는 git이 정상 처리 (세션409 dry-run 실측) — posix
    변환 불필요.
    """
    if not bundle_files:
        return False
    anchor_file = vault_root / _NLM_SYNC_ANCHOR_REL
    try:
        anchor = anchor_file.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not anchor:
        return False
    rel = [os.path.relpath(str(Path(f)), str(vault_root)) for f in bundle_files]
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", anchor, "--", *rel],
            cwd=str(vault_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    if proc.stdout.strip():
        return False  # tracked 변경 있음 → 업로드
    # untracked/staged 도 검사 — ``git diff <anchor>``는 **untracked 파일을
    # 출력하지 않는다**. "신규 회차 파일 생성 → registry glob 자동 편입 →
    # 커밋 전 sync_bundle 호출" 시 기존 원본 무변경 + 신규 파일 diff 미출력
    # → skip 오판으로 신규 회차 누락. git status로 봉쇄 (세션493 신드리 ●●●).
    try:
        proc2 = subprocess.run(
            ["git", "status", "--porcelain", "--", *rel],
            cwd=str(vault_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc2.returncode != 0:
        return False
    return not proc2.stdout.strip()


SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".obsidian", ".smart-env", ".trash", "_archive", ".git",
        # 빌드/캐시/의존성 노이즈 — 정당 소스가 존재할 수 없는 산출 디렉토리.
        # `.pytest_cache/README.md`가 sirpan-tools prio 안에 함께 잡혀
        # `_narrow_by_priority`의 len==1 조기반환을 붕괴시켜 README.md ambiguous를
        # 유발한 근본원인 (세션492, NLM ●●●+신드리 ●●○ 실측). 나머지는 재발 방어.
        ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
        "node_modules", ".venv", "venv",
    }
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
_PROCESSED_TAIL_RE = re.compile(r"\.(py|ts|tsx|json|js|yaml|yml|toml)\.md$")


_FM_BLOCK_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---", re.DOTALL)


def check_processed_stale(md_path: Path, *, vault_root: Path | None = None) -> str | None:
    """`.{ext}.md` 가공물의 *내용* stale 판정 (세션540 신설).

    `detect_drift`의 basename 매핑은 소스가 디스크에 *존재하는지*만 보므로, 원본
    코드가 갱신됐는데 `generate_code_md.py` 재가공을 빠뜨리면 NLM에 구버전이 무음
    잔존한다 — 층3 구조적 사각(세션533 신드리 지적, 실측 1건 발견·해소).
    `generate_code_md.py --check`와 같은 판정(FM `original_sha256` vs 현재 원본
    해시)을 하되, CLI 인자로 원본 경로를 받는 대신 **FM `source_path`에서 스스로
    되찾아** 스윕이 가능하도록 한다.

    Returns:
        ``None``  — 가공물이 아니거나 fresh (정상)
        ``"stale"`` — 원본이 갱신됐는데 재가공 누락
        ``"origin_missing"`` — FM이 가리키는 원본이 디스크에 없음
        ``"fm_broken"`` — FM에 source_path/original_sha256이 없음 (규격 이탈)
    """
    if not _PROCESSED_TAIL_RE.search(md_path.name):
        return None
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "fm_broken"
    m = _FM_BLOCK_RE.search(text)
    if not m:
        return "fm_broken"
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        key, sep, val = line.partition(":")
        if sep:
            fields[key.strip()] = val.strip().strip('"').strip("'")
    src_raw = fields.get("source_path")
    recorded = fields.get("original_sha256")
    if not src_raw or not recorded:
        return "fm_broken"
    src = Path(src_raw)
    if not src.is_absolute():
        # 옛 가공물은 cwd 기준 상대경로일 수 있다 (세션540에 생성기 기본값을 절대경로로
        # 고정했으나 기존 산출물 호환). 볼트 루트 기준으로 해석 시도.
        src = (vault_root or get_vault_root()) / src_raw
    if not src.is_file():
        return "origin_missing"
    try:
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
    except OSError:
        return "origin_missing"
    return None if digest == recorded else "stale"


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
        # 신설: auto_wrap_to_md / generate_code_md.py 가공 꼬리 (.json.md → .json)
        if _PROCESSED_TAIL_RE.search(fname):
            raw = _PROCESSED_TAIL_RE.sub(
                lambda m: f".{m.group(1)}", fname
            )
            # 볼트밖 외부 매핑 재조회 — 진입부(위 EXTERNAL_FILE_MAP 조회)는 원형
            # fname(가공 꼬리 .md 포함)으로만 조회하므로 raw 키를 놓친다. 가공 꼬리를
            # 뗀 raw 로 재조회해 볼트밖 매핑(예: sirpan-sidebar_main.ts) missing 오탐 방지.
            if raw in EXTERNAL_FILE_MAP:
                ext_path = EXTERNAL_FILE_MAP[raw]
                return [ext_path] if ext_path.exists() else []
            matches = _glob_vault(raw, root)
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


class DriftEntry(TypedDict, total=False):
    """drift 분류 1건. total=False — 신규 옵셔널 키 (bundle_origins) 호환."""

    source_id: str
    title: str
    type_name: str
    status: str  # "matched" | "missing" | "ambiguous" | "skip_type" | "matched_bundle"
    disk_path: str | None
    candidates: list[str]
    markdown_relevant: bool  # True 면 .md → markdown 파서 라우팅 적용 대상 (v4 결함 학습)
    bundle_origins: list[str]  # 옵셔널 — matched_bundle 시 원본 N개 경로 (Tier 2 번들)


class DriftReport(TypedDict):
    notebook_id: str
    total: int
    matched: list[DriftEntry]
    matched_markdown: list[DriftEntry]  # matched 중 .md 확장자만 — 진짜 markdown 라우팅 후보
    matched_non_markdown: list[DriftEntry]  # matched 중 .py/.json/.ts 등 — plain text 정상
    matched_bundle: list[DriftEntry]  # Tier 2 N:1 번들 (registry 매칭) — Batch 3 신설
    bundle_origin_dup: list[DriftEntry]  # 번들 원본이 낱개로 재업로드됨 (세션493 신설)
    dup_disk_path: list[DriftEntry]  # 서로 다른 소스가 같은 디스크 파일을 가리킴 (세션540 신설)
    stale_processed: list[DriftEntry]  # `.{ext}.md` 가공물 내용 stale — matched의 파생 뷰 (세션540 신설)
    missing: list[DriftEntry]
    ambiguous: list[DriftEntry]
    skip_type: list[DriftEntry]


# ---------------------------------------------------------------------------
# Tier 2 N:1 번들 매핑 (Batch 3 ATOM-1)
# ---------------------------------------------------------------------------

# Bundle title → (name, optional part number). Non-greedy `.+?` peels an
# optional `_partN` suffix so 1:N chunked bundles (`{name}_part1.md`) map back
# to `{name}`. No hard-coded `_Bundle` suffix — the registry-key check in
# _classify_bundle is the sole gate (실측: 실 registry 키는 `NLM_MCP_Archive`
# 처럼 `_Bundle` 접미사가 없어 옛 정규식이 matched_bundle 인식을 못 했음).
_BUNDLE_TITLE_RE = re.compile(
    r"^(?P<name>.+?)(?:_part(?P<part>\d+))?\.md$", re.IGNORECASE
)


def expand_bundle_files(files: list[str]) -> list[Path]:
    """registry ``files`` 항목을 절대경로 Path 리스트로 확장 (glob 지원, 세션493).

    항목에 glob 메타문자(``*?[``)가 있으면 :func:`glob.glob` 확장 후 **정렬**
    (번들 렌더 순서 결정론 — RAG chunk 순서 안정). 없으면 리터럴 Path 그대로
    (실존 여부는 호출자 Pre-flight가 판정). glob 확장분은 실존 파일만 산출하므로
    삭제된 원본이 자동 필터된다.

    sync_bundle(sources.py)의 abs_files 구성과 detect_drift의 번들 origin
    집합 구성이 **동일 로직을 공유**하도록 하는 SSOT — registry가 ``*.md``
    glob 1줄로 폴더 전체를 등재해도 두 경로가 같은 파일 셋을 본다.
    """
    out: list[Path] = []
    for f in files:
        if any(ch in f for ch in "*?["):
            out.extend(Path(p) for p in sorted(_glob.glob(f)))
        else:
            out.append(Path(f))
    return out


def _default_bundle_registry_path() -> Path:
    return get_vault_root() / "000-시스템" / "030-Configs" / "시스템환경" / "nlm_bundle_registry.json"


def load_bundle_registry(registry_path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Tier 2 번들 매핑 SSOT 로드. Fail-safe — 파일 없음/JSON 결함 시 빈 dict.

    Returns: ``{bundle_name: {"domain": str, "files": [str, ...]}}``.
    빈 dict 반환은 detect_drift 기존 1:1 흐름과 정합 (회귀 0).
    """
    path = registry_path or _default_bundle_registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    bundles = data.get("bundles", {})
    return bundles if isinstance(bundles, dict) else {}


def _classify_bundle(
    title: str, registry: dict[str, dict[str, Any]]
) -> tuple[str | None, list[str]]:
    """title 이 ``{name}.md`` 또는 ``{name}_partN.md`` + registry 매칭 시
    (bundle_name, origins) 반환. part 번호는 무시하고 동일 도메인 origins
    서브셋 전체를 반환 (분할 part 다수가 같은 번들 기원으로 묶임).

    매칭 실패(또는 name 이 registry 미등록)면 ``(None, [])`` — 호출자는 기존
    1:1 매칭 흐름으로 폴백. registry-key 존재 검사가 유일한 FP 게이트.
    """
    m = _BUNDLE_TITLE_RE.match(title.strip())
    if not m:
        return (None, [])
    bundle_name = m.group("name")
    entry = registry.get(bundle_name)
    if not entry or not isinstance(entry, dict):
        return (None, [])
    files = entry.get("files")
    if not isinstance(files, list):
        return (None, [])
    return (bundle_name, [str(f) for f in files])


def detect_drift(
    sources_fetcher: Callable[[str], list[dict[str, Any]]],
    notebook_id: str,
    *,
    vault_root: Path | None = None,
    relevant_types: tuple[str, ...] = ("generated_text", "pasted_text"),
    bundle_registry_path: Path | None = None,
) -> DriftReport:
    """NLM 노트북의 source 전체를 디스크와 매핑하여 drift 분류.

    Args:
        sources_fetcher: 호출 시 ``[{"id", "title", "source_type_name"}, ...]`` 반환.
            보통 ``client.get_notebook_sources_with_types`` 를 직접 전달.
        notebook_id: 점검 대상 노트북 UUID.
        vault_root: 볼트 루트 override (기본은 ``SIRPAN_VAULT`` 또는 hard-coded).
        relevant_types: drift 검사 대상 source type. 외 type은 ``skip_type`` 분류.
        bundle_registry_path: Tier 2 번들 매핑 SSOT override (기본은 볼트
            ``030-Configs/시스템환경/nlm_bundle_registry.json``).

    Returns:
        DriftReport — matched/matched_bundle/bundle_origin_dup/dup_disk_path/
        stale_processed/missing/ambiguous/skip_type 분류 + 카운트.
        ``dup_disk_path``(세션540)는 disk_path 역방향 유일성 위반(중복 소스),
        ``stale_processed``(세션540)는 `.{ext}.md` 가공물 내용 stale의 파생 뷰다.
    """
    sources = sources_fetcher(notebook_id)
    matched: list[DriftEntry] = []
    matched_bundle: list[DriftEntry] = []
    bundle_origin_dup: list[DriftEntry] = []
    missing: list[DriftEntry] = []
    ambiguous: list[DriftEntry] = []
    skip_type: list[DriftEntry] = []

    bundle_registry = load_bundle_registry(bundle_registry_path)
    # 번들 원본 flat 집합 (glob 확장·정규화) — 낱개 재업로드 사후 감지용.
    # registry에 등재된 원본이 번들이 아닌 *낱개 소스*로 본관에 올라오면
    # (라우팅 규칙 미준수 재발) matched 대신 bundle_origin_dup으로 분류해
    # detect_drift(⑥)가 자동 포착 (세션493 신드리 ●●● — 기존엔 matched로
    # silent 통과해 재발을 영영 못 잡던 사각).
    bundle_origins_all: set[str] = set()
    for _entry in bundle_registry.values():
        _fl = _entry.get("files") if isinstance(_entry, dict) else None
        if isinstance(_fl, list):
            for _p in expand_bundle_files([str(x) for x in _fl]):
                try:
                    bundle_origins_all.add(str(_p.resolve()).lower())
                except OSError:
                    bundle_origins_all.add(str(_p).lower())

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

        # Tier 2 N:1 번들 분기 (Batch 3 ATOM-1) — 기존 1:1 흐름보다 먼저
        bundle_name, origins = _classify_bundle(title, bundle_registry)
        if bundle_name is not None:
            matched_bundle.append(
                {
                    "source_id": sid,
                    "title": title,
                    "type_name": type_name,
                    "status": "matched_bundle",
                    "disk_path": None,
                    "candidates": [],
                    "markdown_relevant": True,
                    "bundle_origins": origins,
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
            try:
                _disk_key = str(candidates[0].resolve()).lower()
            except OSError:
                _disk_key = str(candidates[0]).lower()
            if _disk_key in bundle_origins_all:
                # 번들 원본인데 낱개 소스로 올라옴 = 라우팅 규칙 미준수 재발
                bundle_origin_dup.append(
                    {
                        "source_id": sid,
                        "title": title,
                        "type_name": type_name,
                        "status": "bundle_origin_dup",
                        "disk_path": str(candidates[0]),
                        "candidates": [],
                        "markdown_relevant": False,
                    }
                )
            else:
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

    # disk_path 역방향 유일성 검사 (세션540 신설, 신드리 ●●●).
    # 위 루프는 source→disk 단방향만 본다. 서로 다른 제목의 소스 2개가 같은 디스크
    # 파일로 매핑되면 둘 다 각자 len(candidates)==1이라 나란히 matched로 통과하고,
    # 중복은 "N matched" 총계 안에 영구 은폐된다 — 잔재도 모호도 아니므로 어떤
    # 버킷도 울리지 않는다. 세션540 실증: `SKILL.md (suno-lyric-refine)`와
    # `suno-lyric-refine/SKILL.md`(기각된 슬래시형 잔재)가 같은 파일을 가리키며
    # 공존했고, 그날 drift는 "잔재 0"으로 깨끗하게 보고했다. 그 깨끗함이 곧 사각의
    # 증거였다. bundle_origin_dup(세션493)과 동일한 사후 감지 패턴.
    dup_disk_path: list[DriftEntry] = []
    by_disk: dict[str, list[DriftEntry]] = {}
    for m in matched:
        disk_path = m.get("disk_path")
        if disk_path:
            by_disk.setdefault(disk_path.lower(), []).append(m)
    for group in by_disk.values():
        if len(group) > 1:
            for entry in group:
                entry["status"] = "dup_disk_path"
                entry["markdown_relevant"] = False
                dup_disk_path.append(entry)
    if dup_disk_path:
        dup_ids = {e["source_id"] for e in dup_disk_path}
        matched = [m for m in matched if m["source_id"] not in dup_ids]

    matched_markdown = [m for m in matched if m["markdown_relevant"]]
    matched_non_markdown = [m for m in matched if not m["markdown_relevant"]]

    # 층3 — 가공물 *내용* stale 스윕 (세션540 신설, 신드리 ●●○ Q4).
    # 기존 검사는 "디스크에 파일이 있는가"만 봐서 원본 갱신 후 재가공 누락을 구조적으로
    # 못 봤다. 여기서 FM `original_sha256`을 현재 원본 해시와 대조해 그 사각을 닫는다.
    # 파생 뷰이므로 matched에서 빼지 않는다 — 기존 카운트 계약(matched/markdown 분리)을
    # 건드리지 않고 경고만 추가. NLM 호출 0, 로컬 해시 대조뿐이라 비용은 무시 가능.
    # 처방 형태가 헌법 조항 +1이 아니라 *이미 매 동기화에 호출되는 코드로의 편입*인
    # 이유: 뿌리4 결론("코드가 검사·주입하는 형태만 생존 실적이 있다") + 세션538
    # `--list-dangling` 전례.
    stale_processed: list[DriftEntry] = []
    for m in matched:
        disk_path = m.get("disk_path")
        if not disk_path:
            continue
        verdict = check_processed_stale(Path(disk_path), vault_root=vault_root)
        if verdict is not None:
            entry = dict(m)
            entry["status"] = verdict
            stale_processed.append(entry)  # type: ignore[arg-type]

    return {
        "notebook_id": notebook_id,
        "total": len(sources),
        "matched": matched,
        "matched_markdown": matched_markdown,
        "matched_non_markdown": matched_non_markdown,
        "matched_bundle": matched_bundle,
        "bundle_origin_dup": bundle_origin_dup,
        "dup_disk_path": dup_disk_path,
        "stale_processed": stale_processed,
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
    mb = len(report.get("matched_bundle", []))
    bod = len(report.get("bundle_origin_dup", []))
    ddp = len(report.get("dup_disk_path", []))
    sp = len(report.get("stale_processed", []))
    ms = len(report["missing"])
    a = len(report["ambiguous"])
    st = len(report["skip_type"])
    parts = [
        f"📊 drift 점검: {mm} markdown(.md) / {mn} non-md(plain text 정상)"
        f" / {mb} 번들(N:1)"
        f" / {bod} 번들원본 낱개중복"
        f" / {ddp} 동일파일 중복소스"
        f" / {sp} 가공물 내용 stale"
        f" / {ms} NLM 잔재 / {a} 모호 / {st} type-skip"
    ]
    if ms > 0 or a > 0 or bod > 0 or ddp > 0 or sp > 0:
        parts.append(" — 청소·매핑 보강 권고")
    summary = "".join(parts)
    if sp > 0:
        summary += (
            "\n  🟠 가공물 내용 stale (원본 갱신 후 재가공 누락 — NLM에 구버전 잔존."
            " `generate_code_md.py <원본> --force` 후 재업로드 권고):"
        )
        for entry in report["stale_processed"][:10]:
            summary += (
                f"\n    - [{entry['source_id'][:8]}] {entry['title'][:60]}"
                f" ({entry['status']})"
            )
        if sp > 10:
            summary += f"\n    ... +{sp - 10} more"
    if ddp > 0:
        summary += (
            "\n  🔴 동일 디스크 파일을 가리키는 중복 소스 (제목만 다름 — 구버전"
            " 잔재일 가능성. 내용 확인 후 규약 위반 쪽 source_delete 권고):"
        )
        for entry in report["dup_disk_path"][:10]:
            summary += (
                f"\n    - [{entry['source_id'][:8]}] {entry['title'][:60]}"
                f" → {entry['disk_path']}"
            )
        if ddp > 10:
            summary += f"\n    ... +{ddp - 10} more"
    if bod > 0:
        summary += (
            "\n  🔴 번들원본 낱개중복 (registry 등재 원본이 번들 아닌 낱개로 재업로드"
            " — 라우팅 규칙 미준수, 낱개 source_delete 후 sync_bundle 권고):"
        )
        for entry in report["bundle_origin_dup"][:10]:
            summary += f"\n    - [{entry['source_id'][:8]}] {entry['title'][:60]}"
        if bod > 10:
            summary += f"\n    ... +{bod - 10} more"
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
