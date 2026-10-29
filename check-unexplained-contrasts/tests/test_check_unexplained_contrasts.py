"""Unit tests for check-unexplained-contrasts (gha#1302).

The regression case is Ezra's lds#def-feature review: "Statistics uses
predictor for a feature, not for a model" with no reason or source.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_unexplained_contrasts", _DIR / "check-unexplained-contrasts.py"
)
assert _spec is not None and _spec.loader is not None
uct = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uct)


def hits(text: str):
    return [(f.line, f.phrase) for f in uct.scan_contrasts(text.split("\n"))]


LDS_FEATURE = """::: {#def-feature}
A **feature** is one measured property of an input.
Statistics uses *predictor* for a feature, not for a model.
:::"""


def test_regression_lds_feature_contrast_is_flagged():
    assert hits(LDS_FEATURE) == [(3, "not for")]


def test_the_same_contrast_with_a_citation_is_fine():
    text = ("::: {#rem-x}\n"
            "Statistics uses predictor for a feature, not for a model.\n"
            "Hastie et al. use it for a function [@hastie2009esl, eq. 15.2].\n"
            ":::")
    assert hits(text) == []


@pytest.mark.parametrize("sentence,phrase", [
    ("It is a task, not an algorithm.", "not an"),
    ("It does not mean the average.", "does not mean"),
    ("The two words do not mean the same thing.", "do not mean"),
    ("This is not to be confused with the mean.", "not to be confused with"),
    ("A hyperparameter is not a parameter.", "is not a"),
    ("It is a choice rather than a constant.", "rather than a"),
])
def test_each_phrase_is_flagged(sentence, phrase):
    text = f"::: {{#rem-x}}\n{sentence}\n:::"
    assert [p for _, p in hits(text)] == [phrase]


@pytest.mark.parametrize("div_id", ["def-x", "rem-x", "note-x"])
def test_read_div_kinds(div_id):
    assert hits(f"::: {{#{div_id}}}\nIt is a task, not a method.\n:::") == [(2, "not a")]


def test_other_div_kinds_are_not_read():
    assert hits("::: {#exm-x}\nIt is a task, not a method.\n:::") == []
    assert hits("::: {#thm-x}\nIt is a task, not a method.\n:::") == []
    assert hits("It is a task, not a method.") == []


def test_allow_marker_exempts_the_line():
    text = "::: {#rem-x}\nH is not a tree. <!-- check-unexplained-contrasts: allow -->\n:::"
    assert hits(text) == []


def test_code_fence_math_comment_and_inline_code_are_skipped():
    text = "\n".join([
        "::: {#rem-x}",
        "```r",
        "x <- not a thing, not a method",
        "```",
        "$$",
        "x, not a y",
        "$$",
        "<!-- a task, not a method -->",
        "Use `, not a` literally.",
        ":::",
    ])
    assert hits(text) == []


def test_a_citation_anywhere_in_the_div_clears_every_hit():
    text = ("::: {#rem-x}\n"
            "A task, not a method.\n"
            "A choice rather than a constant.\n"
            "See [@murphy2012mlpp].\n"
            ":::")
    assert hits(text) == []


def test_a_citation_in_another_div_does_not_clear_this_one():
    text = ("::: {#rem-x}\nA task, not a method.\n:::\n"
            "::: {#rem-y}\nSee [@murphy2012mlpp].\n:::")
    assert hits(text) == [(2, "not a")]


def test_a_negation_without_a_contrast_phrase_is_fine():
    assert hits("::: {#rem-x}\nWe did not reject the null.\n:::") == []


def test_parse_diff_scopes_to_added_lines():
    diff = (
        "diff --git a/a.qmd b/a.qmd\n--- a/a.qmd\n+++ b/a.qmd\n"
        "@@ -1,0 +2,1 @@\n+A task, not a method.\n"
    )
    added, deleted = uct.parse_diff(diff)
    assert added == {"a.qmd": {2: "A task, not a method."}}
    assert deleted == set()


def test_defaults_agree_between_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    assert uct._DEFAULT_FAIL is False
    assert "default: 'false'" in action.split("fail:")[1]
    assert uct.DEFAULT_GLOBS == "*.qmd"
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-unexplained-contrasts.yml").read_text(encoding="utf-8")
    assert "default: false" in workflow.split("fail:")[1]
    assert "default: '*.qmd'" in workflow.split("globs:")[1]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", *args], check=True,
                   stdout=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.qmd").write_text("::: {#rem-x}\nA term is a word.\n:::\n")
    _git(tmp_path, "add", "a.qmd")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_check_flags_an_added_contrast(repo):
    (repo / "a.qmd").write_text(
        "::: {#rem-x}\nA term is a word.\nA word, not a phrase.\n:::\n")
    report = uct.run_check("HEAD", ["*.qmd"], [], False)
    assert [(p, f.line) for p, f in report.findings] == [("a.qmd", 3)]


def test_run_check_ignores_an_existing_contrast(repo):
    (repo / "a.qmd").write_text("::: {#rem-x}\nA word, not a phrase.\n:::\n")
    _git(repo, "commit", "-q", "-am", "existing")
    (repo / "a.qmd").write_text(
        "::: {#rem-x}\nA word, not a phrase.\nAnother line.\n:::\n")
    assert uct.run_check("HEAD", ["*.qmd"], [], False).findings == []


def test_run_check_whole_tree_flags_an_existing_contrast(repo):
    (repo / "a.qmd").write_text("::: {#rem-x}\nA word, not a phrase.\n:::\n")
    _git(repo, "commit", "-q", "-am", "existing")
    report = uct.run_check("", ["*.qmd"], [], True)
    assert [(p, f.line) for p, f in report.findings] == [("a.qmd", 2)]


def test_run_check_skips_an_unresolvable_base(repo):
    assert uct.run_check("no-such-ref", ["*.qmd"], [], False).skipped


def test_run_check_skips_an_empty_base(repo):
    assert uct.run_check("", ["*.qmd"], [], False).skipped
