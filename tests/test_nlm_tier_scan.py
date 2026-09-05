"""`nlm-tier` disk→source 역방향 스윕 회귀 가드 (세션559 신설).

`detect_drift`의 기존 버킷은 전부 **source→disk** 단방향이라, 디스크에만 있고
NLM에 올라간 적 없는 코어 파일은 어떤 버킷도 울리지 않았다. 세션559 실측에서
그런 파일이 13건 나왔고 `handoff_push.py`는 변경 목록에 최소 두 번 떴는데도
매번 지나쳐졌다 — 판정이 어디에도 기록되지 않아 다음 세션이 같은 판단을
처음부터 다시 했기 때문이다.

본 테스트가 깨지면 그 사각이 되돌아온다.

⚠ **한글 경로 픽스처는 장식이 아니다.** 볼트 경로는 대부분 한글이고,
`_git_lines`가 bytes 모드를 잃으면(=`text=True`로 되돌아가면) Windows에서
stdin의 `\\n`이 `\\r\\n`으로 변환되어 git이 경로 끝 `\\r`까지 파일명으로 읽는다.
그러면 **조용히 적게** 검출된다 — 세션559 로컬 검증 실측으로 R5 54건이 5건으로
줄었다. ASCII-only 픽스처는 그 회귀를 못 잡는다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from notebooklm_tools.services import sync_helpers
from notebooklm_tools.services.sync_helpers import scan_unprocessed_r5


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def tier_vault(tmp_path: Path) -> Path:
    """`nlm-tier` 선언이 있는 최소 git repo.

    구성:
      000-시스템/코어/alpha.py      R5, 가공물 있음  → 미검출이어야
      000-시스템/코어/alpha.py.md   (가공물)
      000-시스템/코어/beta.py       R5, 가공물 없음  → 검출되어야
      000-시스템/코어/bundled.py    R5, 번들 원본     → 미검출이어야
      000-시스템/코어/tests/test_x.py  선언 없음, 테스트 → untiered 제외
      bin/helper.py                R6              → 어느 쪽도 아님
      untiered_top.py              선언 없음        → untiered 1
    """
    _git(tmp_path, "init", "-q")
    core = tmp_path / "000-시스템" / "코어"
    core.mkdir(parents=True)
    (core / "alpha.py").write_text("a", encoding="utf-8")
    (core / "alpha.py.md").write_text("processed", encoding="utf-8")
    (core / "beta.py").write_text("b", encoding="utf-8")
    (core / "bundled.py").write_text("c", encoding="utf-8")
    tests_dir = core / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text("t", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "helper.py").write_text("h", encoding="utf-8")
    (tmp_path / "untiered_top.py").write_text("u", encoding="utf-8")
    (tmp_path / ".gitattributes").write_text(
        "000-시스템/코어/*.py nlm-tier=R5\nbin/*.py nlm-tier=R6\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "-A")
    return tmp_path


def _key(p: Path) -> str:
    return str(p.resolve()).lower()


def test_detects_only_unreached_r5(tier_vault: Path) -> None:
    """가공물·번들로 도달한 R5는 빠지고, 도달 못 한 것만 잡힌다."""
    reached = {
        _key(tier_vault / "000-시스템" / "코어" / "alpha.py.md"),  # 가공물 경로
        _key(tier_vault / "000-시스템" / "코어" / "bundled.py"),  # 번들 원본
    }
    out, untiered = scan_unprocessed_r5(tier_vault, reached)
    titles = sorted(e["title"] for e in out)
    assert titles == ["000-시스템/코어/beta.py"], titles
    assert untiered == 1, untiered  # untiered_top.py 만 (tests/·R6 제외)


def test_entry_shape(tier_vault: Path) -> None:
    """DriftEntry 계약 — 소비자(format_drift_summary)가 기대하는 형태."""
    out, _ = scan_unprocessed_r5(tier_vault, set())
    assert out, "R5 선언이 3개인데 아무것도 안 잡혔다"
    for e in out:
        assert e["status"] == "unprocessed_r5"
        assert e["source_id"] == ""
        assert e["markdown_relevant"] is False
        assert e["candidates"] == []
        assert Path(e["disk_path"]).is_file(), e["disk_path"]
        # title 은 볼트 상대경로 — 사람이 그대로 파일을 찾을 수 있어야 한다
        assert not e["title"].startswith(("/", "C:", '"'))


def test_empty_reached_returns_all_r5(tier_vault: Path) -> None:
    """통제군 — 도달 집합이 비면 R5 전량(3건)이 잡혀야 스윕이 실제로 도는 것."""
    out, _ = scan_unprocessed_r5(tier_vault, set())
    assert sorted(e["title"] for e in out) == [
        "000-시스템/코어/alpha.py",
        "000-시스템/코어/beta.py",
        "000-시스템/코어/bundled.py",
    ]


def test_r6_never_reported(tier_vault: Path) -> None:
    """R6 선언은 도달 여부와 무관하게 절대 안 잡힌다 (명시적 '안 올림' 판정)."""
    out, _ = scan_unprocessed_r5(tier_vault, set())
    assert not any("bin/helper.py" in e["title"] for e in out)


def test_untiered_excludes_tests_and_declared(tier_vault: Path) -> None:
    """untiered 는 *판정이 필요한* 코드만 센다 — 테스트·선언완료는 제외."""
    _, untiered = scan_unprocessed_r5(tier_vault, set())
    assert untiered == 1


def test_untiered_ignores_non_code(tier_vault: Path) -> None:
    """`.md`·`.json` 은 untiered 대상이 아니다 (코드 파일만)."""
    (tier_vault / "note.md").write_text("n", encoding="utf-8")
    (tier_vault / "conf.json").write_text("{}", encoding="utf-8")
    _git(tier_vault, "add", "-A")
    _, untiered = scan_unprocessed_r5(tier_vault, set())
    assert untiered == 1


def test_fail_open_without_git(tmp_path: Path) -> None:
    """git repo 가 아니면 예외 대신 조용히 빈 결과 — 동기화 전체를 세우지 않는다."""
    out, untiered = scan_unprocessed_r5(tmp_path / "__nope__", set())
    assert out == [] and untiered == 0


def test_git_lines_stdin_has_no_cr_or_quotes(tier_vault: Path) -> None:
    """★ `\\r` 회귀 가드 — `_git_lines` 가 bytes 모드를 잃으면 여기서 죽는다.

    `text=True` 로 되돌리면 Windows 에서 stdin 의 `\\n` 이 `\\r\\n` 이 되고, git 은
    경로 끝 `\\r` 을 파일명의 일부로 본다. 그러면 ⓐ 줄 끝에 `\\r` 이 남고
    ⓑ git 이 제어문자 포함 경로로 판단해 `core.quotePath=false` 를 무시하고
    따옴표로 감싼다. 둘 다 여기서 잡는다.
    """
    tracked = sync_helpers._git_lines(tier_vault, ["ls-files"])
    assert tracked, "ls-files 가 비었다 — 픽스처 전제 붕괴"
    attrs = sync_helpers._git_lines(
        tier_vault, ["check-attr", "nlm-tier", "--stdin"], stdin="\n".join(tracked)
    )
    assert attrs, "check-attr 가 비었다"
    for line in attrs:
        assert "\r" not in line, f"CR 혼입: {line!r}"
        path = line.rsplit(": nlm-tier: ", 1)[0]
        assert not path.startswith('"'), f"quotePath 이스케이프: {line!r}"
    # 한글 경로가 온전히 살아 돌아왔는지 (bytes 디코딩 검증)
    assert any("000-시스템/코어/beta.py" in line for line in attrs)


def test_summary_reports_unprocessed(tier_vault: Path) -> None:
    """format_drift_summary 가 R5 미편입을 보고하고 권고 문구를 붙인다."""
    out, untiered = scan_unprocessed_r5(tier_vault, set())
    report = {
        "notebook_id": "nb",
        "total": 0,
        "matched": [],
        "matched_markdown": [],
        "matched_non_markdown": [],
        "matched_bundle": [],
        "bundle_origin_dup": [],
        "dup_disk_path": [],
        "stale_processed": [],
        "unprocessed_r5": out,
        "untiered_count": untiered,
        "missing": [],
        "ambiguous": [],
        "skip_type": [],
    }
    summary = sync_helpers.format_drift_summary(report)  # type: ignore[arg-type]
    assert "3 R5 미편입" in summary
    assert "청소·매핑 보강 권고" in summary
    assert "000-시스템/코어/beta.py" in summary
    assert "nlm-tier 미선언 코드 1" in summary


def test_summary_clean_when_all_reached(tier_vault: Path) -> None:
    """미편입 0이면 권고 문구도 상세 목록도 없다 (늑대소년 방어)."""
    report = {
        "notebook_id": "nb",
        "total": 0,
        "matched": [],
        "matched_markdown": [],
        "matched_non_markdown": [],
        "matched_bundle": [],
        "bundle_origin_dup": [],
        "dup_disk_path": [],
        "stale_processed": [],
        "unprocessed_r5": [],
        "untiered_count": 0,
        "missing": [],
        "ambiguous": [],
        "skip_type": [],
    }
    summary = sync_helpers.format_drift_summary(report)  # type: ignore[arg-type]
    assert "0 R5 미편입" in summary
    assert "청소·매핑 보강 권고" not in summary
    assert "🟡" not in summary


def test_report_keys_backward_compatible() -> None:
    """옛 호출자가 신규 키 없이 만든 report 도 summary 가 받아야 한다."""
    legacy = {
        "notebook_id": "nb",
        "total": 0,
        "matched": [],
        "matched_markdown": [],
        "matched_non_markdown": [],
        "missing": [],
        "ambiguous": [],
        "skip_type": [],
    }
    summary = sync_helpers.format_drift_summary(legacy)  # type: ignore[arg-type]
    assert "0 R5 미편입" in summary
    assert "nlm-tier 미선언 코드 0" in summary


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
