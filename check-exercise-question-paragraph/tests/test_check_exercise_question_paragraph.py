"""Unit tests for check-exercise-question-paragraph.

Covers what is flagged (a paragraph of an exercise that mixes scenario
sentences with a question or an imperative task), what is not (separate
paragraphs, a task-only or scenario-only paragraph, solutions, hints, code,
display math, lists, comments, abbreviations, math and inline code), the
opt-out comment, and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_exercise_question_paragraph", _DIR / "check-exercise-question-paragraph.py"
)
assert _spec is not None and _spec.loader is not None
eqp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eqp)


def exercise(body: str, attrs: str = "{#exr-a}") -> str:
    return f"::: {attrs}\n#### Title\n\n{body}\n:::"


def lines_flagged(text: str):
    return [f.line for f in eqp.exercises(text.split("\n"))]


def test_scenario_and_question_in_one_paragraph_is_flagged():
    text = exercise("A clinic records 40 visits.\nHow many were new patients?")
    assert lines_flagged(text) == [4]


def test_scenario_and_instruction_in_one_paragraph_is_flagged():
    text = exercise("Let $p = 0.3$.\nShow that the odds equal $3/7$.")
    assert lines_flagged(text) == [4]


def test_separate_paragraphs_pass():
    text = exercise("A clinic records 40 visits.\n\nHow many were new patients?")
    assert lines_flagged(text) == []


@pytest.mark.parametrize("body", [
    "Show that the odds equal $3/7$.\nThen find the log odds.",
    "A clinic records 40 visits.\nThe visits are independent.",
    "How many were new?",
])
def test_a_paragraph_of_only_tasks_or_only_scenario_passes(body):
    assert lines_flagged(exercise(body)) == []


def test_a_sentence_broken_across_lines_counts_once():
    text = exercise("Show that the odds,\nwritten as a ratio,\nequal $3/7$.")
    assert lines_flagged(text) == []


def test_abbreviations_and_math_do_not_end_a_sentence():
    text = exercise("Estimate the odds, e.g. for $x = 1.5$. Use `glm` too?")
    assert lines_flagged(text) == []


def test_inline_code_with_a_dollar_sign_is_not_math():
    text = exercise("Of the `r a$b` messages, `r c$d` are spam.\n\nHow many are email?")
    assert lines_flagged(text) == []


def test_display_math_ends_a_paragraph_and_the_next_one_is_checked():
    text = exercise("We fit the model:\n\n$$\ny = x\n$$\n\nThe fit is good. Why?")
    assert lines_flagged(text) == [10]


@pytest.mark.parametrize("body", [
    "::: {.callout-tip}\n#### Hint\nThe data are small. Try a table.\n:::",
    "::: {#sol-a}\nThe data are small. Show a table.\n:::",
    "```r\n# The data are small. Show a table.\n```",
    "<!-- The data are small. Show a table. -->",
    "- The data are small. Show a table.",
])
def test_hints_solutions_code_comments_and_lists_are_not_examined(body):
    assert lines_flagged(exercise(body)) == []


def test_text_outside_an_exercise_is_not_examined():
    text = "A clinic records 40 visits. How many were new?\n\n" + exercise("Show it.")
    assert lines_flagged(text) == []


def test_opt_out_comment_exempts_the_exercise():
    body = "<!-- question-paragraph-ok: one-line prompt -->\nLet $p = 0.3$. Show that $q = 0.7$."
    assert lines_flagged(exercise(body)) == []


def test_added_lines_reads_a_zero_context_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +4,2 @@\n+x\n+y\n"
    assert eqp.added_lines(diff) == {"a.qmd": {4, 5}}


def test_a_finding_is_kept_only_when_the_diff_adds_a_line_of_its_paragraph():
    text = exercise("A clinic records 40 visits.\nHow many were new patients?")
    lines = text.split("\n")
    (item,) = eqp.exercises(lines)
    assert eqp.paragraph_touched(lines, item, {5})
    assert not eqp.paragraph_touched(lines, item, {1})
    assert not eqp.paragraph_touched(lines, item, {8})
