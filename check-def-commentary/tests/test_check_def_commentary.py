"""Unit tests for check-def-commentary (gha#1180).

The regression case is Ezra's sds#444 review comment: commentary ("It is not
the expected squared prediction error.") written inside a ``#def-`` div.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import subprocess

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_def_commentary", _DIR / "check-def-commentary.py"
)
assert _spec is not None and _spec.loader is not None
dcm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dcm)


def hits(text: str):
    return [(f.line, f.phrase) for f in dcm.scan_definitions(text.split("\n"))]


SDS_444 = """::: {#def-prediction-bias}
## Prediction bias

The **bias** is the expected signed prediction error.

$$
\\text{bias} = E[y - \\hat{y}]
$$

The bias is signed, not squared. It is not the expected squared prediction error.
:::"""


def test_regression_sds_444_sentence_is_flagged():
    assert hits(SDS_444) == [(10, "It is not")]


@pytest.mark.parametrize("phrase", [
    "It is not", "This is not", "That is not", "Note that", "Notice that",
    "Unlike", "Do not confuse", "Don't confuse", "Be careful", "Beware",
    "In contrast", "By contrast", "Intuitively", "Informally", "Historically",
])
def test_each_starter_is_flagged(phrase):
    text = f"::: {{#def-x}}\nA thing is a thing. {phrase} the other thing.\n:::"
    assert hits(text) == [(2, phrase)]


def test_starter_at_line_start():
    assert hits("::: {#def-x}\nNote that this holds.\n:::") == [(2, "Note that")]


def test_definition_sentence_is_not_flagged():
    assert hits("::: {#def-x}\nThe **bias** is the expected signed error.\n:::") == []


def test_commentary_outside_a_definition_is_fine():
    assert hits("::: {#rem-x}\nIt is not the squared error.\n:::") == []
    assert hits("Note that this is a paragraph.") == []


def test_commentary_in_theorem_is_fine():
    assert hits("::: {#thm-x}\nNote that this holds.\n:::") == []


def test_allow_marker_exempts_the_line():
    text = "::: {#def-x}\nIt is not empty. <!-- check-def-commentary: allow -->\n:::"
    assert hits(text) == []


def test_code_fence_math_and_comment_are_skipped():
    text = "\n".join([
        "::: {#def-x}",
        "```r",
        "Note that this is code",
        "```",
        "$$",
        "Note that this is math",
        "$$",
        "<!-- Note that this is a comment -->",
        ":::",
    ])
    assert hits(text) == []


def test_inline_code_is_ignored():
    assert hits("::: {#def-x}\nUse `Note that` literally.\n:::") == []


def test_nested_non_definition_div_is_not_read():
    text = "::: {#def-x}\nA thing.\n::: {.callout-note}\nNote that this is a callout.\n:::\n:::"
    assert hits(text) == []


def test_a_word_inside_a_sentence_is_not_a_starter():
    assert hits("::: {#def-x}\nThe value is unlike zero.\n:::") == []


def test_parse_diff_scopes_to_added_lines():
    diff = (
        "diff --git a/a.qmd b/a.qmd\n--- a/a.qmd\n+++ b/a.qmd\n"
        "@@ -1,0 +2,1 @@\n+Note that this is new.\n"
    )
    added, deleted = dcm.parse_diff(diff)
    assert added == {"a.qmd": {2: "Note that this is new."}}
    assert deleted == set()


def test_defaults_agree_between_script_and_action():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    assert dcm._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("fail:")[1]
    assert dcm.DEFAULT_GLOBS == "*.qmd"
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-def-commentary.yml").read_text(encoding="utf-8")
    assert "default: true" in workflow.split("fail:")[1]
    assert "default: '*.qmd'" in workflow.split("globs:")[1]


def test_starter_after_bold_markup_is_not_flagged():
    # Known limit: a starter after bold markup is not at a sentence start.
    assert hits("::: {#def-x}\n**Term.** Note that this holds.\n:::") == []


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", *args], check=True,
                   stdout=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.qmd").write_text("::: {#def-x}\nA term is a word.\n:::\n")
    _git(tmp_path, "add", "a.qmd")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_check_flags_added_commentary(repo):
    (repo / "a.qmd").write_text(
        "::: {#def-x}\nA term is a word.\nIt is not a phrase.\n:::\n")
    report = dcm.run_check("HEAD", ["*.qmd"], [], False)
    assert [(p, f.line) for p, f in report.findings] == [("a.qmd", 3)]


def test_run_check_exempts_a_moved_line(repo):
    (repo / "a.qmd").write_text("::: {#def-x}\nIt is not a phrase.\n:::\n")
    _git(repo, "commit", "-q", "-am", "commentary")
    (repo / "a.qmd").write_text(
        "::: {#def-x}\nA term is a word.\nIt is not a phrase.\n:::\n")
    assert dcm.run_check("HEAD", ["*.qmd"], [], False).findings == []


def test_run_check_skips_an_unresolvable_base(repo):
    assert dcm.run_check("no-such-ref", ["*.qmd"], [], False).skipped


def test_run_check_skips_an_empty_base(repo):
    assert dcm.run_check("", ["*.qmd"], [], False).skipped
