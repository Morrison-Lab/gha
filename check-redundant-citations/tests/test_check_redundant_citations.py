"""Unit tests for check-redundant-citations.

Covers what counts as a repeat (the same key and locator twice in one div or
passage, including a ``Source:`` line), what is not flagged (a different
locator, an in-text citation, different list items, cross-references, code),
diff scoping, the skip-not-fallback guard, and the defaults the action, the
reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_redundant_citations", _DIR / "check-redundant-citations.py"
)
assert _spec is not None and _spec.loader is not None
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def flagged(text: str):
    """``(line, key)`` of each repeat for a document given as one string."""
    findings, _ = rc.scan_file(text.split("\n"))
    return [(f.line, f.key) for f in findings]


# -- What is flagged ---------------------------------------------------------

def test_inline_citation_repeated_in_source_line():
    text = (
        "::: {#def-bias}\n"
        "The bias is the expected error [@wiki_bias]:\n"
        "\n"
        "Source: @wiki_bias.\n"
        ":::\n"
    )
    assert flagged(text) == [(4, "wiki_bias")]


def test_two_brackets_same_key_same_locator():
    text = "::: {#exm-a}\nOne claim [@james, p. 5].\nAnother [@james, p. 5].\n:::\n"
    assert flagged(text) == [(3, "james")]


def test_same_key_no_locator_twice():
    assert flagged("Claim one [@james]. Claim two [@james].") == [(1, "james")]


def test_multi_key_bracket_counts_each_key():
    text = "A [@a; @b].\nB [@b].\n"
    assert flagged(text) == [(2, "b")]


def test_text_after_a_comma_is_a_locator_not_a_key():
    text = "A [@b, @c].\nB [@c].\n"
    assert flagged(text) == []


def test_citation_spanning_lines():
    text = "First [@james,\np. 5].\nSecond [@james, p. 5].\n"
    assert flagged(text) == [(3, "james")]


def test_source_line_lists_key_twice_with_bracket():
    text = "::: {#def-a}\nSee [@k].\nSource: @k; @other.\n:::\n"
    assert flagged(text) == [(3, "k")]


# -- What is not flagged -----------------------------------------------------

def test_different_locators_are_not_a_repeat():
    text = "A [@james, p. 5].\nB [@james, p. 9].\n"
    assert flagged(text) == []


def test_in_text_citation_is_not_counted():
    text = "Studies [@james] agree.\n@james recommend this.\n"
    assert flagged(text) == []


def test_different_divs_are_separate_blocks():
    text = "::: {#def-a}\nA [@k].\n:::\n\n::: {#def-b}\nB [@k].\n:::\n"
    assert flagged(text) == []


def test_slidebreak_separates_blocks():
    text = "A [@k].\n\n{{< slidebreak >}}\n\nB [@k].\n"
    assert flagged(text) == []


def test_different_list_items_are_separate_claims():
    text = "- first video [@talk]\n- second video [@talk]\n"
    assert flagged(text) == []


def test_cross_references_are_ignored():
    text = "See [@def-a] and [@def-a], also [@eq-x] [@eq-x].\n"
    assert flagged(text) == []


def test_code_fences_and_chunk_options_are_ignored():
    text = (
        "```{r}\n"
        "x <- c(@k, @k) # [@k] [@k]\n"
        "```\n"
        "```{python}\n"
        "#| label: [@k] [@k]\n"
        "```\n"
    )
    assert flagged(text) == []


def test_nested_link_brackets_do_not_break_matching():
    text = "A [see [the text](url) @k].\nB [@k].\n"
    assert flagged(text) == [(2, "k")]


# -- Counting ----------------------------------------------------------------

def test_blocks_examined_counts_only_blocks_with_a_citation():
    _, n = rc.scan_file(
        ["::: {#a}", "no cite", ":::", "::: {#b}", "x [@k]", ":::"])
    assert n == 1


# -- Diff scoping ------------------------------------------------------------

def test_select_findings_keeps_repeat_or_first_on_added_line():
    f = rc.Finding(line=10, key="k", locator="", first_line=3)
    assert rc.select_findings([f], {10}) == [f]
    assert rc.select_findings([f], {3}) == [f]
    assert rc.select_findings([f], {7}) == []
    assert rc.select_findings([f], None) == [f]


def test_parse_diff_collects_added_and_deleted():
    diff = (
        "diff --git a/a.qmd b/a.qmd\n"
        "--- a/a.qmd\n"
        "+++ b/a.qmd\n"
        "@@ -2,1 +2,2 @@\n"
        "-old [@k]\n"
        "+new [@k]\n"
        "+added\n"
    )
    added, deleted = rc.parse_diff(diff)
    assert added == {"a.qmd": {2: "new [@k]", 3: "added"}}
    assert deleted == {"old [@k]"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_run_check_flags_only_repeats_the_diff_touches(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    page = tmp_path / "page.qmd"
    page.write_text("::: {#def-old}\nA [@k].\nB [@k].\n:::\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "base")
    page.write_text(
        "::: {#def-old}\nA [@k].\nB [@k].\n:::\n\n::: {#def-new}\nC [@j].\nD [@j].\n:::\n")
    monkeypatch.chdir(tmp_path)
    report = rc.run_check("HEAD", ["*.qmd"], [], whole_tree=False)
    assert not report.skipped
    assert [(f.key, f.line) for _p, f in report.findings] == [("j", 8)]
    whole = rc.run_check("", ["*.qmd"], [], whole_tree=True)
    assert sorted(f.key for _p, f in whole.findings) == ["j", "k"]


def test_run_check_skips_without_a_base_ref(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    monkeypatch.chdir(tmp_path)
    assert rc.run_check("", ["*.qmd"], [], whole_tree=False).skipped


# -- Defaults the action, workflow and script agree on -----------------------

def test_script_is_warn_only_by_default():
    assert rc._DEFAULT_FAIL is False


def test_action_and_workflow_default_to_warn_only():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-redundant-citations.yml").read_text()
    for text in (action, workflow):
        fail_block = text.split("fail:", 1)[1]
        assert "default: 'false'" in fail_block or "default: false" in fail_block


@pytest.mark.parametrize("name", ["RC_BASE_REF", "RC_GLOBS", "RC_PATHS_IGNORE",
                                  "RC_FAIL", "RC_WHOLE_TREE"])
def test_action_passes_every_environment_variable(name):
    assert name in (_DIR / "action.yml").read_text()
