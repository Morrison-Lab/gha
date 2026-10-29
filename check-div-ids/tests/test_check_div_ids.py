"""Unit tests for check-div-ids.

Covers which divs are flagged (a theorem-type class without its id prefix),
what is left alone (right id, other classes, code fences, comments,
blockquotes), diff scoping, the skip-not-fallback guard, and the defaults the
action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_div_ids", _DIR / "check-div-ids.py"
)
assert _spec is not None and _spec.loader is not None
cdi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cdi)


def flagged(text: str):
    """(line, class, prefix) of each flagged div in a document string."""
    found, _ = cdi.scan(text.split("\n"))
    return [(f.line, f.cls, f.prefix) for f in found]


# -- missing_prefix ----------------------------------------------------------

@pytest.mark.parametrize("attrs, expected", [
    ("{.remark .notes}", ("remark", "rem")),
    ("{.remark}", ("remark", "rem")),
    ("remark", None),
    ("{.theorem #lem-a}", ("theorem", "thm")),
    ("{.definition}", ("definition", "def")),
    ("{.lemma}", ("lemma", "lem")),
    ("{.corollary}", ("corollary", "cor")),
    ("{.proposition}", ("proposition", "prp")),
    ("{.example}", ("example", "exm")),
    ("{.exercise}", ("exercise", "exr")),
])
def test_missing_prefix(attrs, expected):
    assert cdi.missing_prefix(attrs) == expected or (
        expected is None and cdi.missing_prefix(attrs) is None)


@pytest.mark.parametrize("attrs", [
    "{#rem-a .remark}",
    "{#rem-a .remark .notes}",
    "{.remark .notes #rem-mixed-selection}",
    "{#thm-a .theorem}",
    "{#def-a}",
    "{.proof}",
    "{.notes}",
    "{.callout-note}",
    "{.remarkable}",
    "{#exm-a title=\"a .remark\"}",
])
def test_no_finding(attrs):
    assert cdi.missing_prefix(attrs) is None


def test_quoted_class_text_is_not_a_class():
    assert cdi.missing_prefix("{#thm-a title='the .remark'}") is None


def test_wrong_prefix_is_flagged():
    assert cdi.missing_prefix("{#lem-a .theorem}") == ("theorem", "thm")


# -- scan --------------------------------------------------------------------

def test_hoeffding_shape_is_flagged():
    doc = "text\n\n::: {.remark .notes}\n\nNote.\n\n:::\n"
    assert flagged(doc) == [(3, "remark", "rem")]


def test_good_div_is_clean():
    assert flagged("::: {#rem-a .remark}\nNote.\n:::\n") == []


def test_nested_div_is_checked_too():
    doc = "::::: {#thm-a}\nx\n\n::: {.remark}\ny\n:::\n:::::\n"
    assert flagged(doc) == [(4, "remark", "rem")]


def test_div_in_code_fence_is_ignored():
    assert flagged("```\n::: {.remark}\n:::\n```\n") == []


def test_div_in_html_comment_is_ignored():
    assert flagged("<!--\n::: {.remark}\n:::\n-->\n") == []
    assert flagged("<!-- ::: {.remark} -->\n") == []


def test_blockquoted_div_is_ignored():
    assert flagged("> ::: {.remark}\n> x\n> :::\n") == []


def test_closer_is_not_a_div():
    assert flagged("::: {#rem-a}\nx\n:::\n") == []


def test_divs_examined_are_counted():
    _, seen = cdi.scan("::: {#a}\n::: {.remark}\n:::\n:::\n".split("\n"))
    assert seen == 2


def test_crlf_endings():
    assert flagged("::: {.remark}\r\nx\r\n:::\r\n") == [(1, "remark", "rem")]


# -- git: diff scoping end to end --------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    _git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


BAD = "::: {.remark .notes}\nNote.\n:::\n"


def _write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _commit(repo, name, text):
    _write(repo, name, text)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return cdi.run_check(base, [cdi.DEFAULT_GLOBS], [], False)


def test_existing_bad_div_is_grandfathered(repo):
    _commit(repo, "old.qmd", BAD + "\nTail.\n")
    _write(repo, "old.qmd", BAD + "\nTail changed.\n")
    report = _run("HEAD")
    assert not report.skipped and report.findings == []


def test_added_bad_div_is_flagged(repo):
    _commit(repo, "a.qmd", "text\n")
    _write(repo, "b.qmd", "intro\n\n" + BAD)
    report = _run("HEAD")
    assert [(p, f.line) for p, f in report.findings] == [("b.qmd", 3)]


def test_moved_bad_div_is_not_flagged(repo):
    _commit(repo, "a.qmd", BAD + "\nTail.\n")
    _write(repo, "a.qmd", "Tail.\n\n" + BAD)
    assert _run("HEAD").findings == []


def test_fixing_the_div_is_clean(repo):
    _commit(repo, "a.qmd", BAD)
    _write(repo, "a.qmd", "::: {#rem-a .remark .notes}\nNote.\n:::\n")
    assert _run("HEAD").findings == []


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "a.qmd", BAD)
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "a.qmd", BAD)
    assert _run("no-such-ref").skipped


def test_whole_tree_flags_existing(repo):
    _commit(repo, "a.qmd", BAD)
    report = cdi.run_check("", [cdi.DEFAULT_GLOBS], [], True)
    assert not report.skipped and len(report.findings) == 1


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "a.qmd", BAD)
    ignores = cdi.compile_ignores(["a.qmd"])
    assert cdi.run_check("", [cdi.DEFAULT_GLOBS], ignores, True).findings == []


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-div-ids.yml").read_text(encoding="utf-8")
    assert cdi._DEFAULT_FAIL is False
    assert "default: 'false'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: false" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{cdi.DEFAULT_GLOBS}'" in action
    assert f"default: '{cdi.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CDI_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "a.qmd", BAD)
    monkeypatch.setenv("CDI_WHOLE_TREE", "true")
    assert cdi.main() == 0
    monkeypatch.setenv("CDI_FAIL", "true")
    assert cdi.main() == 1
