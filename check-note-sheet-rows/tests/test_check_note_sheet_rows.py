"""Unit tests for check-note-sheet-rows.

Covers which rows are flagged (notation in a label, a label joining two
concepts, two formulas in one cell), what is left alone (separator rows, rows
in code fences, a link label, one formula per cell), and the defaults the
action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_note_sheet_rows", _DIR / "check-note-sheet-rows.py"
)
assert _spec is not None and _spec.loader is not None
nsr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nsr)


def reasons(text: str):
    return [f.reason for f in nsr.scan_rows(text.split("\n"))]


@pytest.mark.parametrize("row", [
    "| Dot product | $\\dprod{\\vx}{\\vy} = \\sumin x_i y_i$ |",
    "| [Design matrix](linear-regression.qmd#def-design-matrix) | $\\design(\\mx)$ |",
    "| Assume | $\\stprod{\\design(\\mx)}$ invertible |",
    "| [$k$-fold cross-validation](big-ideas.qmd#def-cross-validation) | $\\frac{1}{k} \\sum_j \\text{MSE}_j$ |",
    "| Sample MSE, matrix form | $\\frac{1}{n} \\norm{\\vy}$ |",
    "| | |",
    "| --- | --- |",
    "| Product | $(a \\times b)(b \\times c)$ is $a \\times c$ |",
])
def test_clean_rows_pass(row):
    assert reasons(row) == []


def test_notation_in_label():
    assert reasons("| Degree at most $d$ | $\\sum a_j \\le d$ |") == [
        "the label holds notation"]


def test_label_joining_two_concepts():
    assert reasons("| Dot product, sample mean | $\\bar{y}$ |") == [
        "the label joins two concepts"]
    assert reasons("| Bias and variance | $b$ |") == [
        "the label joins two concepts"]


def test_two_formulas_in_one_cell():
    assert reasons("| Moments | $\\mu = 1$, $\\sigma = 2$ |") == [
        "one cell holds two formulas"]
    assert reasons("| Moments | $\\mu = 1$ and $\\sigma = 2$ |") == [
        "one cell holds two formulas"]


def test_formula_with_trailing_words_is_one_formula():
    assert reasons("| Product | $a$ is $b$ |") == []


def test_code_fence_rows_ignored():
    text = "```\n| Dot product, sample mean | $x$ |\n```"
    assert reasons(text) == []


def test_line_numbers():
    found = nsr.scan_rows(["intro", "| Dot product, sample mean | $x$ |"])
    assert [f.line for f in found] == [2]


def test_defaults_agree_with_action():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    assert f"default: '{nsr.DEFAULT_GLOBS}'" in action
    assert nsr._DEFAULT_FAIL is False
    assert "default: 'false'" in action
