"""Unit tests for check-note-sheet-rows.

Covers which rows are flagged (notation in a label, a label joining two
concepts, two formulas in one cell), what is left alone (separator rows, rows
in code fences, a link label, one formula per cell), and the defaults the
action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
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


def test_header_row_not_flagged():
    text = "| Term and definition | Formula |\n| --- | --- |\n| Mean | $m$ |"
    assert reasons(text) == []


# -- diff scoping, in throwaway git repositories -----------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _repo(tmp_path, before: str, after: str):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
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
