"""Unit tests for check-note-sheet-rows.

Covers which rows are flagged (notation in a label, a label joining two
concepts, two formulas in one cell), what is left alone (separator rows, rows
in code fences, a link label, one formula per cell), and the defaults the
action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
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
    return [f.reason for f in nsr.scan_rows(text.split("\n")) if not f.hard]


def hard_reasons(text: str):
    return [f.reason for f in nsr.scan_rows(text.split("\n")) if f.hard]


@pytest.mark.parametrize("row", [
    "| Dot product | $\\dprod{\\vx}{\\vy} = \\sumin x_i y_i$ |",
    "| [Design matrix](linear-regression.qmd#def-design-matrix) | $\\design(\\mx)$ |",
    "| Condition | $\\stprod{\\design(\\mx)}$ invertible |",
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


# -- prose rules (gha#1201): always errors -----------------------------------

@pytest.mark.parametrize("row", [
    "| Product | $(a \\times b)(b \\times c)$ is $a \\times c$ |",
    "| Transpose | $a \\times b$ becomes $b \\times a$ |",
    "| Assume | $\\stprod{\\design(\\mx)}$ invertible |",
])
def test_words_in_a_formula_cell_are_prose(row):
    assert hard_reasons(row) == ["a formula cell holds prose"]


@pytest.mark.parametrize("label", [
    "The mean is the average of the values.",
    "A label that runs on for far too many words",
])
def test_sentence_label_is_prose(label):
    assert hard_reasons(f"| {label} | $m$ |") == ["the label is prose"]


def test_brief_labels_and_math_only_cells_pass():
    text = "| Sample mean | $\\bar{y}$ |\n| Sample MSE, matrix form | $\\mx$ |"
    assert hard_reasons(text) == []


def test_inline_comma_list_outside_a_table_fails():
    # The closing line of lds#1267 before it was made a table.
    text = "**Values:** $e \\approx 2.718$, $\\ln 2 \\approx 0.693$, $\\ln 3 \\approx 1.099$."
    assert hard_reasons(text) == [
        "a paragraph outside a table (put a list in a table or bullets)"]


def test_plain_paragraph_fails():
    assert hard_reasons("Remember to bring a calculator.") == [
        "a paragraph outside a table (put a list in a table or bullets)"]


def test_structure_lines_pass():
    text = "\n".join([
        "---", "title: Sheet", "---", "",
        "::: {.content-visible when-format=\"html\"}",
        "[Download the PDF](sheet.pdf)", ":::", "",
        "## Heading", "**Linear regression**", "",
        "| $\\euler$ | $\\ln 2$ |", "| --- | --- |", "| $2.718$ | $0.693$ |", "",
        ": {tbl-colwidths=\"[35,65]\"}", "",
        "- $x$", "- $y$",
    ])
    assert hard_reasons(text) == []


def test_wrapped_bullet_continuation_passes():
    assert hard_reasons("- $x$\n  continues here\n- $y$") == []


def test_indented_line_after_a_paragraph_still_fails():
    assert hard_reasons("Some prose.\n  more prose") != []


def test_multiline_html_comment_passes():
    assert hard_reasons("<!-- a long\nnote that spans\nlines -->\n| A | $x$ |") == []


@pytest.mark.parametrize("line", [
    "![Alt text](figure.png)",
    "> A quoted line",
    "<div class=\"x\">",
])
def test_images_quotes_and_raw_html_pass(line):
    assert hard_reasons(line) == []


def test_link_text_in_a_formula_cell_counts_as_words():
    assert hard_reasons("| Mean | [definition](x.qmd) |") == [
        "a formula cell holds prose"]


def test_bullet_with_two_formulas_fails():
    assert hard_reasons("- $x$, $y$") == ["a bullet holds two formulas"]


def test_front_matter_is_skipped():
    assert hard_reasons("---\ntitle: A long title with words\n---") == []


def test_prose_is_an_error_even_when_fail_is_false(tmp_path, monkeypatch, capsys):
    _repo(tmp_path, GOOD + "\n", GOOD + "\nSome prose.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NSR_BASE_REF", "HEAD^1")
    monkeypatch.setenv("NSR_FAIL", "false")
    assert nsr.main() == 1
    assert "::error file=x-note-sheet.qmd,line=2::" in capsys.readouterr().out


def test_code_fence_rows_ignored():
    text = "```\n| Dot product, sample mean | $x$ |\n```"
    assert reasons(text) == []


def test_line_numbers():
    found = nsr.scan_rows(["## Intro", "| Dot product, sample mean | $x$ |"])
    assert [f.line for f in found] == [2]


def test_defaults_agree_with_action():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    assert f"default: '{nsr.DEFAULT_GLOBS}'" in action
    assert nsr._DEFAULT_FAIL is False
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-note-sheet-rows.yml").read_text(encoding="utf-8")
    for text in (action, workflow):
        block = re.search(r"^( +)fail:\n((?:\1 .*\n)+)", text, re.MULTILINE)
        assert block is not None
        assert re.search(r"default: '?false'?$", block.group(2), re.MULTILINE)


def test_variant_suffix_does_not_hide_a_joined_label():
    assert reasons("| Sample MSE, matrix form | $\\frac{1}{n}$ |") == []
    assert reasons("| Bias and variance, matrix form | $b$ |") == [
        "the label joins two concepts"]


def test_header_row_not_flagged():
    text = "| Term and definition | Formula |\n| --- | --- |\n| Mean | $m$ |"
    assert reasons(text) == []


# -- diff scoping, in throwaway git repositories -----------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _repo(tmp_path, before: str, after: str):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow
    _git(tmp_path, "config", "user.name", "t")
    sheet = tmp_path / "x-note-sheet.qmd"
    sheet.write_text(before, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    sheet.write_text(after, encoding="utf-8")
    _git(tmp_path, "commit", "-q", "-am", "change")


BAD = "| Dot product, sample mean | $x$ |"
GOOD = "| Dot product | $x$ |"


def test_only_added_rows_are_reported(tmp_path, monkeypatch):
    _repo(tmp_path, BAD + "\n", BAD + "\n" + BAD.replace("Dot", "Cross") + "\n")
    monkeypatch.chdir(tmp_path)
    report = nsr.run_check("HEAD^1", [nsr.DEFAULT_GLOBS], [], False)
    assert [f[1] for f in report.findings] == [2]


def test_untouched_bad_row_is_not_reflagged(tmp_path, monkeypatch):
    _repo(tmp_path, BAD + "\n", BAD + "\n" + GOOD + "\n")
    monkeypatch.chdir(tmp_path)
    report = nsr.run_check("HEAD^1", [nsr.DEFAULT_GLOBS], [], False)
    assert report.findings == []


def test_whole_tree_reports_existing_rows(tmp_path, monkeypatch):
    _repo(tmp_path, BAD + "\n", BAD + "\n" + GOOD + "\n")
    monkeypatch.chdir(tmp_path)
    report = nsr.run_check("", [nsr.DEFAULT_GLOBS], [], True)
    assert [f[1] for f in report.findings] == [1]


def test_no_base_ref_skips(tmp_path, monkeypatch):
    _repo(tmp_path, BAD + "\n", BAD + "\n" + GOOD + "\n")
    monkeypatch.chdir(tmp_path)
    assert nsr.run_check("", [nsr.DEFAULT_GLOBS], [], False).skipped


def test_unresolvable_base_ref_skips(tmp_path, monkeypatch):
    _repo(tmp_path, BAD + "\n", BAD + "\n" + GOOD + "\n")
    monkeypatch.chdir(tmp_path)
    assert nsr.run_check("no-such-ref", [nsr.DEFAULT_GLOBS], [], False).skipped


def test_moved_row_is_not_reported(tmp_path, monkeypatch):
    other = "| Other | $y$ |"
    _repo(tmp_path, BAD + "\n" + other + "\n", other + "\n" + BAD + "\n")
    monkeypatch.chdir(tmp_path)
    report = nsr.run_check("HEAD^1", [nsr.DEFAULT_GLOBS], [], False)
    assert report.findings == []


def test_paths_ignore(tmp_path, monkeypatch):
    _repo(tmp_path, GOOD + "\n", GOOD + "\n" + BAD + "\n")
    monkeypatch.chdir(tmp_path)
    ignores = nsr.compile_ignores(["x-note-sheet.qmd"])
    report = nsr.run_check("HEAD^1", [nsr.DEFAULT_GLOBS], ignores, False)
    assert report.findings == []


def test_fail_exit_code(tmp_path, monkeypatch):
    _repo(tmp_path, GOOD + "\n", GOOD + "\n" + BAD + "\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NSR_BASE_REF", "HEAD^1")
    monkeypatch.setenv("NSR_FAIL", "true")
    assert nsr.main() == 1
    monkeypatch.setenv("NSR_FAIL", "false")
    assert nsr.main() == 0
