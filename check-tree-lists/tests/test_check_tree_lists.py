"""Unit tests for check-tree-lists.

Covers which divs are checked, what counts as a tree mention, nested-list depth,
what counts as a figure, the exemption comment and its reason, diff scoping (an
untouched div is not reflagged, a touched one is), the skip-not-fallback guard,
and the defaults the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_tree_lists", _DIR / "check-tree-lists.py"
)
assert _spec is not None and _spec.loader is not None
tls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tls)

TREE_LIST = (
    "::: {#exm-parse-tree}\n"
    "The parse tree of the expression is:\n"
    "\n"
    "- the root $+$, whose children are\n"
    "    - the node $\\times$, whose children are\n"
    "        - the leaves $a$ and $x$,\n"
    "    - the leaf $c$.\n"
    ":::\n"
)


def flagged(text: str):
    """Opening lines of the flagged divs, for a document string."""
    found, _ = tls.scan_file(text.split("\n"), None)
    return [d.start for d in found]


# -- what is flagged ---------------------------------------------------------

def test_tree_as_three_level_list_is_flagged():
    assert flagged(TREE_LIST) == [1]


def test_two_level_list_is_not_flagged():
    text = (
        "::: {#exm-a}\nA tree:\n\n- root\n    - child\n:::\n"
    )
    assert flagged(text) == []


def test_three_level_list_without_a_tree_mention_is_not_flagged():
    text = (
        "::: {#exm-a}\nAn outline:\n\n- one\n    - two\n        - three\n:::\n"
    )
    assert flagged(text) == []


@pytest.mark.parametrize("word", ["tree", "Trees", "dendrogram"])
def test_tree_words(word):
    text = f"::: {{#def-a}}\nA {word} follows.\n\n- a\n  - b\n    - c\n:::\n"
    assert flagged(text) == [1]


def test_word_containing_tree_is_not_a_mention():
    text = "::: {#def-a}\nThe street.\n\n- a\n  - b\n    - c\n:::\n"
    assert flagged(text) == []


@pytest.mark.parametrize("prefix", ["def", "exm", "thm", "lem", "cor", "prp", "rem", "exr"])
def test_checked_div_kinds(prefix):
    text = f"::: {{#{prefix}-a}}\nA tree.\n\n- a\n  - b\n    - c\n:::\n"
    assert flagged(text) == [1]


def test_unlabelled_div_is_not_checked():
    text = "::: remark\nA tree.\n\n- a\n  - b\n    - c\n:::\n"
    assert flagged(text) == []


def test_numbered_items_count_as_list_items():
    text = "::: {#exm-a}\nA tree.\n\n1. a\n   - b\n      - c\n:::\n"
    assert flagged(text) == [1]


def test_list_in_a_code_fence_is_not_counted():
    text = (
        "::: {#exm-a}\nA tree.\n\n```\n- a\n  - b\n    - c\n```\n:::\n"
    )
    assert flagged(text) == []


def test_div_in_a_code_fence_or_comment_is_not_checked():
    fenced = "```\n" + TREE_LIST + "```\n"
    assert flagged(fenced) == []
    assert flagged("<!--\n" + TREE_LIST + "-->\n") == []


# -- what counts as a figure -------------------------------------------------

@pytest.mark.parametrize("figure", [
    "![A tree](images/tree.png)",
    '<img src="a.png" alt="tree">',
    "::: {#fig-a}\nplot\n:::",
    "```{r}\n#| label: fig-tree\nplot(1)\n```",
    "See @fig-tree.",
    "{{< include _subfiles/ch/_tree_fig.qmd >}}",
])
def test_figure_clears_the_list(figure):
    text = TREE_LIST.replace("is:\n", f"is:\n\n{figure}\n")
    assert flagged(text) == []


# -- exemption ---------------------------------------------------------------

def test_exemption_with_a_reason_clears_the_list():
    text = TREE_LIST.replace(
        "is:\n", "is:\n<!-- no-tree-figure: the list is the point -->\n"
    )
    assert flagged(text) == []


def test_exemption_without_a_reason_does_not():
    text = TREE_LIST.replace("is:\n", "is:\n<!-- no-tree-figure: -->\n")
    assert flagged(text) == [1]


# -- diff scoping ------------------------------------------------------------

def test_untouched_div_is_not_reflagged():
    lines = TREE_LIST.split("\n")
    found, _ = tls.scan_file(lines, {99})
    assert found == []


def test_touched_div_is_flagged():
    lines = TREE_LIST.split("\n")
    found, _ = tls.scan_file(lines, {5})
    assert [d.start for d in found] == [1]


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_check_flags_only_added_lines(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / "old.qmd").write_text(TREE_LIST)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "new.qmd").write_text(TREE_LIST)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "head")
    report = tls.run_check("HEAD^1", ["*.qmd"], [], False)
    assert [f[0] for f in report.findings] == ["new.qmd"]
    assert not report.skipped


def test_whole_tree_flags_every_file(tmp_path, monkeypatch):
    repo = _repo(tmp_path, monkeypatch)
    (repo / "old.qmd").write_text(TREE_LIST)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    report = tls.run_check("", ["*.qmd"], [], True)
    assert [f[0] for f in report.findings] == ["old.qmd"]


def test_no_base_ref_skips(tmp_path, monkeypatch):
    _repo(tmp_path, monkeypatch)
    report = tls.run_check("", ["*.qmd"], [], False)
    assert report.skipped


# -- defaults agree across action, workflow and script ----------------------

def test_defaults_agree():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-tree-lists.yml").read_text()
    assert tls._DEFAULT_FAIL is True
    assert "TLS_FAIL: ${{ inputs.fail }}" in action
    assert "default: 'true'" in action
    assert "default: true" in workflow
    assert "Morrison-Lab/gha/check-tree-lists@v3" in workflow
