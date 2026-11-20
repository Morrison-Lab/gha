"""Tests for check-ball-neighborhoods."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "check-ball-neighborhoods.py"

_spec = importlib.util.spec_from_file_location("cbn", SCRIPT)
cbn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cbn)


def texts(math):
    return [text for text, _ in cbn.ball_conditions(math)]


@pytest.mark.parametrize("math", [
    r"\norm{\vx - \vx^*} < \delta",
    r"\abs{x - c} < \tolin",
    r"\| x - y \| < r",
    r"\left\| x - y \right\| < r",
    r"|x - a| < \delta",
    r"\left| x - a \right| < \delta",
    r"\lVert x - y \rVert < r",
    r"\left\lVert x - y \right\rVert < r",
    r"\lvert x - y \rvert \le r",
    r"\norm{\vx - \vy}_2 < \epsilon",
    r"\norm{\vx - \vy}_{2} \leq \epsilon",
    r"\norm{f(\vy) - f(\vx)} < \tolout / 2",
    r"\norm{\vy - \vx} \lt \tolin",
    r"\abs{\frac{1}{m} - \frac{1}{n}} < \frac{1}{N}",
])
def test_flags_a_neighborhood(math):
    assert len(texts(math)) == 1


@pytest.mark.parametrize("math", [
    # No difference: a norm bound such as a constraint on the coefficients.
    r"\norm{\vw} \le t",
    r"\abs{x} < 1",
    # A leading minus is a sign, not a difference.
    r"\abs{-x} < 1",
    # Two distances compared: the triangle inequality and a Lipschitz bound.
    r"\norm{\vx - \vz} \le \norm{\vx - \vy} + \norm{\vy - \vz}",
    r"\abs{f(x) - f(y)} \le L \abs{x - y}",
    r"\norm{\vx - \vy} \le C\,\norm{\vx - \vz}^2",
    # A complement of a ball, and an equality.
    r"\norm{\vx - \vy} > \delta",
    r"\norm{\vx - \vy} \ge \delta",
    r"\norm{\vx - \vy} = \delta",
    # A step-size factor: the first operand is a number.
    r"\abs{1 - \steplen\,\eigval_i} < 1",
    r"|1 - \learnrate| < 1",
    # A difference inside a group is not a top-level difference.
    r"\norm{f(x - y)} < 1",
    # Conditioning bars are not an absolute value.
    r"p(y | x) < 1",
])
def test_passes(math):
    assert texts(math) == []


def test_closed_ball_is_reported_as_closed():
    [(_, closed)] = cbn.ball_conditions(r"\norm{\vx - \vy} \le r")
    assert closed
    [(_, closed)] = cbn.ball_conditions(r"\norm{\vx - \vy} < r")
    assert not closed


def test_rhs_ends_at_a_separator():
    found = texts(r"\abs{x - c} < \tolin, \text{ then } \abs{y} \le 1")
    assert found == [r"\abs{x - c} < \tolin"]


def test_conditioning_bar_before_an_absolute_value():
    assert texts(r"p(y | x) \text{ for } |x - a| < \delta") == [r"|x - a| < \delta"]


def test_two_conditions_in_one_span():
    math = r"\norm{\vy - \vx} < \tolin \implies \norm{f(\vy) - f(\vx)} < \tolout"
    assert len(texts(math)) == 2


def scan(text):
    return cbn.scan_file(text.splitlines())[0]


def test_scan_reads_inline_and_display_math():
    found = scan("For all $\\abs{x - c} < \\tolin$.\n\n$$\n\\norm{x - y} < r\n$$\n")
    assert [f.line for f in found] == [1, 4]


def test_scan_skips_code_comments_and_front_matter():
    text = (
        "---\ntitle: $\\abs{x - c} < 1$\n---\n"
        "`$\\abs{x - c} < r$`\n"
        "<!-- $\\abs{x - c} < r$ -->\n"
        "```\n$\\abs{x - c} < r$\n```\n"
    )
    assert scan(text) == []


def test_allow_comment_needs_a_reason():
    with_reason = ("<!-- check-ball-neighborhoods: allow: defines the ball -->\n"
                   "$\\norm{\\vy - \\vx} < r$\n")
    assert scan(with_reason) == []
    without = "<!-- check-ball-neighborhoods: allow -->\n$\\norm{\\vy - \\vx} < r$\n"
    assert len(scan(without)) == 1


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ,
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",  # phi-allow
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})  # phi-allow


def run_main(cwd, **env):
    full = {k: v for k, v in os.environ.items() if not k.startswith("CBN_")}
    full.update(env)
    return subprocess.run(["python3", str(SCRIPT)], cwd=cwd, env=full,
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "page.qmd").write_text("Old $\\abs{x - c} < r$ here.\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "work")
    return tmp_path


def test_diff_scope_reports_only_added_lines(repo):
    page = repo / "page.qmd"
    page.write_text(page.read_text() + "New $\\norm{\\vx - \\vy} < \\delta$.\n")
    git(repo, "commit", "-qam", "add")
    result = run_main(repo, CBN_BASE_REF="main")
    assert result.returncode == 1
    assert "line=2" in result.stdout and "line=1" not in result.stdout


def test_moved_line_is_not_new(repo):
    page = repo / "page.qmd"
    page.write_text("Intro.\n" + page.read_text())
    git(repo, "commit", "-qam", "move")
    assert run_main(repo, CBN_BASE_REF="main").returncode == 0


def test_warn_only(repo):
    page = repo / "page.qmd"
    page.write_text(page.read_text() + "New $\\norm{\\vx - \\vy} < \\delta$.\n")
    git(repo, "commit", "-qam", "add")
    result = run_main(repo, CBN_BASE_REF="main", CBN_FAIL="false")
    assert result.returncode == 0
    assert "::warning file=page.qmd,line=2" in result.stdout


def test_no_base_skips(repo):
    result = run_main(repo)
    assert result.returncode == 0
    assert "Skipping" in result.stdout


def test_whole_tree(repo):
    result = run_main(repo, CBN_WHOLE_TREE="true")
    assert result.returncode == 1
    assert "line=1" in result.stdout
