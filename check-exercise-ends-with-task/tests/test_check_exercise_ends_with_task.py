"""Unit tests for check-exercise-ends-with-task.

Covers what is flagged (a last block that is a figure, table, code block or
include; a last paragraph with no task; an empty exercise), what is not (a
task last, a solution, hint or comment after it, a task-only paragraph with
scenario before it, an opt-out comment), and diff scoping on a throwaway repo.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_exercise_ends_with_task", _DIR / "check-exercise-ends-with-task.py"
)
assert _spec is not None and _spec.loader is not None
eet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eet)


def exercise(body: str, attrs: str = "{#exr-a}") -> str:
    return f"::: {attrs}\n#### Title\n\n{body}\n:::"


def reasons(text: str):
    return [f.reason for f in eet.exercises(text.split("\n"))]


@pytest.mark.parametrize("body", [
    "A clinic records 40 visits.\n\nHow many were new patients?",
    "Show that the odds equal $3/7$.",
    "Let $p = 0.3$.\nShow that the odds equal $3/7$.",
    "Describe the data.\n\n![A plot](plot.png)\n\nWhat do you see?",
    "Find the mean.\n\n::: {.callout-tip}\nA hint.\n:::",
    "Find the mean.\n\n<!-- a note -->",
    "Find the mean.\n\n$$\nx = 1\n$$",
    "Find the mean of these:\n\n- 1\n- 2",
])
def test_task_last_passes(body):
    assert reasons(exercise(body)) == []


@pytest.mark.parametrize("body, word", [
    ("What do you see?\n\n![A plot](plot.png)", "figure"),
    ("What do you see?\n\n{{< include _plot.qmd >}}", "include"),
    ("What do you see?\n\n| a | b |\n|---|---|\n| 1 | 2 |", "table"),
    ("What do you see?\n\n```{r}\nplot(1)\n```", "code block"),
    ("What do you see?\n\n::: {#fig-a}\n![A](a.png)\n\nCaption.\n:::", "figure"),
    ("What do you see?\n\n::: {#tbl-a}\n| a |\n\nCaption.\n:::", "table"),
])
def test_trailing_non_task_block_is_flagged(body, word):
    assert reasons(exercise(body)) == [f"its last block is a {word}, not a task"]


def test_last_paragraph_without_task_is_flagged():
    text = exercise("Show that the odds equal $3/7$.\n\nThe data are in Table 1.")
    assert reasons(text) == ["its last paragraph holds no question or instruction"]


def test_empty_exercise_is_flagged():
    assert reasons(exercise("")) == ["it has no text"]


def test_solution_after_task_is_not_examined():
    text = exercise("Find the mean.\n\n::: {#sol-a}\nThe mean is 3.\n\n![A](a.png)\n:::")
    assert reasons(text) == []


def test_opt_out_comment_exempts():
    text = exercise("What?\n\n![A](a.png)\n\n<!-- ends-with-task-ok: shown first -->")
    assert reasons(text) == []


def test_non_exercise_div_ignored():
    text = "::: {#def-a}\nA term.\n\n![A](a.png)\n:::"
    assert reasons(text) == []


def test_failing_example_figure_include_last():
    text = exercise("Why not fit a line?\n\n{{< include _fig.qmd >}}", "{#exr-why-not-a-line}")
    assert reasons(text) == ["its last block is a include, not a task"]


def test_diff_scoping_and_whole_tree(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.invalid")  # phi-allow
    git("config", "user.name", "t")
    bad = exercise("What?\n\n![A](a.png)", "{#exr-old}")
    (tmp_path / "a.qmd").write_text(bad + "\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    (tmp_path / "b.qmd").write_text(exercise("What?\n\n![A](b.png)", "{#exr-new}") + "\n",
                                    encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "new")
    monkeypatch.chdir(tmp_path)
    diff = eet.eqp.wanted_lines("HEAD~1", ["*.qmd"], False)
    assert sorted(diff) == ["b.qmd"]
    whole = eet.eqp.wanted_lines("", ["*.qmd"], True)
    assert sorted(whole) == ["a.qmd", "b.qmd"]
    flagged = [p for p in whole if eet.exercises((tmp_path / p).read_text().split("\n"))]
    assert flagged == ["a.qmd", "b.qmd"]
    assert eet.touched(eet.Finding(1, 6, "x"), diff["b.qmd"])
    assert not eet.touched(eet.Finding(1, 6, "x"), set())


@pytest.mark.parametrize("body", [
    # psw's #exr-sum-deviations (gha#1843): one sentence split by a display.
    "Show that\n\n$$\n\\sum_{i=1}^n (x_i - \\bar{x}) = 0,\n$$\n\n"
    "where $\\bar{x}$ is the sample mean (@def-sample-mean).",
    "Show that\n$$\nx = 1,\n$$\nwhere $x$ is a number.",
    "Show that\n\n$$\na = b,\n$$\n\nand\n\n$$\nb = c,\n$$\n\nwhere $a$ is a number.",
    # A paragraph after a list has ended can still run on past a display.
    "Intro.\n\n- an item\n\nShow that\n\n$$\nx = 1,\n$$\n\nwhere $x$ is a number.",
    # Unchanged by gha#1843: an indented paragraph inside a list item is still judged.
    "Consider data.\n\n1. Item a.\n2. Item b.\n\n   Explain why.",
    "Consider data.\n\n- item\n\n    Find the mean.",
])
def test_a_sentence_continued_past_a_display_is_judged_whole(body):
    assert reasons(exercise(body)) == []


@pytest.mark.parametrize("body", [
    # A capitalized paragraph after the display starts a new sentence.
    "Show that\n\n$$\nx = 1.\n$$\n\nThe data are in Table 1.",
    # A display that opens the exercise has no sentence before it to continue.
    "$$\nx = 1,\n$$\n\nwhere $x$ is a number.",
    # Another block between the display and the lowercase paragraph breaks the link.
    "Show that\n\n$$\nx = 1,\n$$\n\n- a list item\n\nwhere $x$ is a number.",
    # So does a block between the paragraph and the display.
    "Show that $x = 1$.\n\n- a list item\n\n$$\nx = 1,\n$$\n\nwhere $x$ is a number.",
    # A solution or callout div is not judged, but it still splits the sentence.
    "Show that\n\n$$\nx = 1,\n$$\n\n::: {.sol}\nAns.\n:::\n\nwhere $x$ is a number.",
    "Show that\n\n::: {.callout-tip}\nA hint.\n:::\n\n$$\nx = 1,\n$$\n\nwhere $x$ is a number.",
    # A sentence inside a list item does not run on past a display to a later paragraph,
    # whether its line is indented or lazy.
    "Some text.\n\n- an item\n  Show that\n\n$$\nx = 1,\n$$\n\nwhere $x$ is a number.",
    "Some text.\n\n- an item\nShow that\n\n$$\nx = 1,\n$$\n\nwhere $x$ is a number.",
    "Some text.\n\n- an item\n  Show that\n  $$\n  x = 1,\n  $$\n\nwhere $x$ is a number.",
])
def test_a_new_sentence_after_a_display_is_judged_alone(body):
    assert reasons(exercise(body)) == ["its last paragraph holds no question or instruction"]
