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


def test_exercise_and_solution_are_two_divs():
    doc = "::: {#exr-a}\nAsk.\n:::\n\n::: {#sol-a}\nAnswer.\n:::\n"
    assert extra_lines(doc) == [5]


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
    doc = "::: solution\nx\n:::\n::: notes\ny\n:::\n"
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


TWO = "::: {#exr-a}\nAsk.\n:::\n\n::: {#sol-a}\nAnswer.\n:::\n"


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
    swapped = "::: {#sol-a}\nAnswer.\n:::\n\n::: {#exr-a}\nAsk.\n:::\n"
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
