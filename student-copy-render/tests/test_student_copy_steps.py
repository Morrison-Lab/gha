"""Tests of student_copy_steps.py: the lines it writes, run under bash with a stub quarto."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "student_copy_steps.py"
FRAGMENTS = ["exercises/logic/_exr-a.qmd", "exercises/logic/_exr-b.qmd", "exercises/sets/_exr-c.qmd"]


def write_steps(cwd: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT)], env={"PATH": os.environ["PATH"], **env},
                          cwd=cwd, capture_output=True, text=True, check=False)


def steps(cwd: Path, **env: str) -> list[str]:
    result = write_steps(cwd, SC_CHECK="python3 tools/check.py", **env)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    for name in [*FRAGMENTS, "Homework/hw1.qmd"]:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x\n")
    quarto = tmp_path / "bin" / "quarto"
    quarto.parent.mkdir()
    quarto.write_text('#!/bin/sh\necho "$*" >> "$QUARTO_LOG"\n')
    quarto.chmod(quarto.stat().st_mode | stat.S_IEXEC)
    return tmp_path


def run_line(checkout: Path, line: str) -> tuple[int, list[str]]:
    log = checkout / "quarto.log"
    log.unlink(missing_ok=True)
    env = {"PATH": f"{checkout / 'bin'}:{os.environ['PATH']}", "QUARTO_LOG": str(log)}
    rc = subprocess.run(["bash", "-c", line], cwd=checkout, env=env, check=False).returncode
    return rc, log.read_text().splitlines() if log.exists() else []


def test_all_writes_both_profiles_fragments_and_check(checkout: Path) -> None:
    lines = steps(checkout)
    assert lines[:2] == ["quarto render", "quarto render --profile solution"]
    assert lines[3] == "python3 tools/check.py" and len(lines) == 4
    rc, calls = run_line(checkout, lines[2])
    assert rc == 0 and calls[0] == f"render {FRAGMENTS[0]} --to html"  # the first alone
    assert sorted(calls) == [f"render {f} --to html" for f in FRAGMENTS]


def test_lists_render_only_what_they_name(checkout: Path) -> None:
    # Spaces, a quote, CRLF endings and a blank line: each nonblank line is one name.
    (checkout / "my docs.txt").write_text("Homework/my hw.qmd\r\n")
    (checkout / "frags.txt").write_text(f"{FRAGMENTS[2]}\r\n\r\nexercises/it's.qmd\r\n")
    lines = steps(checkout, SC_DOCUMENTS="my docs.txt", SC_FRAGMENTS="frags.txt")
    assert run_line(checkout, lines[0]) == (0, ["render Homework/my hw.qmd"])
    assert run_line(checkout, lines[1]) == (0, ["render Homework/my hw.qmd --profile solution"])
    assert run_line(checkout, lines[2]) == (0, [f"render {FRAGMENTS[2]} --to html", "render exercises/it's.qmd --to html"])


def test_empty_lists_render_nothing(checkout: Path) -> None:
    (checkout / "none.txt").write_text("")
    for line in steps(checkout, SC_DOCUMENTS="none.txt", SC_FRAGMENTS="none.txt")[:3]:
        assert run_line(checkout, line) == (0, [])


def test_failures_fail_the_line(checkout: Path) -> None:
    # A glob that matches nothing is a mistake, not a pass.
    assert run_line(checkout, steps(checkout, SC_FRAGMENT_GLOB="nowhere/*.qmd")[2]) == (2, [])
    (checkout / "bin" / "quarto").write_text("#!/bin/sh\nexit 3\n")
    assert run_line(checkout, steps(checkout)[2])[0] != 0
    # A listed name starting with - (even after a CR), or a missing list.
    (checkout / "dash.txt").write_text("a.qmd\n\r--output=/tmp/x\n")
    for name in ("dash.txt", "gone.txt"):
        for line in steps(checkout, SC_DOCUMENTS=name, SC_FRAGMENTS=name)[:3]:
            assert run_line(checkout, line)[0] != 0 and run_line(checkout, line)[1] == [], (name, line)


@pytest.mark.parametrize("env, word", [
    ({"SC_CHECK": ""}, "check is required"), ({"SC_CHECK": "a\nb"}, "one line"),
    ({"SC_PARALLEL": "0"}, "parallel"), ({"SC_PARALLEL": "x"}, "parallel"),
    ({"SC_DOCUMENTS": "/etc/list"}, "relative path"), ({"SC_FRAGMENTS": "../list"}, "relative path"),
    ({"SC_FRAGMENT_GLOB": "a;rm -rf b"}, "fragment-glob"), ({"SC_FRAGMENT_GLOB": "../../*"}, "fragment-glob"),
    ({"SC_FRAGMENT_GLOB": "-la"}, "fragment-glob"), ({"SC_FRAGMENTS": "-n"}, "relative path"), ({"SC_DOCUMENTS": ""}, "relative path"),
])
def test_bad_inputs_are_refused(tmp_path: Path, env: dict[str, str], word: str) -> None:
    result = write_steps(tmp_path, **{"SC_CHECK": "c", **env})
    assert result.returncode == 64 and word in result.stderr


def test_action_defaults_match_the_script() -> None:
    action = (SCRIPT.parents[1] / ".github/actions/student-copy-render/action.yml").read_text()
    source = SCRIPT.read_text()
    assert "default: exercises/*/_exr-*.qmd" in action
    assert '"SC_FRAGMENT_GLOB", "exercises/*/_exr-*.qmd"' in source
    assert "default: '4'" in action and '"SC_PARALLEL", "4"' in source
