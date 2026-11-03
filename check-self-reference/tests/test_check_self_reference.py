"""Unit tests for check-self-reference.

Covers the pattern (structural noun plus a verb that reports what the notes
do), what is not counted (code fences, comments, front matter, the allow
marker, content sentences, figure and table sentences), diff scoping (an
untouched sentence is not reflagged, an added one is), the skip-not-fallback
guard, and the defaults the action and script must agree on.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_self_reference", _DIR / "check-self-reference.py"
)
assert _spec is not None and _spec.loader is not None
srf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srf)


def flagged(tmp_path, body):
    path = tmp_path / "page.qmd"
    path.write_text(f'---\ntitle: "T"\n---\n\n{body}')
    return [f.line for f in srf.scan_file(str(path))]


@pytest.mark.parametrize("sentence", [
    "This exercise shows that the negative gradient is the best answer.",
    "This exercise and the ones that follow it establish the properties.",
    "These exercises prove the bound.",
    "This chapter covers what a network can represent.",
    "This chapter is about that mixture.",
    "This exercise computes the cost of that precaution.",
    "This exercise handles the multiplication and the activation function.",
    "This section explains the criterion.",
    "This solution derives the update.",
    "Go downhill. This exercise shows which way.",
    "this lecture introduces the model.",
    "The next exercises establish the properties of the sigmoid.",
    "Go downhill. The previous section defined the cost.",
    "The following exercises make this precise.",
])
def test_self_reference_is_flagged(tmp_path, sentence):
    assert flagged(tmp_path, sentence + "\n")


@pytest.mark.parametrize("sentence", [
    "The negative gradient decreases the cost the most.",
    "Table 2 shows the estimates.",
    "This figure shows the fitted curve.",
    "This example shows a pitfall.",
    "This exercise requires the dataset.",
    "The exercise shows nothing, as a word in a longer sentence.",
    "In this exercise we compute the cost.",
    "This exercises the muscles.",
    "This problem does not have a closed form.",
    "This solution shows up twice in the table.",
    "This section does the bookkeeping.",
    "Exercises @exr-a through @exr-b establish the properties.",
    "The next step is to differentiate the cost.",
    "The following equation holds for every x.",
    "In the next section we derive the update.",
])
def test_content_sentences_pass(tmp_path, sentence):
    assert flagged(tmp_path, sentence + "\n") == []


def test_not_counted_places(tmp_path):
    body = (
        "```\nThis exercise shows a fence.\n```\n\n"
        "<!-- This exercise shows a comment. -->\n\n"
        "<!--\nThis exercise shows a long comment.\n-->\n\n"
        "This exercise shows an exempt line. <!-- check-self-reference: allow -->\n"
    )
    assert flagged(tmp_path, body) == []


def test_front_matter_is_skipped(tmp_path):
    path = tmp_path / "page.qmd"
    path.write_text('---\ntitle: "This chapter covers x"\n---\n\nPlain.\n')
    assert srf.scan_file(str(path)) == []


def test_line_numbers_are_reported(tmp_path):
    assert flagged(tmp_path, "Plain.\n\nThis chapter covers x.\n") == [7]


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


def test_only_added_lines_are_reported(tmp_path, monkeypatch):
    init_repo(tmp_path, "This chapter covers what already exists.\n")
    page = tmp_path / "page.qmd"
    page.write_text(page.read_text() + "\nThis exercise shows the new one.\n")
    git(tmp_path, "commit", "-q", "-am", "add")
    monkeypatch.chdir(tmp_path)
    report = srf.run_check("HEAD^1", ["*.qmd"], [], False)
    assert [f.line for f in report.findings] == [7]
    whole = srf.run_check("", ["*.qmd"], [], True)
    assert [f.line for f in whole.findings] == [5, 7]


def test_no_base_skips(tmp_path, monkeypatch):
    init_repo(tmp_path, "This chapter covers what already exists.\n")
    monkeypatch.chdir(tmp_path)
    report = srf.run_check("", ["*.qmd"], [], False)
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
                / "check-self-reference.yml").read_text()
    assert "SRF_FAIL: ${{ inputs.fail }}" in action
    assert "SRF_GLOBS: ${{ inputs.globs }}" in action
    assert srf._DEFAULT_FAIL is True
    assert srf.DEFAULT_GLOBS == "*.qmd"
    for text in (action, workflow):
        assert input_default(text, "fail") == "true"
        assert input_default(text, "globs") == srf.DEFAULT_GLOBS
        assert input_default(text, "whole-tree") == "false"
