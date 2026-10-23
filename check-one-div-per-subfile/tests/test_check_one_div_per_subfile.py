"""Unit tests for check-one-div-per-subfile.

Covers which divs count (top level only, source remarks excepted, code fences
ignored), which files are subfiles, diff scoping (an untouched subfile is not
reflagged, a touched one is), the skip-not-fallback guard, and the defaults
the action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_one_div_per_subfile", _DIR / "check-one-div-per-subfile.py"
)
assert _spec is not None and _spec.loader is not None
ods = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ods)

SUB = "chapters/_subfiles/ch/_x_exr.qmd"


def extra_lines(text: str, path: str = SUB):
    """Lines of the divs after the first, for a document given as a string."""
    extra, _ = ods.scan_file(text.split("\n"), path)
    return [d.line for d in extra]


# -- is_subfile --------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "chapters/_subfiles/ch/_x_exr.qmd",
    "_subfiles/_def-x.qmd",
    "a/b/_subfiles/_x.qmd",
])
def test_subfile_paths(path):
    assert ods.is_subfile(path)


@pytest.mark.parametrize("path", [
    "chapters/ch.qmd",
    "chapters/_subfiles/ch/x.qmd",
    "chapters/_subfiles/ch/_x.md",
    "chapters/other/_x.qmd",
])
def test_non_subfile_paths(path):
    assert not ods.is_subfile(path)


# -- top_level_divs ----------------------------------------------------------

def test_one_div_is_fine():
    assert extra_lines("::: {#exr-a}\nAsk.\n:::\n") == []


def test_exercise_and_solution_share_a_file():
    doc = "::: {#exr-a}\nAsk.\n:::\n\n::: {#sol-a}\nAnswer.\n:::\n"
    assert extra_lines(doc) == []


@pytest.mark.parametrize("head", [
    "::: proof", "::: {.proof}", "::: {#prf-a}", "::: sol", "::: {.sol}",
    "::: solution", "::: {.solution #x}",
])
def test_proof_or_solution_stays_with_its_claim(head):
    doc = "::: {#thm-a}\nClaim.\n:::\n\n" + head + "\nWhy.\n:::\n"
    assert extra_lines(doc) == []


@pytest.mark.parametrize("head", [
    "::: proofreading", "::: {.solutions-list}", "::: {#prfx-a}",
    "::: {#solid-a}", "::: notes",
    '::: {#exm-a title="a sol"}', "::: {#exm-a title='a proof'}",
])
def test_lookalike_div_still_counts(head):
    doc = "::: {#thm-a}\nClaim.\n:::\n\n" + head + "\nx\n:::\n"
    assert extra_lines(doc) == [5]


def test_second_claim_after_a_proof_still_counts():
    doc = ("::: {#thm-a}\nA.\n:::\n::: proof\nP.\n:::\n"
           "::: {#thm-b}\nB.\n:::\n")
    assert extra_lines(doc) == [7]


def test_nested_div_does_not_count():
    doc = "::::: {#exr-a}\nAsk.\n\n::: solution\nAnswer.\n:::\n:::::\n"
    assert extra_lines(doc) == []


def test_third_div_is_counted_in_the_total():
    doc = "::: {#a}\nx\n:::\n::: {#b}\ny\n:::\n::: {#c}\nz\n:::\n"
    extra, seen = ods.scan_file(doc.split("\n"), SUB)
    assert [d.line for d in extra] == [4, 7] and seen == 3


def test_source_remark_is_exempt():
    doc = "::: {#exm-a}\nx\n:::\n\n::: {#rem-source-a .remark}\nFrom ISL.\n:::\n"
    assert extra_lines(doc) == []


def test_other_remark_is_not_exempt():
    doc = "::: {#exm-a}\nx\n:::\n\n::: {#rem-a .remark}\nNote.\n:::\n"
    assert extra_lines(doc) == [5]


def test_div_in_code_fence_is_ignored():
    doc = "::: {#a}\nx\n:::\n\n```\n::: {#b}\ny\n:::\n```\n"
    assert extra_lines(doc) == []


def test_longer_fence_holding_shorter_one():
    doc = "::: {#a}\nx\n:::\n\n````\n```\n::: {#b}\n```\n````\n"
    assert extra_lines(doc) == []


def test_bare_class_div_counts():
    doc = "::: example\nx\n:::\n::: notes\ny\n:::\n"
    assert extra_lines(doc) == [4]


def test_non_subfile_is_never_flagged():
    doc = "::: {#a}\nx\n:::\n::: {#b}\ny\n:::\n"
    assert extra_lines(doc, "chapters/ch.qmd") == []


def test_unbalanced_closer_is_harmless():
    assert extra_lines(":::\n::: {#a}\nx\n:::\n") == []


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


TWO = "::: {#exr-a}\nAsk.\n:::\n\n::: {#exm-a}\nExample.\n:::\n"


def _write(repo, name, text, stage=True):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if stage:
        _git(repo, "add", name)


def _commit(repo, name, text):
    _write(repo, name, text)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return ods.run_check(base, [ods.DEFAULT_GLOBS], [], False)


def test_untouched_multi_div_subfile_is_grandfathered(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    _write(repo, "_subfiles/_new_exr.qmd", "::: {#exr-b}\nAsk.\n:::\n")
    report = _run("HEAD")
    assert not report.skipped and report.findings == []


def test_new_multi_div_subfile_is_flagged(repo):
    _commit(repo, "x.qmd", "text\n")
    _write(repo, "_subfiles/_new.qmd", TWO)
    report = _run("HEAD")
    assert report.findings == [("_subfiles/_new.qmd", 5, 2)]


def test_touching_a_multi_div_subfile_flags_it(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    _write(repo, "_subfiles/_old.qmd", TWO.replace("Ask.", "Ask again."))
    report = _run("HEAD")
    assert [(f, n) for f, n, _ in report.findings] == [("_subfiles/_old.qmd", 5)]


def test_moved_lines_alone_do_not_flag(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    swapped = "::: {#exm-a}\nExample.\n:::\n\n::: {#exr-a}\nAsk.\n:::\n"
    _write(repo, "_subfiles/_old.qmd", swapped)
    assert _run("HEAD").findings == []


def test_split_into_one_div_files_is_clean(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    _git(repo, "rm", "-q", "_subfiles/_old.qmd")
    _write(repo, "_subfiles/_a_exr.qmd", "::: {#exr-a}\nAsk.\n:::\n")
    _write(repo, "_subfiles/_a_sol.qmd", "::: {#sol-a}\nAnswer.\n:::\n")
    report = _run("HEAD")
    assert report.findings == [] and report.files == 2


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    assert _run("no-such-ref").skipped


def test_whole_tree_flags_every_multi_div_subfile(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    report = ods.run_check("", [ods.DEFAULT_GLOBS], [], True)
    assert not report.skipped
    assert [n for _, n, _ in report.findings] == [5]


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    ignores = ods.compile_ignores(["_subfiles/_old.qmd"])
    assert ods.run_check("", [ods.DEFAULT_GLOBS], ignores, True).findings == []


def test_files_and_divs_are_counted(repo):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    report = ods.run_check("", [ods.DEFAULT_GLOBS], [], True)
    assert (report.files, report.divs) == (1, 2)


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-one-div-per-subfile.yml").read_text(encoding="utf-8")
    assert ods._DEFAULT_FAIL is False
    assert "default: 'false'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: false" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{ods.DEFAULT_GLOBS}'" in action
    assert f"default: '{ods.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"ODS_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "_subfiles/_old.qmd", TWO)
    monkeypatch.setenv("ODS_WHOLE_TREE", "true")
    assert ods.main() == 0
    monkeypatch.setenv("ODS_FAIL", "true")
    assert ods.main() == 1


# -- adversarial inputs ------------------------------------------------------

def test_crlf_line_endings_count_the_same():
    doc = "::: {#exr-a}\r\nAsk.\r\n:::\r\n\r\n::: {#exm-a}\r\nAns.\r\n:::\r\n"
    assert extra_lines(doc) == [5]


def test_tilde_fence_hides_divs():
    assert extra_lines("~~~\n::: {#a}\n:::\n::: {#b}\n:::\n~~~\n") == []


def test_tilde_fence_does_not_close_backtick_fence():
    doc = "```\n~~~\n::: {#a}\n```\n::: {#b}\nx\n:::\n"
    assert extra_lines(doc) == []
    assert ods.top_level_divs(doc.split("\n"))[0].line == 5


def test_fence_inside_a_list_item_hides_divs():
    doc = "- x\n\n    ```\n::: {#a}\n:::\n    ```\n::: {#b}\n:::\n"
    assert ods.top_level_divs(doc.split("\n"))[0].line == 7
    assert extra_lines(doc) == []


def test_divs_in_an_html_comment_are_ignored():
    doc = "<!--\n::: {#a}\n:::\n-->\n::: {#b}\n:::\n::: {#c}\n:::\n"
    assert extra_lines(doc) == [7]
    assert extra_lines("<!-- ::: {#a} -->\n::: {#b}\n:::\n") == []


def test_backtick_opener_with_backtick_info_string_is_not_a_fence():
    doc = "```r``` text\n::: {#a}\nx\n:::\n::: {#b}\ny\n:::\n"
    assert extra_lines(doc) == [5]


def test_tilde_opener_may_hold_backticks_in_info_string():
    doc = "~~~ a`b\n::: {#a}\n:::\n::: {#b}\n:::\n~~~\n"
    assert extra_lines(doc) == []


def test_blockquoted_divs_and_fences_are_ignored():
    doc = "> ::: {#a}\n> x\n> :::\n> ::: {#b}\n> y\n> :::\n"
    assert extra_lines(doc) == []
    doc = "> ```\n::: {#a}\nx\n:::\n::: {#b}\ny\n:::\n"
    assert extra_lines(doc) == [5]


def test_include_shortcode_is_not_a_div():
    doc = "{{< include _x_sol.qmd >}}\n::: {#a}\nx\n:::\n"
    assert ods.top_level_divs(doc.split("\n"))[0].line == 2
    assert extra_lines(doc) == []


def test_unclosed_div_is_unclosed_and_hides_later_divs():
    doc = "::: {#a}\nx\n\n::: {#b}\ny\n:::\n"
    assert not ods.is_balanced(doc.split("\n"))
    assert extra_lines(doc) == []
    assert ods.is_balanced("::: {#a}\nx\n:::\n".split("\n"))


def test_unclosed_code_fence_is_reported():
    doc = "```\n::: {#a}\n:::\n::: {#b}\n:::\n"
    assert not ods.is_balanced(doc.split("\n"))


def test_unclosed_html_comment_is_reported():
    assert not ods.is_balanced("<!--\n::: {#a}\n:::\n".split("\n"))


def test_stray_closer_hides_nothing_and_is_not_reported():
    doc = ":::\n::: {#a}\nx\n:::\n"
    assert ods.is_balanced(doc.split("\n"))


def test_lazy_blockquote_closer_is_not_reported():
    doc = "> ::: {#a}\n> x\n:::\n::: {#b}\n:::\n"
    assert ods.is_balanced(doc.split("\n"))


def test_fenced_divs_do_not_unbalance():
    assert ods.is_balanced("```\n::: {#a}\n```\n".split("\n"))


def test_unbalanced_subfile_is_reported_by_the_run(repo, capsys, monkeypatch):
    _commit(repo, "README.md", "base\n")
    _write(repo, "_subfiles/_bad_exr.qmd", "::: {#exr-a}\nAsk.\n")
    report = _run("HEAD")
    assert report.unbalanced == ("_subfiles/_bad_exr.qmd",)
    monkeypatch.setenv("ODS_BASE_REF", "HEAD")
    assert ods.main() == 0
    assert "never closed" in capsys.readouterr().out
    monkeypatch.setenv("ODS_FAIL", "true")
    assert ods.main() == 1


def test_untouched_unclosed_subfile_is_not_reported(repo):
    _commit(repo, "_subfiles/_bad_exr.qmd", "::: {#exr-a}\nAsk.\n")
    _write(repo, "_subfiles/_ok_exr.qmd", "::: {#exr-b}\nAsk.\n:::\n")
    assert _run("HEAD").unbalanced == ()


def test_balanced_subfile_is_not_reported_unbalanced(repo):
    _commit(repo, "README.md", "base\n")
    _write(repo, "_subfiles/_ok_exr.qmd", "::: {#exr-a}\nAsk.\n:::\n")
    assert _run("HEAD").unbalanced == ()


def test_glob_matches_that_are_not_subfiles_are_counted(repo, capsys,
                                                         monkeypatch):
    _commit(repo, "README.md", "base\n")
    _write(repo, "_subfiles/_ok_exr.qmd", "::: {#exr-a}\nAsk.\n:::\n")
    _write(repo, "_subfiles/plain.qmd", TWO)
    report = ods.run_check("HEAD", ["_subfiles/*.qmd"], [], False)
    assert (report.files, report.dropped) == (1, 1)
    assert report.findings == []
    monkeypatch.setenv("ODS_BASE_REF", "HEAD")
    monkeypatch.setenv("ODS_GLOBS", "_subfiles/*.qmd")
    ods.main()
    assert "not subfiles" in capsys.readouterr().out


def test_default_glob_drops_nothing(repo):
    _commit(repo, "README.md", "base\n")
    _write(repo, "_subfiles/_ok_exr.qmd", "::: {#exr-a}\nAsk.\n:::\n")
    assert _run("HEAD").dropped == 0


# -- HTML comments -----------------------------------------------------------

def test_comment_marker_in_a_code_span_is_prose():
    doc = "Use `<!--` to open.\n::: {#a}\nx\n:::\n::: {#b}\ny\n:::\n"
    assert ods.is_balanced(doc.split("\n"))
    assert extra_lines(doc) == [5]


def test_second_comment_on_a_line_stays_open():
    doc = "<!-- a --> <!-- b\n::: {#a}\n:::\n-->\n::: {#b}\n:::\n::: {#c}\n:::\n"
    assert [d.line for d in ods.top_level_divs(doc.split("\n"))] == [5, 7]


def test_text_after_a_closing_marker_is_kept():
    doc = "<!--\nx\n--> ::: {#a}\nx\n:::\n::: {#b}\ny\n:::\n"
    assert [d.line for d in ods.top_level_divs(doc.split("\n"))] == [3, 6]


def test_div_opener_before_a_comment_is_kept():
    doc = "::: {#a} <!-- c\nx\n-->\n:::\n::: {#b}\ny\n:::\n"
    assert [d.line for d in ods.top_level_divs(doc.split("\n"))] == [1, 5]
