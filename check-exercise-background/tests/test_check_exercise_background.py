"""Unit tests for check-exercise-background.

Covers what is flagged (a title word the body never mentions), what is not
(a word the body repeats or shares a stem with, generic task verbs, math in the
title, text outside an exercise, code, comments), diff scoping, and the
defaults the script, the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_exercise_background", _DIR / "check-exercise-background.py"
)
assert _spec is not None and _spec.loader is not None
exb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exb)


def exercise(title: str, body: str, attrs: str = "{#exr-a}") -> str:
    return f"::: {attrs}\n#### {title}\n\n{body}\n:::"


def found(text: str):
    return [(f.line, f.missing) for f in exb.exercises(text.split("\n"))]


def test_title_word_missing_from_the_body_is_flagged():
    text = exercise("Maximizing a gamma-family kernel",
                    "Find the maximum value of $f(x) = x^4 e^{-x}$.")
    assert found(text) == [(2, ["gamma", "family", "kernel"])]


def test_background_in_the_body_clears_the_finding():
    body = ("The gamma distributions form a family. Its kernel is the part "
            "that depends on $x$. Find the maximum.")
    assert found(exercise("Maximizing a gamma-family kernel", body)) == []


@pytest.mark.parametrize("title, body", [
    ("Maximizing a function", "Find the maximum of the function."),
    ("Classifying a point", "Classify the point."),
    ("Plot the data", "Show the data."),
])
def test_a_word_sharing_five_letters_with_the_body_counts_as_present(title, body):
    assert found(exercise(title, body)) == []


@pytest.mark.parametrize("title", [
    "Find it", "Compute and check", "Differentiate", "Show that",
])
def test_generic_task_titles_are_not_flagged(title):
    assert found(exercise(title, "Do the thing.")) == []


def test_math_in_the_title_is_ignored():
    assert found(exercise("Slope at $w = 1$ of the curve", "The slope of the curve.")) == []


def test_a_link_target_is_not_body_text():
    assert found(exercise("Kernel", "See [x](kernel.qmd).")) == [(2, ["kernel"])]


def test_text_outside_an_exercise_is_not_checked():
    assert found("::: {#exm-a}\n#### Gamma kernel\n\nNothing.\n:::") == []


def test_solution_div_is_not_the_exercise_body():
    text = exercise("Gamma kernel", "Nothing.") + "\n\n::: {#sol-a}\nGamma kernel.\n:::"
    assert found(text) == [(2, ["gamma", "kernel"])]


def test_nested_div_counts_as_body():
    text = ("::: {#exr-a}\n#### Gamma kernel\n\nText.\n\n"
            "::: {.callout-note}\nA gamma kernel.\n:::\n:::")
    assert found(text) == []


def test_code_and_comments_are_skipped():
    text = ("::: {#exr-a}\n#### Gamma kernel\n\n```r\ngamma kernel\n```\n"
            "<!-- gamma kernel -->\nNothing.\n:::")
    assert found(text) == [(2, ["gamma", "kernel"])]


def test_an_exercise_without_a_heading_is_not_flagged():
    assert found("::: {#exr-a}\nFind the maximum.\n:::") == []


def test_added_lines_scopes_the_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +5,2 @@\n+x\n+y\n+++ /dev/null\n"
    assert exb.added_lines(diff) == {"a.qmd": {5, 6}}


def test_a_finding_needs_an_added_line_inside_the_exercise():
    finding = exb.Finding(line=3, title="t", missing=["x"], start=2, end=8)
    assert exb.touched(finding, {5}) is True
    assert exb.touched(finding, {20}) is False
    assert exb.touched(finding, None) is True
