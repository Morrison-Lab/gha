"""Unit tests for check-multipart-exercises.

Covers which exercises are flagged (list parts in each marker style, inline
parts), what is ignored (math, code, comments, bullets, the allow comment,
non-exercise divs), diff scoping, the skip-not-fall-back guard, and the
defaults the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_multipart_exercises", _DIR / "check-multipart-exercises.py"
)
assert _spec is not None and _spec.loader is not None
mpe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mpe)


def flagged(text: str):
    """(line, style) of each multi-part exercise in a document string."""
    found, _ = mpe.scan_file(text.split("\n"))
    return [(part.line, part.style) for _, part in found]


def exercise(body: str, attrs: str = "{#exr-a}") -> str:
    return f"::: {attrs}\n{body}\n:::"


# -- list parts --------------------------------------------------------------

@pytest.mark.parametrize("body, style", [
    ("Ask.\n\n(a) First.\n(b) Second.", "paren-alpha"),
    ("Ask.\n\n(i) First.\n(ii) Second.", "paren-alpha"),
    ("Ask.\n\na. First.\nb. Second.", "dot.-alpha"),
    ("Ask.\n\na) First.\nb) Second.", "dot)-alpha"),
    ("Ask.\n\n1. First.\n2. Second.", "dot.-num"),
    ("Ask.\n\n1) First.\n2) Second.", "dot)-num"),
    ("Ask.\n\n(1) First.\n(2) Second.", "paren-num"),
    ("Ask.\n\n**(a)** First.\n**(b)** Second.", "paren-alpha"),
    ("Ask.\n\n**a.** First.\n**b.** Second.", "dot.-alpha"),
    ("Ask.\n\n(A) First.\n(B) Second.", "paren-alpha"),
])
def test_list_parts_are_flagged(body, style):
    assert flagged(exercise(body)) == [(5, style)]


def test_finding_sits_on_the_second_part():
    text = "Intro.\n\n::: {#exr-a}\nAsk.\n\n(a) First.\n\n(b) Second.\n\n(c) Third.\n:::"
    assert flagged(text) == [(8, "paren-alpha")]


def test_one_part_is_not_flagged():
    assert flagged(exercise("Ask.\n\n(a) The only item.")) == []


def test_plain_exercise_is_not_flagged():
    assert flagged(exercise("Compute the odds ratio for a 2 by 2 table.")) == []


def test_bullets_are_not_parts():
    assert flagged(exercise("Let:\n\n- $x$ be one.\n- $y$ be two.\n\nFind $x+y$.")) == []


def test_sentence_starting_with_a_word_and_period_is_not_a_part():
    assert flagged(exercise("Ask.\n\nA fitted model is used.\nA second sentence.")) == []


# -- inline parts ------------------------------------------------------------

def test_inline_parts_are_flagged():
    assert flagged(exercise("Find (a) the mean and (b) the variance.")) == [(2, "inline")]


def test_inline_roman_parts_are_flagged():
    assert flagged(exercise("Show (i) it is odd and (ii) it is even.")) == [(2, "inline")]


def test_inline_parts_across_lines_are_flagged():
    assert flagged(exercise("Find (a) the mean\nand (b) the variance.")) == [(3, "inline")]


def test_lone_inline_marker_is_not_flagged():
    assert flagged(exercise("Use the formula in (a) of the definition.")) == []


# -- what is ignored ---------------------------------------------------------

def test_inline_math_is_ignored():
    assert flagged(exercise("Evaluate $f(a)$ and $f(b)$ at both points.")) == []


def test_display_math_is_ignored():
    body = "Ask.\n\n$$\n(a) x\n(b) y\n$$"
    assert flagged(exercise(body)) == []


def test_code_fence_is_ignored():
    body = "Ask.\n\n```python\n(a) x\n(b) y\n```"
    assert flagged(exercise(body)) == []


def test_html_comment_is_ignored():
    body = "Ask.\n\n<!--\n(a) x\n(b) y\n-->"
    assert flagged(exercise(body)) == []


def test_allow_comment_exempts_the_exercise():
    body = "<!-- multipart-ok: single-choice options -->\nPick one.\n\n(a) Yes.\n(b) No."
    assert flagged(exercise(body)) == []


def test_non_exercise_div_is_ignored():
    assert flagged(exercise("Ask.\n\n(a) First.\n(b) Second.", "{#sol-a}")) == []
    assert flagged(exercise("Ask.\n\n(a) First.\n(b) Second.", "{#def-a}")) == []


def test_exercise_nested_in_a_div_is_read():
    text = "::: {.callout-note}\n::: {#exr-a}\n(a) x\n(b) y\n:::\n:::"
    assert flagged(text) == [(4, "paren-alpha")]


def test_div_nested_in_exercise_belongs_to_it():
    text = "::: {#exr-a}\n::: {.hint}\nHint.\n:::\n\n(a) x\n(b) y\n:::"
    assert flagged(text) == [(7, "paren-alpha")]


def test_two_exercises_are_judged_separately():
    text = exercise("(a) x\n(b) y", "{#exr-a}") + "\n\n" + exercise("Single.", "{#exr-b}")
    assert flagged(text) == [(3, "paren-alpha")]


def test_unclosed_exercise_runs_to_end_of_file():
    assert flagged("::: {#exr-a}\n(a) x\n(b) y") == [(3, "paren-alpha")]


# -- diff scoping ------------------------------------------------------------

def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


OLD = exercise("(a) x\n(b) y", "{#exr-old}")


def test_untouched_multipart_exercise_is_not_reflagged(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "pr")
    (repo / "new.qmd").write_text(exercise("Single.", "{#exr-new}") + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pr")
    report = mpe.run_check("main", ["*.qmd"], [], False)
    assert report.findings == []
    assert report.files == 1


def test_touched_multipart_exercise_is_flagged(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "pr")
    (repo / "old.qmd").write_text(OLD.replace("(a) x", "(a) x2") + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pr")
    report = mpe.run_check("main", ["*.qmd"], [], False)
    assert [(f[0], f[1]) for f in report.findings] == [("old.qmd", 3)]


def test_added_multipart_exercise_is_flagged(repo):
    (repo / "a.qmd").write_text("Prose.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "pr")
    (repo / "b.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pr")
    assert len(mpe.run_check("main", ["*.qmd"], [], False).findings) == 1


def test_line_added_outside_the_exercise_does_not_flag_it(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "pr")
    (repo / "old.qmd").write_text(OLD + "\n\nNew prose after.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "pr")
    assert mpe.run_check("main", ["*.qmd"], [], False).findings == []


def test_whole_tree_flags_untouched_exercises(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    assert len(mpe.run_check("", ["*.qmd"], [], True).findings) == 1


def test_no_base_ref_skips(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    assert mpe.run_check("", ["*.qmd"], [], False).skipped


def test_unresolvable_base_ref_skips(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    assert mpe.run_check("no-such-ref", ["*.qmd"], [], False).skipped


def test_paths_ignore(repo):
    (repo / "old.qmd").write_text(OLD + "\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "base")
    ignores = mpe.compile_ignores(["old.qmd"])
    assert mpe.run_check("", ["*.qmd"], ignores, True).findings == []


# -- defaults agree ----------------------------------------------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-multipart-exercises.yml").read_text()
    assert mpe.DEFAULT_GLOBS == "*.qmd"
    assert mpe._DEFAULT_FAIL is True
    assert "default: '*.qmd'" in action
    assert "default: '*.qmd'" in workflow
    assert "default: 'true'" in action
    assert "default: true" in workflow
    assert "MPE_BASE_REF" in action
