"""Unit tests for check-axis-titles.

Covers which strings count as a plain-word title, which calls are axis titles
(ggplot2, matplotlib, plotly; one line or spanning lines), the exemption
comment and its reason, diff scoping, and the defaults the action, the
reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_axis_titles", _DIR / "check-axis-titles.py"
)
assert _spec is not None and _spec.loader is not None
axt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(axt)


def bad(text: str):
    """Flagged title strings for a document string."""
    found, _ = axt.scan_file(text.split("\n"), None)
    return [t.text for t in found]


@pytest.mark.parametrize("title", [
    "x", "y", "z", "x1", "f(x)", "y h(x)", "p", r"$\hat{y}$", "$z$", "pi",
])
def test_bare_symbol_or_expression_has_no_plain_word(title):
    assert not axt.has_plain_word(title)


@pytest.mark.parametrize("title", [
    "mpg", "Log-odds, η", "Probability, π", "Weight (lb)", "RMSE",
    "horsepower", "Score $z$", "Body mass index (bmi)",
])
def test_title_with_a_word_is_fine(title):
    assert axt.has_plain_word(title)


# -- which calls are axis titles ---------------------------------------------

def test_matplotlib_labels():
    assert bad('ax.set_xlabel("x")\nax.set_ylabel("Miles per gallon")') == ["x"]


def test_ggplot_xlab_ylab():
    assert bad('p + xlab("z") + ylab("Probability")') == ["z"]


def test_labs_one_line():
    assert bad('labs(x = "x1", y = "x2", colour = "g")') == ["x1", "x2"]


def test_labs_spanning_lines():
    text = 'ggplot(d) +\n  labs(\n    x = "x",\n    y = "Probability, p",\n    colour = "z"\n  )'
    assert bad(text) == ["x"]


def test_x_equals_outside_labs_is_not_a_title():
    assert bad('aes(x = "x")\nlist(y = "y")') == []


def test_labs_depth_resets_after_the_call():
    text = 'labs(\n  x = "Weight (lb)"\n) +\n  other(x = "x")'
    assert bad(text) == []


def test_plotly_axis_titles():
    assert bad('fig.update_layout(xaxis_title="x", yaxis_title="Density")') == ["x"]
    assert bad('layout(xaxis = list(title = "z"), yaxis = list(title = "Rate"))') == ["z"]


def test_single_quotes():
    assert bad("ax.set_xlabel('x')") == ["x"]


def test_null_and_variable_titles_are_not_examined():
    assert bad("labs(x = NULL, y = NULL)\nax.set_xlabel(label)") == []


def test_empty_and_placeholder_titles_are_not_flagged():
    assert bad('ax.set_xlabel("")\nax.set_ylabel("...")') == []


def test_raw_string_prefix():
    assert bad('ax.set_xlabel(r"$\\eta$")') == [r"$\eta$"]


# -- exemptions --------------------------------------------------------------

def test_exemption_needs_a_reason():
    assert bad('ax.set_xlabel("x")  # axis-title-ok: the data column is named x') == []
    assert bad('ax.set_xlabel("x")  # axis-title-ok:') == ["x"]


# -- diff scoping ------------------------------------------------------------

def test_only_kept_lines_are_reported():
    lines = ['ax.set_xlabel("x")', 'ax.set_ylabel("y")']
    found, seen = axt.scan_file(lines, {2})
    assert [t.text for t in found] == ["y"]
    assert seen == 2


def test_multiline_labs_attributes_to_the_string_line():
    lines = ["labs(", '  x = "x",', '  y = "Probability"', ")"]
    found, _ = axt.scan_file(lines, {2})
    assert [(t.line, t.text) for t in found] == [(2, "x")]
    found, _ = axt.scan_file(lines, {3})
    assert found == []


def test_skips_without_a_base_ref():
    report = axt.run_check("", ["*.qmd"], [], False)
    assert report.skipped


# -- the action, workflow and script agree -----------------------------------

def test_defaults_agree():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-axis-titles.yml").read_text()
    default_globs = axt.DEFAULT_GLOBS
    assert f"default: '{default_globs}'" in action
    assert f"default: '{default_globs}'" in workflow
    assert axt._DEFAULT_FAIL is True
    assert re.search(r"fail:\s*\n(?:.*\n)*?\s*default: true", workflow)
