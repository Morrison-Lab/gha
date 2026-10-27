"""Unit tests for check-single-ask-parts.

Covers which parts are flagged, what is ignored (solutions, code, math,
comments, the allow comment), diff scoping, the skip-not-fall-back guard, and
the defaults the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_single_ask_parts", _DIR / "check-single-ask-parts.py"
)
assert _spec is not None and _spec.loader is not None
sap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sap)


def exercise(body: str) -> str:
    return "::: {#exr-a}\n" + body + "\n:::\n"


def flagged(body: str):
    """First line (1-based, in the whole document) of each flagged part."""
    found, _ = sap.scan_file(exercise(body).split("\n"))
    return [p.line for p in found]


# -- what is flagged ---------------------------------------------------------

@pytest.mark.parametrize("body", [
    "1. Compute the slope exactly, and compare it with the fitted value.",
    "Compute the mean. Then plot the residuals.",
    "- Fit the model; then report the slope.",
    "Explain why the line fits and then derive its variance.",
    "(a) Find the mean and then compare it with the median.",
    "Plot the data. Explain the trend.",
    "Fit the model, then report the slope.",
    "Compute the mean and also compare it with the median.",
])
def test_two_asks_are_flagged(body):
    assert flagged(body) == [2]


def test_reports_the_first_line_of_the_part():
    body = "Consider the data.\n\n1. Plot the data.\n2. Compute the slope, and compare it with 2."
    assert flagged(body) == [5]


def test_second_list_item_only_is_flagged():
    body = "1. Plot the data.\n2. Compute x. Then compare y."
    assert flagged(body) == [3]


# -- what is compliant -------------------------------------------------------

@pytest.mark.parametrize("body", [
    "1. Compute the slope exactly.",
    "Find the mean and the variance.",
    "Show that the estimator is unbiased.",
    "Consider the data. Compute the mean.",
    "1. Plot the data.\n2. Compare the two fits.",
    "Explain why the fit is poor, and why the residuals grow.",
    "Compare and contrast the two figures.",
    "Let $X$ have mass function $p$, and write $q_X$ for the variable that equals $q_k$.\nShow that the two are equal.",
])
def test_one_ask_is_not_flagged(body):
    assert flagged(body) == []


@pytest.mark.parametrize("body", [
    "Prompt.\n\n::: {.sol}\nCompute x. Then plot y.\n:::",
    "```r\ncompute(x); plot(y)\n```\nFind the mean.",
    "<!-- Compute x. Then plot y. -->\nFind the mean.",
    "<!-- single-ask-ok: one task -->\nCompute x. Then plot y.",
    "Compute x. Then plot y. <!-- single-ask-ok: one task -->",
    "$$\\text{compute } x, \\text{then plot } y$$\nFind x.",
])
def test_ignored(body):
    assert flagged(body) == []


def test_text_outside_an_exercise_is_ignored():
    found, seen = sap.scan_file("Compute x. Then plot y.\n".split("\n"))
    assert found == [] and seen == 0


# -- diff scoping ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "old.qmd").write_text(exercise("1. Compute x. Then plot y."))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(base="HEAD", whole_tree=False):
    return sap.run_check(base, ["*.qmd"], [], whole_tree)


def test_old_part_is_not_reflagged(repo):
    (repo / "new.qmd").write_text(exercise("1. Compute x."))
    _git(repo, "add", ".")
    assert _run().findings == []


def test_added_part_is_flagged(repo):
    (repo / "new.qmd").write_text(exercise("1. Compute x, and compare it with y."))
    _git(repo, "add", ".")
    assert _run().findings == [("new.qmd", 2, 2)]


def test_editing_an_old_part_flags_it(repo):
    (repo / "old.qmd").write_text(exercise("1. Compute z. Then plot y."))
    _git(repo, "add", ".")
    assert _run().findings == [("old.qmd", 2, 2)]


def test_whole_tree_flags_old_part(repo):
    assert _run(whole_tree=True).findings == [("old.qmd", 2, 2)]


def test_no_base_skips(repo):
    assert _run(base="").skipped


# -- defaults agree ----------------------------------------------------------

def test_default_is_warn_only():
    assert sap._DEFAULT_FAIL is False
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-single-ask-parts.yml").read_text()
    assert "default: 'false'" in _input_block(action, "fail")
    assert "default: false" in _input_block(workflow, "fail")


def _input_block(text: str, name: str) -> str:
    """The lines of one input, from its `name:` key to the next input."""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.strip() == f"{name}:" and l.startswith(("  ", "      ")))
    indent = len(lines[start]) - len(lines[start].lstrip())
    block = [lines[start]]
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        block.append(line)
    return "\n".join(block)


def test_a_part_exemption_does_not_hide_the_next_part():
    body = "<!-- single-ask-ok: one task -->\n1. Compute x. Then plot y.\n\n2. Compute x. Then plot y."
    assert flagged(body) == [5]


def test_an_exercise_exemption_sits_on_the_line_before_the_opening_fence():
    text = "<!-- single-ask-ok: one task -->\n::: {#exr-a}\nCompute x. Then plot y.\nAlso find z. Then plot w.\n:::\n"
    found, _ = sap.scan_file(text.split("\n"))
    assert found == []


def test_an_exercise_exemption_sits_on_the_opening_fence():
    text = "::: {#exr-a}  <!-- single-ask-ok: one task -->\nCompute x. Then plot y.\nAlso find z. Then plot w.\n:::\n"
    found, _ = sap.scan_file(text.split("\n"))
    assert found == []


def test_a_comment_with_a_code_span_keeps_the_later_spans():
    text, _ = sap.strip_comments("<!-- `a` --> Compute `b`", False)
    assert text == " Compute `b`"


def test_double_dollar_in_a_code_span_is_not_display_math():
    assert flagged("Write `$$` and compute x. Then plot y.") == [2]


def test_a_display_pair_on_one_line_keeps_the_prose_around_it():
    assert flagged("1. Compute $$\\hat\\beta$$, and compare it with $\\beta$.") == [2]


def test_display_math_inside_a_paragraph_does_not_split_the_part():
    body = "Compute the slope\n$$\nb = 2\n$$\nand compare it with the intercept."
    assert flagged(body) == [2]


def test_div_fences_inside_a_code_fence_do_not_open_a_solution():
    body = "Plot the data.\n```\n::: {.sol}\n```\nExplain the trend."
    found, _ = sap.scan_file(exercise(body).split("\n"))
    assert [p.line for p in found] == [2]


def test_inline_math_only_line_does_not_split_the_part():
    body = "Compute the slope\n$$ b = 2 $$\nand compare it with the intercept."
    assert flagged(body) == [2]


def test_prose_next_to_an_opening_display_delimiter_is_kept():
    body = "Plot the data, where $$\nb = 2\n$$ and explain the trend."
    assert flagged(body) == [2]


def test_prose_before_a_display_delimiter_counts():
    body = "Compute the slope, and compare it with y $$\nb = 2\n$$"
    assert flagged(body) == [2]


def test_main_warns_only_when_a_diff_fails(repo, monkeypatch, capsys):
    monkeypatch.setenv("SAP_BASE_REF", "")
    sap.main()
    assert "::warning::" not in capsys.readouterr().out
    monkeypatch.setenv("SAP_BASE_REF", "no-such-ref")
    sap.main()
    assert "::warning::" in capsys.readouterr().out


@pytest.mark.parametrize("middle", [
    "$b = 2$",
    "`b = 2`",
    "<!-- note -->",
])
def test_a_filled_line_inside_a_paragraph_does_not_split_the_part(middle):
    body = f"Compute the slope\n{middle}\nand compare it with the intercept."
    assert flagged(body) == [2]


def test_a_solution_without_blank_lines_ends_the_part():
    body = "Compute the slope.\n::: {.sol}\nThe slope is 2.\n:::\nPlot the data."
    assert flagged(body) == []


def test_a_part_starting_with_math_is_reported_on_its_first_line():
    body = "$f(x) = x^2$.\nCompute f, and compare it with g."
    assert flagged(body) == [2]


def test_a_line_that_closes_and_reopens_display_math_keeps_its_prose():
    body = "Compute $$\na = 1\n$$ and compare it with y, $$\nb = 2\n$$"
    assert flagged(body) == [2]


def test_main_says_so_when_the_whole_tree_cannot_be_listed(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAP_WHOLE_TREE", "true")
    sap.main()
    out = capsys.readouterr().out
    assert "::warning::" in out
    assert "not falling back" not in out
