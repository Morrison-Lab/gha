"""Unit tests for check-definite-antecedents.

Covers which div openers are flagged, what exempts one (a link, a
cross-reference, code, comments, headings), diff scoping, and the defaults
the action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_definite_antecedents", _DIR / "check-definite-antecedents.py"
)
assert _spec is not None and _spec.loader is not None
oda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oda)


def hits(text: str):
    found, _ = oda.scan_file(text.split("\n"))
    return [(h.line, h.phrase) for h in found if h.kind == "opener"]


def demos(text: str):
    found, _ = oda.scan_file(text.split("\n"))
    return [h.line for h in found if h.kind == "demonstrative"]


@pytest.mark.parametrize("line", [
    "Exercise 9 asks you to make this precise.",
    "This is because the loss is convex.",
    "The second model avoids this.",
    "These are the same.",
    "Those are not the same.",
    "That means the step size shrinks.",
    "We can show this in two steps.",
    "Apply this to the data.",
    "Fit the model and then plot this, which is odd.",
    "Compare these with the truth.",
    "**This** shows the bias.",
    "We keep that.",
])
def test_bare_demonstratives_are_flagged(line):
    assert demos(line) == [1]


@pytest.mark.parametrize("line", [
    "This overfitting poses a problem.",
    "The result of this bias is large.",
    "a function that is convex",
    "We show that the estimate is unbiased.",
    "That is, the loss is convex.",
    "Consider this:",
    "Those who attend pass.",
    "Those samples were held out.",
    "In these days of data, we vary.",
    "In this way, the bias shrinks.",
    "Let `this` and $this$ be code and math.",
    "That's fine.",
    "The first-order Taylor expansion at this point is exact.",
    "Make this precise. <!-- check-definite-antecedents: allow -->",
])
def test_named_or_exempt_demonstratives_pass(line):
    assert demos(line) == []


def test_demonstratives_in_code_math_and_comments_are_ignored():
    text = "```r\nprint('this is')\n```\n\n$$\nx = this\n$$\n\n<!-- This is a note. -->\n"
    assert demos(text) == []


def test_demonstrative_in_a_div_body_is_flagged_on_its_line():
    text = "::: {#exr-a}\nFit a line.\nMake this precise.\n:::"
    assert demos(text) == [3]


def test_one_demonstrative_finding_per_line():
    assert demos("Use this or that.") == [1]


def test_allow_comment_also_exempts_an_opener():
    text = "::: {#exr-a}\nThe labels are bad. <!-- check-definite-antecedents: allow -->\n:::"
    assert hits(text) == []


def test_flags_unlinked_definite_opener():
    text = "::: {#exr-a}\nExplain the labels.\n:::\n\n::: {#exr-b}\nThe labels are bad.\n:::"
    assert hits(text) == [(6, "The labels")]


def test_indefinite_opener_is_fine():
    assert hits("::: {#exr-a}\nA label is a name.\n:::") == []


def test_defining_a_bolded_term_is_fine():
    assert hits("::: {#def-a}\nThe **mean** of a variable is its average.\n:::") == []


def test_link_or_crossref_exempts():
    assert hits("::: {#exr-a}\nThe [labels](#def-label) are bad.\n:::") == []
    assert hits("::: {#exr-a}\nThe labels of @exm-data are bad.\n:::") == []


def test_email_is_not_a_crossref():
    assert hits("::: {#exr-a}\nThe user a@b.org wrote.\n:::") == [(2, "The user")]  # phi-allow


def test_heading_is_skipped():
    assert hits("::: {#exr-a}\n## Title\nThe labels are bad.\n:::") == [(3, "The labels")]


def test_only_first_sentence_of_a_div_is_checked():
    assert hits("::: {#exr-a}\nFit a line. The line is bad.\n:::") == []


def test_code_and_comments_ignored():
    assert hits("```r\nThe x\n```") == []
    assert hits("<!--\nThe x\n-->\nA fine start.") == []


def test_file_without_div_checks_first_line():
    assert hits("This shows nothing.") == [(1, "This shows")]


def test_yaml_header_skipped():
    assert hits("---\ntitle: x\n---\n\nThe data are bad.") == [(5, "The data")]


def test_list_marker_stripped():
    assert hits("::: {#exr-a}\n1. The labels are bad.\n:::") == [(2, "The labels")]


def test_defaults_fail():
    assert oda._DEFAULT_FAIL is True
    assert oda.DEFAULT_GLOBS == "*.qmd"


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_diff_scope_flags_only_added_lines(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.org")  # phi-allow
    _git(tmp_path, "config", "user.name", "t")
    old = tmp_path / "old.qmd"
    old.write_text("::: {#exr-a}\nThe old labels.\n:::\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    new = tmp_path / "new.qmd"
    new.write_text("::: {#exr-b}\nThe new labels.\n:::\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "add")
    monkeypatch.chdir(tmp_path)
    report = oda.run_check("HEAD^1", ["*.qmd"], [], False)
    assert [(f[0], f[1]) for f in report.findings] == [("new.qmd", 2)]
    whole = oda.run_check("", ["*.qmd"], [], True)
    assert len(whole.findings) == 2


def test_skips_without_base_ref(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    assert oda.run_check("", ["*.qmd"], [], False).skipped
