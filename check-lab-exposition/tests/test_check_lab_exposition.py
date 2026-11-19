"""Unit tests for check-lab-exposition.

Covers which divs count as exposition, code fences, the exemption comment and
its reason and where its search stops, include following (nested, escaped, through
an ignored or exempted include, and a lab page's own content
against a page that is not a lab), diff scoping (an untouched div is not
reflagged, an added div or an added include of one is, a moved line is not),
the skip-not-fallback guard, the exit codes, and the defaults the action, the
reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_lab_exposition", _DIR / "check-lab-exposition.py"
)
assert _spec is not None and _spec.loader is not None
cle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cle)

PATTERN = cle.div_re(cle.DEFAULT_PREFIXES.split())


def divs(text: str):
    return [d for _, d in cle.scan_lines(text.split("\n"), PATTERN).divs]


# -- which divs count ---------------------------------------------------------

@pytest.mark.parametrize("prefix", ["def", "thm", "lem", "prp", "cor", "cnj", "rem"])
def test_exposition_prefixes_are_found(prefix):
    assert divs(f"::: {{#{prefix}-a}}\nText.\n:::\n") == [f"{prefix}-a"]


@pytest.mark.parametrize("prefix", ["exr", "sol", "exm", "fig", "tbl", "sec"])
def test_other_prefixes_are_not_exposition(prefix):
    assert divs(f"::: {{#{prefix}-a}}\nText.\n:::\n") == []


def test_classes_before_the_id_and_longer_fences_count():
    assert divs(":::: {.callout #def-b}\nText.\n::::\n") == ["def-b"]


def test_div_in_a_code_fence_is_not_exposition():
    assert divs("````markdown\n::: {#def-a}\nText.\n:::\n````\n") == []


def test_fence_closes_only_on_a_matching_run():
    doc = "````\n```\n::: {#def-a}\n````\n::: {#def-b}\n"
    assert divs(doc) == ["def-b"]


# -- exemptions ---------------------------------------------------------------

def test_exemption_with_a_reason_on_a_later_line():
    lines = ["::: {#rem-a}", "", "#### Title", "<!-- lab-exposition-ok: points to the sds lab -->"]
    assert cle.exempt(lines, 1)


def test_exemption_without_a_reason_does_not_count():
    lines = ["::: {#rem-a}", "<!-- lab-exposition-ok: -->"]
    assert not cle.exempt(lines, 1)


def test_exemption_too_far_below_does_not_count():
    lines = ["::: {#rem-a}", "a", "b", "c", "<!-- lab-exposition-ok: reason -->"]
    assert not cle.exempt(lines, 1)


# -- the repository-level runs -----------------------------------------------

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow
    git(tmp_path, "config", "user.name", "t")
    sub = tmp_path / "ch" / "_subfiles"
    sub.mkdir(parents=True)
    (sub / "_def-old.qmd").write_text("::: {#def-old}\nOld.\n:::\n")
    (sub / "_exr-a.qmd").write_text("::: {#exr-a}\nFit it.\n:::\n")
    (sub / "_wrap.qmd").write_text("{{< include _subfiles/_def-old.qmd >}}\n")
    (tmp_path / "ch" / "fit-lab.qmd").write_text(
        "# Lab\n\n{{< include _subfiles/_exr-a.qmd >}}\n\n"
        "{{< include _subfiles/_def-old.qmd >}}\n")
    (tmp_path / "ch" / "theory.qmd").write_text("::: {#thm-t}\nT.\n:::\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(base_ref="", whole_tree=False, ignores=None):
    return cle.run_check(base_ref, ["*-lab.qmd"], cle.DEFAULT_PREFIXES.split(),
                         ignores or [], whole_tree)


def test_whole_tree_reports_existing_divs_in_included_files(repo):
    report = run(whole_tree=True)
    assert [(f.path, f.what) for f in report.findings] == [("ch/_subfiles/_def-old.qmd", "#def-old")]
    assert report.pages == 1 and report.files == 3


def test_page_that_is_not_a_lab_is_not_scanned(repo):
    assert all("theory" not in f.path for f in run(whole_tree=True).findings)


def test_untouched_divs_are_not_reflagged(repo):
    (repo / "ch" / "fit-lab.qmd").write_text(
        (repo / "ch" / "fit-lab.qmd").read_text() + "\nMore steps.\n")
    git(repo, "commit", "-qam", "edit")
    assert run("HEAD~1").findings == []


def test_added_div_in_the_lab_page_is_flagged(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n::: {#def-new}\nNew.\n:::\n")
    git(repo, "commit", "-qam", "edit")
    assert [f.what for f in run("HEAD~1").findings] == ["#def-new"]


def test_added_div_in_an_included_subfile_is_flagged(repo):
    sub = repo / "ch" / "_subfiles" / "_exr-a.qmd"
    sub.write_text(sub.read_text() + "\n::: {#thm-new}\nNew.\n:::\n")
    git(repo, "commit", "-qam", "edit")
    found = run("HEAD~1").findings
    assert [(f.path, f.page) for f in found] == [("ch/_subfiles/_exr-a.qmd", "ch/fit-lab.qmd")]


def test_added_include_of_exposition_is_flagged_through_nesting(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n{{< include _subfiles/_wrap.qmd >}}\n")
    git(repo, "commit", "-qam", "edit")
    assert [f.what for f in run("HEAD~1").findings] == ["_subfiles/_wrap.qmd"]


def test_added_include_of_an_exercise_is_not_flagged(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n{{< include _subfiles/_exr-a.qmd >}}\n")
    git(repo, "commit", "-qam", "edit")
    assert run("HEAD~1").findings == []


def test_escaped_include_is_not_followed(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n<!-- {{</* include _subfiles/_wrap.qmd */>}} -->\n")
    git(repo, "commit", "-qam", "edit")
    assert run("HEAD~1").findings == []


def test_moved_div_is_not_new(repo):
    sub = repo / "ch" / "_subfiles" / "_def-old.qmd"
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n" + sub.read_text())
    sub.write_text("Moved.\n")
    git(repo, "commit", "-qam", "move")
    assert run("HEAD~1").findings == []


def test_exempted_added_div_is_not_flagged(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text()
                    + "\n::: {#rem-new}\n<!-- lab-exposition-ok: navigation only -->\nSee x.\n:::\n")
    git(repo, "commit", "-qam", "edit")
    assert run("HEAD~1").findings == []


def test_ignored_paths_are_skipped(repo):
    ignores = cle.diffscope.compile_ignores(["ch/_subfiles/**"])
    assert run(whole_tree=True, ignores=ignores).findings == []


def test_exemption_stops_at_the_next_include():
    lines = ["{{< include _subfiles/_a.qmd >}}",
             "{{< include _subfiles/_b.qmd >}}",
             "<!-- lab-exposition-ok: b is navigation only -->"]
    assert not cle.exempt(lines, 1)
    assert cle.exempt(lines, 2)


def test_exemption_stops_at_the_next_div():
    lines = ["::: {#rem-a}", "A.", ":::", "::: {#rem-b}",
             "<!-- lab-exposition-ok: reason -->"]
    assert not cle.exempt(lines, 1)


def test_include_of_an_ignored_file_is_not_flagged(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n{{< include _subfiles/_wrap.qmd >}}\n")
    git(repo, "commit", "-qam", "edit")
    ignores = cle.diffscope.compile_ignores(["ch/_subfiles/_wrap.qmd"])
    assert run("HEAD~1", ignores=ignores).findings == []


def test_includes_are_not_followed_through_an_ignored_file(repo):
    ignores = cle.diffscope.compile_ignores(["ch/_subfiles/_wrap.qmd"])
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text("# Lab\n\n{{< include _subfiles/_wrap.qmd >}}\n")
    git(repo, "commit", "-qam", "edit")
    report = run(whole_tree=True, ignores=ignores)
    assert report.findings == [] and report.files == 1


def test_exempted_nested_include_does_not_make_its_wrapper_exposition(repo):
    wrap = repo / "ch" / "_subfiles" / "_wrap.qmd"
    wrap.write_text("{{< include _subfiles/_def-old.qmd >}}\n"
                    "<!-- lab-exposition-ok: the lab points back to it -->\n")
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text(page.read_text() + "\n{{< include _subfiles/_wrap.qmd >}}\n")
    git(repo, "commit", "-qam", "edit")
    assert run("HEAD~1").findings == []

def test_no_base_skips_rather_than_scanning_everything(repo):
    assert run("").skipped
    assert run("no-such-ref").skipped


def test_main_blocks_by_default_and_warns_when_told(repo, monkeypatch, capsys):
    monkeypatch.setenv("CLE_WHOLE_TREE", "true")
    monkeypatch.delenv("CLE_FAIL", raising=False)
    assert cle.main() == 1
    assert "::error file=ch/_subfiles/_def-old.qmd,line=1::" in capsys.readouterr().out
    monkeypatch.setenv("CLE_FAIL", "false")
    assert cle.main() == 0
    assert "::warning file=" in capsys.readouterr().out


# -- defaults agree -----------------------------------------------------------

def _yaml_default(path: Path, name: str) -> str:
    text = path.read_text()
    m = re.search(rf"^\s+{re.escape(name)}:\n(?:.*\n)*?\s+default: (.*)$", text, re.M)
    assert m, f"{name} has no default in {path}"
    return m.group(1).strip().strip("'\"")


@pytest.mark.parametrize("name,script", [
    ("pages", cle.DEFAULT_PAGES),
    ("prefixes", cle.DEFAULT_PREFIXES),
    ("fail", str(cle._DEFAULT_FAIL).lower()),
])
def test_defaults_agree(name, script):
    action = _DIR / "action.yml"
    workflow = _DIR.parent / ".github" / "workflows" / "check-lab-exposition.yml"
    assert _yaml_default(action, name) == script
    assert _yaml_default(workflow, name) == script


def test_exempted_include_is_not_followed_in_whole_tree_mode(repo):
    page = repo / "ch" / "fit-lab.qmd"
    page.write_text("# Lab\n\n{{< include _subfiles/_wrap.qmd >}}\n"
                    "<!-- lab-exposition-ok: the lab points back to it -->\n")
    git(repo, "commit", "-qam", "edit")
    report = run(whole_tree=True)
    assert report.findings == [] and report.files == 1
