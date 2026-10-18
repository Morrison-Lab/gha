"""Unit tests for check-wikipedia-further-reading.

Covers the reading-context rules (heading, `.reading` div, filename), what is
not flagged (prose citations, other sections), diff scoping (moved lines are
not reflagged), the skip-not-fallback guard, and the defaults the action, the
reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_wikipedia_further_reading", _DIR / "check-wikipedia-further-reading.py"
)
assert _spec is not None and _spec.loader is not None
wfr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wfr)


def flagged(text: str, path: str = "chapter.qmd"):
    """Line numbers of flagged items for a document given as one string."""
    findings, _ = wfr.scan_file(text.split("\n"), path)
    return [f.line for f in findings]


# -- scan_file ---------------------------------------------------------------

def test_wikipedia_citation_bullet_under_further_reading_is_flagged():
    doc = "## Further reading {.unnumbered}\n\n-   @wikipedia_bayes_theorem --- the theorem\n"
    assert flagged(doc) == [3]


def test_wikipedia_link_autolink_and_wikipedia_on_are_flagged():
    doc = "\n".join([
        "## Further reading",
        "- [wikipedia](https://en.wikipedia.org/wiki/Dot_product)",
        "* <https://en.wikipedia.org/wiki/Slope>",
        "1. Wikipedia on the slope of a line",
        "- @hoggtanis2015 [Sec. 9.3]",
    ])
    assert flagged(doc) == [2, 3, 4]


def test_bracketed_citation_in_a_reading_item_is_flagged():
    doc = "## Additional reading\n- See [@wikipedia_slope] for pictures\n"
    assert flagged(doc) == [2]


def test_prose_citation_is_not_flagged():
    doc = (
        "## Slope\n\nThe slope is rise over run [@wikipedia_slope].\n\n"
        "- a list item citing [@wikipedia_slope] outside any reading section\n"
    )
    assert flagged(doc) == []


def test_prose_paragraph_inside_further_reading_is_not_a_list_item():
    doc = "## Further reading\n\nSee [@wikipedia_slope] in the text.\n"
    assert flagged(doc) == []


@pytest.mark.parametrize("heading", [
    "Further reading", "Online references", "Going further",
    "Additional reading", "Learn more", "Reading", "Suggested Reading",
    "### Further Reading".lstrip("# "),
])
def test_heading_variants_open_a_reading_context(heading):
    assert flagged(f"## {heading}\n- @wikipedia_x\n") == [2]


def test_unrelated_heading_does_not_open_a_context():
    assert flagged("## Spreading\n- @wikipedia_x\n") == []
    assert flagged("## Exercises\n- @wikipedia_x\n") == []


def test_next_heading_resets_the_context():
    doc = "\n".join([
        "## Further reading",
        "- @hoggtanis2015",
        "",
        "## Exercises",
        "- @wikipedia_slope",
        "",
        "### Learn more",
        "- @wikipedia_logarithm",
    ])
    assert flagged(doc) == [8]


def test_heading_in_code_fence_is_ignored():
    doc = "## Further reading\n```\n## Exercises\n```\n- @wikipedia_x\n"
    assert flagged(doc) == [5]


def test_wikipedia_in_code_fence_is_ignored():
    doc = "## Further reading\n```\n- @wikipedia_x\n```\n"
    assert flagged(doc) == []


def test_reading_div_is_a_context():
    doc = "::: {.reading}\n- @wikipedia_x\n:::\n\n- @wikipedia_y\n"
    assert flagged(doc) == [2]


def test_nested_div_closing_keeps_outer_reading_context():
    doc = "::: {.reading}\n::: {.callout-note}\ntext\n:::\n- @wikipedia_x\n:::\n"
    assert flagged(doc) == [5]


@pytest.mark.parametrize("path", [
    "_subfiles/m/_prose-further-reading.qmd", "_subfiles/m/_sec-reading.qmd",
    "chapters/sec-reading-x.md",
])
def test_reading_subfile_name_flags_without_a_heading(path):
    assert flagged("- @wikipedia_slope --- slopes\n", path) == [1]


def test_other_subfile_names_do_not_flag_without_a_heading():
    assert flagged("- @wikipedia_slope --- slopes\n", "_subfiles/m/_note.qmd") == []


def test_filename_rule_uses_the_basename_only():
    assert flagged("- @wikipedia_x\n", "further-reading/notes.qmd") == []


def test_continuation_line_belongs_to_the_item():
    doc = "## Further reading\n- A good text\n  see https://en.wikipedia.org/wiki/X\n- Another\n"
    findings, _ = wfr.scan_file(doc.split("\n"), "c.qmd")
    assert [f.line for f in findings] == [2]


def test_items_examined_are_counted():
    doc = "## Further reading\n- a\n- @wikipedia_x\n## Other\n- b\n"
    _, seen = wfr.scan_file(doc.split("\n"), "c.qmd")
    assert seen == 2


# -- select_findings (diff scoping) -----------------------------------------

def test_only_added_lines_are_reported():
    items, _ = wfr.scan_items(
        "## Further reading\n- @wikipedia_a\n- @wikipedia_b\n".split("\n"), "c.qmd")
    assert wfr.select_findings(items, {3}) == [(3, "@wikipedia_b")]
    assert wfr.select_findings(items, set()) == []
    assert [n for n, _ in wfr.select_findings(items, None)] == [2, 3]


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


def _commit(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return wfr.run_check(base, ["*.qmd", "*.md"], [], False)


def test_preexisting_entries_are_not_reflagged(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_old\n")
    (repo / "a.qmd").write_text(
        "## Further reading\n- @wikipedia_old\n- @hoggtanis2015\n", encoding="utf-8")
    _git(repo, "add", "a.qmd")
    report = _run("HEAD")
    assert not report.skipped
    assert report.findings == []


def test_added_entry_is_flagged(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @hoggtanis2015\n")
    (repo / "a.qmd").write_text(
        "## Further reading\n- @hoggtanis2015\n- @wikipedia_new\n", encoding="utf-8")
    _git(repo, "add", "a.qmd")
    report = _run("HEAD")
    assert [(f, n) for f, n, _ in report.findings] == [("a.qmd", 3)]


def test_moved_line_is_not_reflagged(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_a\n- @wikipedia_b\n")
    (repo / "a.qmd").write_text(
        "## Further reading\n- @wikipedia_b\n- @wikipedia_a\n", encoding="utf-8")
    _git(repo, "add", "a.qmd")
    assert _run("HEAD").findings == []


def test_item_moved_between_files_is_not_reflagged(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_a\n")
    _commit(repo, "b.qmd", "## Intro\ntext\n")
    (repo / "a.qmd").write_text("## Further reading\n", encoding="utf-8")
    (repo / "b.qmd").write_text("## Further reading\n- @wikipedia_a\n", encoding="utf-8")
    _git(repo, "add", "a.qmd", "b.qmd")
    assert _run("HEAD").findings == []


def test_new_subfile_with_reading_name_is_flagged(repo):
    _commit(repo, "x.qmd", "text\n")
    sub = repo / "_subfiles"
    sub.mkdir()
    (sub / "_prose-further-reading.qmd").write_text("- @wikipedia_a\n", encoding="utf-8")
    _git(repo, "add", "_subfiles/_prose-further-reading.qmd")
    report = _run("HEAD")
    assert [(f, n) for f, n, _ in report.findings] == [
        ("_subfiles/_prose-further-reading.qmd", 1)]


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_old\n")
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_old\n")
    assert _run("no-such-ref").skipped


def test_whole_tree_flags_every_line(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_old\n")
    report = wfr.run_check("", ["*.qmd", "*.md"], [], True)
    assert not report.skipped
    assert [n for _, n, _ in report.findings] == [2]


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_old\n")
    ignores = wfr.compile_ignores(["a.qmd"])
    assert wfr.run_check("", ["*.qmd"], ignores, True).findings == []


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-wikipedia-further-reading.yml").read_text(encoding="utf-8")
    assert wfr._DEFAULT_FAIL is True
    assert wfr.DEFAULT_GLOBS == "*.qmd *.md"
    assert "default: 'true'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: true" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{wfr.DEFAULT_GLOBS}'" in action
    assert f"default: '{wfr.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"WFR_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "a.qmd", "## Further reading\n- @wikipedia_old\n")
    monkeypatch.setenv("WFR_WHOLE_TREE", "true")
    assert wfr.main() == 1
    monkeypatch.setenv("WFR_FAIL", "false")
    assert wfr.main() == 0
