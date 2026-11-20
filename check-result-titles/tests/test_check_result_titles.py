"""Unit tests for check-result-titles.

Covers the sentence test (verbs, auxiliaries, math relations, a customary
name before a colon, the first-word and clause-opener guards, noun-like words
left out of the verb list), which divs and titles are read (heading or title
attribute, result prefixes only, the first heading only, fences, comments, the
allow marker), diff scoping (an untouched title is not reflagged, a moved one
is not new, an added one is), the skip-not-fallback guard, and the defaults the
action, workflow and script must agree on.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_result_titles", _DIR / "check-result-titles.py"
)
assert _spec is not None and _spec.loader is not None
crt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crt)

PREFIXES = crt.DEFAULT_PREFIXES.split()


def flagged(tmp_path, body):
    path = tmp_path / "page.qmd"
    path.write_text(f'---\ntitle: "T"\n---\n\n{body}')
    return [f.line for f in crt.scan_file(str(path), PREFIXES)]


@pytest.mark.parametrize("title", [
    "A minimizer is a stationary point",
    "The cross-entropy loss equals the log loss",
    "Perplexity does not depend on the base",
    "XOR is not linearly separable",
    "The product feature separates XOR",
    "Relabeling the classes negates the coefficients",
    "Only points on the margin carry weight",
    "The two simple regression slopes multiply to the squared correlation",
    "$K$-means never raises the distortion",
    "The margin never increases with $C$",
    "Gradient descent converges when the step is below $2 / L$",
    "Best subset selection over $p$ features fits $2^p$ models",
    "Ridge divides each coefficient by $1 + c$",
    "A small enough step lowers the loss at every step",
    "Backfitting smooths the partial residuals",
    "Fixing the scale turns the program into a minimization",
    "Under squared-error loss, the empirical risk is the sample mean squared error",
    "Bias-variance decomposition: the expected error is the variance plus the squared bias",
    "Variance of a sum: $\\Var{X + Y} = \\Var{X} + \\Var{Y}$",
    "The derivative $\\sigma'(z) \\eqdef \\sigma(z)(1 - \\sigma(z))$",
    "Separated data have no maximum likelihood estimate",
])
def test_sentences_pass(title):
    assert crt.is_sentence(title), title


@pytest.mark.parametrize("title", [
    "Derivative of the logistic function",
    "The normal equations",
    "Bounds on the leverage",
    "Recovering the coefficients from the dual",
    "Hoeffding's inequality for a held-out set",
    "Bias-variance decomposition",
    "Mean and covariance of the least squares estimate",
    "Level sets of an affine function",
    "Shortcut formulas for the centered sums",
    "Parameter counts of the classifiers",
    # "smooth" and "lower" are adjectives in their base form.
    "Minimizing a smooth convex function",
    "A lower bound on the risk",
    # A verb in a relative clause does not make the title a sentence.
    "Number of models that best subset selection fits",
    "A step size that is safe for every coefficient vector",
    # The first word never counts as the verb.
    "Equals and its uses",
    # Math with no relation is not a statement.
    "The margin of a point, in $p$ dimensions",
])
def test_noun_phrases_fail(title):
    assert not crt.is_sentence(title), title


def test_a_link_and_code_do_not_hide_the_verb():
    assert crt.is_sentence("The [log loss](x.qmd#def-log-loss) is convex")
    assert not crt.is_sentence("The `is` operator in R")


def test_heading_title_of_result_divs_is_read(tmp_path):
    body = (
        "::: {#thm-a}\n## Derivative of the logistic function\n\nText.\n:::\n\n"
        "::: {#lem-b}\n#### The logistic function is steepest at zero\n:::\n\n"
        ":::{#cor-c}\n# The normal equations\n:::\n"
    )
    assert flagged(tmp_path, body) == [6, 16]


def test_title_attribute_is_read(tmp_path):
    body = '::: {#prp-a title="Gradient of the squared error"}\nText.\n:::\n'
    assert flagged(tmp_path, body) == [5]


def test_other_divs_are_not_read(tmp_path):
    body = (
        "::: {#def-a}\n## Derivative of the logistic function\n:::\n\n"
        "::: {#exm-b}\n## The normal equations\n:::\n\n"
        "::: {.callout-note}\n## Gradient of the loss\n:::\n"
    )
    assert flagged(tmp_path, body) == []


def test_only_the_first_heading_is_the_title(tmp_path):
    body = (
        "::: {#thm-a}\n## The hat matrix is a projection\n\n"
        "### Proof sketch\n:::\n\n"
        "::: {#thm-b}\nThe statement comes first.\n\n## Later heading\n:::\n"
    )
    assert flagged(tmp_path, body) == []


def test_a_nested_div_is_not_the_title(tmp_path):
    body = (
        "::: {#thm-a}\n::: {.content-visible}\n## Inner heading only\n:::\n:::\n"
    )
    assert flagged(tmp_path, body) == []


def test_fences_comments_and_allow_marker(tmp_path):
    body = (
        "::: {#thm-a}\n"
        "## The VC bound <!-- check-result-titles: allow: a named bound -->\n"
        ":::\n\n"
        "<!--\n::: {#thm-b}\n## Commented out\n:::\n-->\n\n"
        "```\n::: {#thm-c}\n## In a fence\n:::\n```\n"
    )
    assert flagged(tmp_path, body) == []


def test_custom_prefixes(tmp_path):
    path = tmp_path / "page.qmd"
    path.write_text("::: {#alg-a}\n## Gradient descent\n:::\n")
    assert crt.scan_file(str(path), PREFIXES) == []
    assert [f.line for f in crt.scan_file(str(path), ["alg"])] == [2]


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def init_repo(tmp_path, body):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow
    git(tmp_path, "config", "user.name", "T")
    (tmp_path / "page.qmd").write_text(f'---\ntitle: "T"\n---\n\n{body}')
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")


def test_only_added_titles_are_reported(tmp_path, monkeypatch):
    init_repo(tmp_path, "::: {#thm-a}\n## The normal equations\n:::\n")
    page = tmp_path / "page.qmd"
    page.write_text(page.read_text()
                    + "\n::: {#thm-b}\n## Gradient of the loss\n:::\n")
    git(tmp_path, "commit", "-q", "-am", "add")
    monkeypatch.chdir(tmp_path)
    report = crt.run_check("HEAD^1", ["*.qmd"], [], False)
    assert [f.line for f in report.findings] == [10]
    whole = crt.run_check("", ["*.qmd"], [], True)
    assert [f.line for f in whole.findings] == [6, 10]


def test_moved_title_is_not_new(tmp_path, monkeypatch):
    init_repo(tmp_path, "Intro.\n\n::: {#thm-a}\n## The normal equations\n:::\n")
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "T"\n---\n\n'
                    "::: {#thm-a}\n## The normal equations\n:::\n\nIntro.\n")
    git(tmp_path, "commit", "-q", "-am", "move")
    monkeypatch.chdir(tmp_path)
    assert crt.run_check("HEAD^1", ["*.qmd"], [], False).findings == []


def test_no_base_skips(tmp_path, monkeypatch):
    init_repo(tmp_path, "::: {#thm-a}\n## The normal equations\n:::\n")
    monkeypatch.chdir(tmp_path)
    report = crt.run_check("", ["*.qmd"], [], False)
    assert report.skipped and not report.findings


def test_main_exit_codes(tmp_path, monkeypatch):
    init_repo(tmp_path, "::: {#thm-a}\n## The normal equations\n:::\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CRT_WHOLE_TREE", "true")
    assert crt.main() == 1
    monkeypatch.setenv("CRT_FAIL", "false")
    assert crt.main() == 0


def input_default(text, name):
    """The ``default:`` of the input ``name`` in an action or workflow file."""
    match = re.search(
        rf"^( +){name}:\n(?:\1 +.*\n)*?\1 +default: *'?([^'\n]*)'?$",
        text, re.MULTILINE)
    assert match, f"no default for input {name}"
    return match.group(2)


def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-result-titles.yml").read_text()
    for var, name in (("CRT_FAIL", "fail"), ("CRT_GLOBS", "globs"),
                      ("CRT_PREFIXES", "prefixes"),
                      ("CRT_WHOLE_TREE", "whole-tree")):
        assert f"{var}: ${{{{ inputs.{name} }}}}" in action
    assert crt._DEFAULT_FAIL is True
    for text in (action, workflow):
        assert input_default(text, "fail") == "true"
        assert input_default(text, "globs") == crt.DEFAULT_GLOBS
        assert input_default(text, "prefixes") == crt.DEFAULT_PREFIXES
        assert input_default(text, "whole-tree") == "false"
