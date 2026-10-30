"""Unit tests for check-heading-levels.

Covers the three rules (skipped level, page starting too deep, title repeated
as the first heading), what is not counted (fenced divs, code fences, comments,
front matter, the allow marker), include resolution, diff scoping (an untouched
heading is not reflagged, an added one is), the skip-not-fallback guard, and
the defaults the action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_heading_levels", _DIR / "check-heading-levels.py"
)
assert _spec is not None and _spec.loader is not None
hlv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hlv)


def page(tmp_path, body, name="page.qmd", title="Newton"):
    path = tmp_path / name
    path.write_text(f'---\ntitle: "{title}"\n---\n\n{body}')
    return str(path)


def kinds(tmp_path, body, **kwargs):
    path = page(tmp_path, body, **kwargs)
    return [(f.kind, f.line) for f in hlv.scan_page(path, str(tmp_path))]


# -- skipped level -----------------------------------------------------------

def test_skipped_level_is_flagged(tmp_path):
    assert kinds(tmp_path, "## A\n\n#### B\n") == [("skip", 7)]


def test_next_level_down_is_fine(tmp_path):
    assert kinds(tmp_path, "## A\n\n### B\n\n#### C\n\n## D\n") == []


def test_going_back_up_any_distance_is_fine(tmp_path):
    assert kinds(tmp_path, "## A\n\n### B\n\n#### C\n\n## D\n") == []


# -- page starts too deep ----------------------------------------------------

def test_page_starting_at_level_three_is_flagged_once(tmp_path):
    assert kinds(tmp_path, "### A\n\n### B\n") == [("deep", 5)]


def test_page_starting_at_level_one_is_fine(tmp_path):
    assert kinds(tmp_path, "# A\n\n## B\n") == []


def test_include_opening_a_page_deep_is_flagged_at_the_include(tmp_path):
    (tmp_path / "_cfg.qmd").write_text("### Configuring R\n")
    found = kinds(tmp_path, "{{< include _cfg.qmd >}}\n\n## A\n")
    assert found == [("deep", 1)]
    path = page(tmp_path, "{{< include _cfg.qmd >}}\n\n## A\n")
    assert hlv.scan_page(path, str(tmp_path))[0].path.endswith("_cfg.qmd")


def test_include_headings_set_the_level_for_the_page(tmp_path):
    (tmp_path / "_cfg.qmd").write_text("## Setup\n")
    assert kinds(tmp_path, "{{< include _cfg.qmd >}}\n\n### A\n") == []


# -- title repeated ----------------------------------------------------------

def test_first_heading_repeating_the_title_is_flagged(tmp_path):
    assert kinds(tmp_path, "## Newton {#sec-newton}\n\nText.\n") == [("title", 5)]


def test_title_match_ignores_case_and_attributes(tmp_path):
    assert kinds(tmp_path, "## NEWTON {.unnumbered}\n") == [("title", 5)]


def test_a_later_heading_repeating_the_title_is_fine(tmp_path):
    assert kinds(tmp_path, "## A\n\n## Newton\n") == []


def test_a_level_one_heading_matching_the_title_is_fine(tmp_path):
    assert kinds(tmp_path, "# Newton\n") == []


# -- what is not counted -----------------------------------------------------

def test_div_titles_are_not_headings(tmp_path):
    body = "## A\n\n::: {#def-a}\n#### Title\n\nText.\n:::\n\n## B\n"
    assert kinds(tmp_path, body) == []


def test_code_fences_and_comments_hold_no_headings(tmp_path):
    body = "## A\n\n```r\n#### not a heading\n```\n\n<!--\n#### nor this\n-->\n"
    assert kinds(tmp_path, body) == []


def test_allow_marker_exempts_a_heading(tmp_path):
    body = "## A\n\n#### B <!-- check-heading-levels: allow -->\n"
    assert kinds(tmp_path, body) == []


# -- files without a title are includes ---------------------------------------

def test_titleless_file_is_not_a_page(tmp_path):
    path = tmp_path / "exm-fragment.qmd"
    path.write_text("#### Example\n\nText.\n")
    assert not hlv.is_page(str(path))


def test_underscore_file_is_not_a_page(tmp_path):
    path = tmp_path / "_sub.qmd"
    path.write_text('---\ntitle: "x"\n---\n')
    assert not hlv.is_page(str(path))


def test_first_heading_of_an_include_has_no_predecessor(tmp_path):
    path = tmp_path / "_sub.qmd"
    path.write_text("#### Deep\n\n### Up\n")
    assert hlv.scan_subfile(str(path)) == []


def test_skip_inside_an_include_is_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "_sub.qmd"
    path.write_text("## A\n\n#### Deep\n")
    assert [(f.kind, f.line) for f in hlv.scan_subfile(str(path))] == [("skip", 3)]


# -- diff scoping ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "T")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_untouched_bad_heading_is_not_reflagged(repo):
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n## A\n\n#### Deep\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "other.qmd").write_text('---\ntitle: "O"\n---\n\n## Fine\n')
    _git(repo, "add", ".")
    report = hlv.run_check("HEAD", ["*.qmd"], [], False)
    assert report.findings == [] and not report.skipped


def test_added_bad_heading_is_flagged(repo):
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n## A\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n## A\n\n#### Deep\n')
    _git(repo, "add", ".")
    report = hlv.run_check("HEAD", ["*.qmd"], [], False)
    assert [(f.path, f.line, f.kind) for f in report.findings] == [("page.qmd", 7, "skip")]


def test_bad_heading_in_an_untouched_include_is_not_reflagged(repo):
    (repo / "_cfg.qmd").write_text("### Configuring R\n")
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n{{< include _cfg.qmd >}}\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n{{< include _cfg.qmd >}}\n\nMore.\n')
    _git(repo, "add", ".")
    report = hlv.run_check("HEAD", ["*.qmd"], [], False)
    assert report.findings == []


def test_whole_tree_flags_the_include_without_a_diff(repo):
    (repo / "_cfg.qmd").write_text("### Configuring R\n")
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n{{< include _cfg.qmd >}}\n')
    _git(repo, "add", ".")
    report = hlv.run_check("", ["*.qmd"], [], True)
    assert [(f.path, f.kind) for f in report.findings] == [("_cfg.qmd", "deep")]


def test_no_base_ref_skips_rather_than_scanning(repo):
    (repo / "page.qmd").write_text('---\ntitle: "T"\n---\n\n#### Deep\n')
    _git(repo, "add", ".")
    report = hlv.run_check("", ["*.qmd"], [], False)
    assert report.skipped and report.findings == []


# -- defaults the action and the script must agree on -------------------------

def test_action_and_script_agree_on_defaults():
    action = (_DIR / "action.yml").read_text()
    assert "default: 'false'" in action
    assert hlv._DEFAULT_FAIL is False
    assert hlv.DEFAULT_GLOBS == "*.qmd"
    assert "HLV_FAIL" in action and "HLV_BASE_REF" in action
