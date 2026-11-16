"""Tests of student_copy_steps.py: the lines it writes, and what they run.

The lines are run under bash in a throwaway checkout with a stub `quarto`
that records its arguments, so each test checks what would be rendered.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "student_copy_steps.py"


def steps(tmp_path: Path, **env: str) -> list[str]:
    full = {"PATH": os.environ["PATH"], "SC_CHECK": "python3 tools/check.py", **env}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=full, cwd=tmp_path,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def refused(tmp_path: Path, **env: str) -> str:
    full = {"PATH": os.environ["PATH"], **env}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], env=full, cwd=tmp_path,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 64, result.stdout
    return result.stderr


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    for name in ["exercises/logic/_exr-a.qmd", "exercises/logic/_exr-b.qmd",
                 "exercises/sets/_exr-c.qmd", "Homework/hw1.qmd", "Homework/hw2.qmd"]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    quarto = bin_dir / "quarto"
    quarto.write_text('#!/bin/sh\necho "$*" >> "$QUARTO_LOG"\n')
    quarto.chmod(quarto.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def run_line(checkout: Path, line: str) -> tuple[int, list[str]]:
    log = checkout / "quarto.log"
    log.unlink(missing_ok=True)
    env = {"PATH": f"{checkout / 'bin'}:{os.environ['PATH']}", "QUARTO_LOG": str(log)}
    result = subprocess.run(["bash", "-c", line], cwd=checkout, env=env,
                            capture_output=True, text=True, check=False)
    calls = log.read_text().splitlines() if log.exists() else []
    return result.returncode, calls


def test_all_writes_bare_renders_then_fragments_then_check(checkout: Path) -> None:
    lines = steps(checkout)
    assert lines[:2] == ["quarto render", "quarto render --profile solution"]
    assert lines[3] == "python3 tools/check.py"
    assert len(lines) == 4  # condor-batch refuses fewer than two


def test_all_fragments_renders_every_match_first_alone(checkout: Path) -> None:
    rc, calls = run_line(checkout, steps(checkout)[2])
    assert rc == 0
    assert calls[0] == "render exercises/logic/_exr-a.qmd --to html"
    assert sorted(calls) == sorted(
        f"render exercises/{p} --to html"
        for p in ["logic/_exr-a.qmd", "logic/_exr-b.qmd", "sets/_exr-c.qmd"]
    )


def test_document_list_renders_each_in_both_profiles(checkout: Path) -> None:
    (checkout / "docs.txt").write_text("Homework/hw2.qmd\n")
    lines = steps(checkout, SC_DOCUMENTS="docs.txt")
    assert run_line(checkout, lines[0]) == (0, ["render Homework/hw2.qmd"])
    assert run_line(checkout, lines[1]) == (0, ["render Homework/hw2.qmd --profile solution"])


def test_empty_lists_render_nothing(checkout: Path) -> None:
    (checkout / "docs.txt").write_text("")
    (checkout / "frags.txt").write_text("")
    lines = steps(checkout, SC_DOCUMENTS="docs.txt", SC_FRAGMENTS="frags.txt")
    for line in lines[:3]:
        assert run_line(checkout, line) == (0, [])


def test_fragment_list_renders_only_the_listed(checkout: Path) -> None:
    (checkout / "frags.txt").write_text("exercises/sets/_exr-c.qmd\n")
    line = steps(checkout, SC_FRAGMENTS="frags.txt")[2]
    assert run_line(checkout, line) == (0, ["render exercises/sets/_exr-c.qmd --to html"])


def test_a_failing_render_fails_the_line(checkout: Path) -> None:
    (checkout / "bin" / "quarto").write_text("#!/bin/sh\nexit 3\n")
    rc, _ = run_line(checkout, steps(checkout)[2])
    assert rc != 0


def test_glob_matching_nothing_fails_rather_than_passing(checkout: Path) -> None:
    line = steps(checkout, SC_FRAGMENT_GLOB="nowhere/*.qmd")[2]
    rc, calls = run_line(checkout, line)
    assert rc != 0 and calls == []


def test_list_path_with_a_space_is_quoted(checkout: Path) -> None:
    (checkout / "my docs.txt").write_text("Homework/hw1.qmd\n")
    line = steps(checkout, SC_DOCUMENTS="my docs.txt")[0]
    assert run_line(checkout, line) == (0, ["render Homework/hw1.qmd"])


@pytest.mark.parametrize("env, word", [
    ({}, "check is required"),
    ({"SC_CHECK": "a\nb"}, "one line"),
    ({"SC_CHECK": "c", "SC_PARALLEL": "0"}, "parallel"),
    ({"SC_CHECK": "c", "SC_PARALLEL": "x"}, "parallel"),
    ({"SC_CHECK": "c", "SC_DOCUMENTS": "/etc/list"}, "relative path"),
    ({"SC_CHECK": "c", "SC_FRAGMENTS": "../list"}, "relative path"),
    ({"SC_CHECK": "c", "SC_FRAGMENT_GLOB": "a;rm -rf b"}, "fragment-glob"),
])
def test_bad_inputs_are_refused(tmp_path: Path, env: dict[str, str], word: str) -> None:
    assert word in refused(tmp_path, **env)


def test_action_defaults_match_the_script() -> None:
    action = (SCRIPT.parent.parent / ".github/actions/student-copy-render/action.yml").read_text()
    source = SCRIPT.read_text()
    assert "default: exercises/*/_exr-*.qmd" in action
    assert '"SC_FRAGMENT_GLOB", "exercises/*/_exr-*.qmd"' in source
    assert "default: '4'" in action and '"SC_PARALLEL", "4"' in source
