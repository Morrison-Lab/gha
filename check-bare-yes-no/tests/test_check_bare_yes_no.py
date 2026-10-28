"""Unit tests for check-bare-yes-no.

Covers what is flagged (a bare Yes or No opening a solution paragraph or list
item, plain or bolded), what is not (a conclusion sentence, "No other ...",
text outside a solution, code, comments), diff scoping, and the defaults the
script, the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_bare_yes_no", _DIR / "check-bare-yes-no.py"
)
assert _spec is not None and _spec.loader is not None
byn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(byn)


def flagged(text: str):
    return [n for n, _ in byn.bare_answers(text.split("\n"))]


def sol(body: str, attrs: str = "{#sol-a}") -> str:
    return f"::: {attrs}\n{body}\n:::"


@pytest.mark.parametrize("opener", [
    "No.", "Yes.", "No", "**No.**", "**No**.", "*Yes.*", "_No._",
    "No. The irreducible error is a lower bound.",
    "Yes! It is.",
])
def test_bare_opener_is_flagged(opener):
    assert flagged(sol(opener)) == [2]


@pytest.mark.parametrize("prefix", ["a. ", "(a) ", "- ", "1. ", "> "])
def test_bare_opener_after_a_list_marker_is_flagged(prefix):
    assert flagged(sol(prefix + "No. The reason.")) == [2]


@pytest.mark.parametrize("opener", [
    "No, the test error cannot be below the irreducible error.",
    "No: it's not possible that the advanced network has a test error of 0.25.",
    "Yes: the estimator is unbiased.",
    "Yes, the estimator is unbiased.",
    "No other notes are allowed.",
    "Not possible.",
    "Yesterday it rained.",
    "**No**, it cannot.",
])
def test_a_stated_conclusion_is_not_flagged(opener):
    assert flagged(sol(opener)) == []


def test_text_outside_a_solution_is_not_flagged():
    assert flagged("::: {#exr-a}\nNo.\n:::\n\nNo.\n") == []


@pytest.mark.parametrize("attrs", ["{#sol-a}", "{.sol}", "{.solution}", "{.answer}"])
def test_solution_div_forms(attrs):
    assert flagged(sol("No.", attrs)) == [2]


def test_nested_div_stays_in_the_solution_and_exit_ends_it():
    text = "::: {.sol}\n::: {.callout-note}\nNo.\n:::\nYes.\n:::\nNo.\n"
    assert flagged(text) == [3, 5]


def test_code_and_comments_are_skipped():
    body = "```\nNo.\n```\n<!-- \nNo.\n-->\n<!-- No. -->\nNo."
    assert flagged(sol(body)) == [9]


def test_only_a_paragraph_opening_is_checked():
    assert flagged(sol("The answer is no.\n\nNo. A new paragraph.")) == [4]


def test_a_wrapped_continuation_line_is_not_flagged():
    assert flagged(sol("The answer is\nNo. It continues.")) == []


def test_a_list_item_is_an_opener_without_a_blank_line():
    assert flagged(sol("a. First.\nb. No. Second.")) == [3]


def test_class_names_must_match_exactly():
    assert flagged(sol("No.", "{.solution-notes}")) == []
    assert flagged(sol("No.", "{.answer-key}")) == []


def test_emphasis_runs_match_in_linear_time():
    assert flagged(sol("No" + "*" * 5000 + "x")) == []


def test_added_lines_scopes_the_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +5,2 @@\n+x\n+y\n+++ /dev/null\n"
    assert byn.added_lines(diff) == {"a.qmd": {5, 6}}


def test_defaults_agree_across_script_action_and_workflow():
    def input_block(text: str, name: str) -> str:
        start = text.index(f"\n      {name}:" if "workflow_call" in text else f"\n  {name}:")
        return text[start:].split("\n\n")[0]

    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-bare-yes-no.yml").read_text()
    assert byn._flag("BYN_FAIL", True) is True  # the script's default, with the variable unset
    assert "default: 'true'" in input_block(action, "fail")
    assert "default: true" in input_block(workflow, "fail")
    assert "default: '*.qmd'" in input_block(action, "globs")
    assert "default: '*.qmd'" in input_block(workflow, "globs")
