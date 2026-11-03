"""Unit tests for check-heading-titles.

Covers the two rules (a question, an interrogative start including after a
colon), what is not counted (code fences, comments, fenced divs, the allow
marker, plain headings that merely contain an interrogative later), diff
scoping (an untouched heading is not reflagged, an added one is), the
skip-not-fallback guard, and the defaults the action and script must agree on.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_heading_titles", _DIR / "check-heading-titles.py"
)
assert _spec is not None and _spec.loader is not None
htt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(htt)


def kinds(tmp_path, body):
    path = tmp_path / "page.qmd"
    path.write_text(f'---\ntitle: "T"\n---\n\n{body}')
    return [(f.kind, f.line) for f in htt.scan_file(str(path), str(tmp_path))]


@pytest.mark.parametrize("title", [
    "What the coefficients mean",
    "Where cross-entropy comes from",
    "Why the loss is convex",
    "When the coefficients diverge",
    "Who needs regularization",
    "Which model to choose",
    "How the optimizer works",
    "how lower case starts",
])
def test_interrogative_start_is_flagged(tmp_path, title):
    assert kinds(tmp_path, f"# {title}\n") == [("interrogative", 5)]


def test_phrase_after_colon_is_flagged(tmp_path):
    assert kinds(tmp_path, "# Fitting: where the cost comes from\n") == [
        ("interrogative", 5)]


def test_question_is_flagged(tmp_path):
    assert kinds(tmp_path, "# Is the model calibrated?\n") == [("question", 5)]


def test_question_starting_with_how_gets_both(tmp_path):
    assert kinds(tmp_path, "# How sure are the coefficients?\n") == [
        ("question", 5), ("interrogative", 5)]


def test_attributes_are_ignored(tmp_path):
    assert kinds(tmp_path, "# What it means {#sec-meaning}\n") == [
        ("interrogative", 5)]


@pytest.mark.parametrize("title", [
    "Interpretation of the coefficients",
    "Fitting by maximum likelihood",
    "Uncertainty of the coefficients",
    "Whatever remains",
    "Howell's data",
    "Fitting: the cost function",
    "Estimating how much variance remains",
])
def test_plain_titles_pass(tmp_path, title):
    assert kinds(tmp_path, f"# {title}\n") == []


def test_not_counted_places(tmp_path):
    body = (
        "```\n# What is in a fence\n```\n\n"
        "<!-- # What is in a comment -->\n\n"
        "# Why allowed <!-- check-heading-titles: allow -->\n"
    )
    assert kinds(tmp_path, body) == []


def test_include_headings_are_not_the_pages_own(tmp_path):
    (tmp_path / "_sub.qmd").write_text("# What the include says\n")
    body = "{{< include _sub.qmd >}}\n"
    assert kinds(tmp_path, body) == []
    sub = htt.scan_file(str(tmp_path / "_sub.qmd"), str(tmp_path))
    assert [f.kind for f in sub] == ["interrogative"]


# -- diff scoping --------------------------------------------------------------

def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def init_repo(tmp_path, body):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow
    git(tmp_path, "config", "user.name", "T")
    (tmp_path / "page.qmd").write_text(f'---\ntitle: "T"\n---\n\n{body}')
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")


def test_only_added_headings_are_reported(tmp_path, monkeypatch):
    init_repo(tmp_path, "# What already exists\n")
    page = tmp_path / "page.qmd"
    page.write_text(page.read_text() + "\n# Why this is new\n")
    git(tmp_path, "commit", "-q", "-am", "add")
    monkeypatch.chdir(tmp_path)
    report = htt.run_check("HEAD^1", ["*.qmd"], [], False)
    assert [(f.line, f.kind) for f in report.findings] == [(7, "interrogative")]
    whole = htt.run_check("", ["*.qmd"], [], True)
    assert [f.line for f in whole.findings] == [5, 7]


def test_no_base_skips(tmp_path, monkeypatch):
    init_repo(tmp_path, "# What already exists\n")
    monkeypatch.chdir(tmp_path)
    report = htt.run_check("", ["*.qmd"], [], False)
    assert report.skipped and not report.findings


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
                / "check-heading-titles.yml").read_text()
    assert "HTT_FAIL: ${{ inputs.fail }}" in action
    assert "HTT_GLOBS: ${{ inputs.globs }}" in action
    assert htt._DEFAULT_FAIL is True
    assert htt.DEFAULT_GLOBS == "*.qmd"
    for text in (action, workflow):
        assert input_default(text, "fail") == "true"
        assert input_default(text, "globs") == htt.DEFAULT_GLOBS
        assert input_default(text, "whole-tree") == "false"


def test_div_titles_are_checked(tmp_path):
    body = (
        "::: {#exr-x}\n#### What the logistic function does\n:::\n\n"
        '::: {.callout-note title="Why this works"}\n:::\n\n'
        "::: {#exr-y}\n#### Properties of the logistic function\n:::\n"
    )
    assert kinds(tmp_path, body) == [("interrogative", 6), ("interrogative", 9)]


def test_div_title_allow_marker_and_fences(tmp_path):
    body = (
        "::: {#exr-x}\n"
        "#### Why allowed <!-- check-heading-titles: allow -->\n:::\n\n"
        "::: {#exr-y}\n```\n#### What in a fence\n```\n:::\n"
    )
    assert kinds(tmp_path, body) == []
