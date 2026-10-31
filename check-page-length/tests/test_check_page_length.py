"""Unit tests for check-page-length: counting, include expansion, scoping, defaults."""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_page_length", _DIR / "check-page-length.py")
assert _spec is not None and _spec.loader is not None
cpl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpl)


def test_counts_display_and_inline_math():
    assert cpl.count_math("a $x$ and $y$.\n\n$$\nz = 1\n$$\n") == 3


def test_math_in_code_and_comments_is_not_counted():
    text = "```r\nx <- '$a$'\n```\n<!-- $b$ -->\nprice is $5 and $6.\n"
    assert cpl.count_math(text) == 1  # "$5 and $" reads as one inline span


def test_math_like_text_in_inline_code_is_not_counted():
    assert cpl.count_math("Use `$VAR` and `$HOME` in shell, then $x$.") == 1


def test_escaped_dollar_is_not_math():
    assert cpl.count_math(r"costs \$5 and \$6") == 0


def test_over_limit_reports_math_first():
    assert cpl.over_limit(601, 6000, 600, 5000) == ("math", 601, 600)
    assert cpl.over_limit(10, 5001, 600, 5000) == ("lines", 5001, 5000)
    assert cpl.over_limit(600, 5000, 600, 5000) is None


def make_page(tmp_path, n_math, marker=""):
    sub = tmp_path / "_sub.qmd"
    sub.write_text("\n".join(f"Line ${i}$ here." for i in range(n_math)) + "\n")
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n'
                    f'{marker}{{{{< include _sub.qmd >}}}}\n')
    return page, sub


def test_includes_are_expanded(tmp_path):
    page, _ = make_page(tmp_path, 5)
    text, files = cpl.expand(str(page), str(tmp_path))
    assert cpl.count_math(text) == 5 and len(files) == 2


def test_include_cycle_terminates(tmp_path):
    a = tmp_path / "a.qmd"
    a.write_text("{{< include a.qmd >}}\n$x$\n")
    text, _ = cpl.expand(str(a), str(tmp_path))
    assert "$x$" in text


def test_is_page_needs_title(tmp_path):
    assert cpl.is_page('---\ntitle: "T"\n---\nbody')
    assert not cpl.is_page("body only")
    assert not cpl.is_page("---\nfoo: 1\n---\nbody")


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "tester")
    git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_untouched_long_page_is_not_flagged(repo):
    make_page(repo, 20)
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    (repo / "other.md").write_text("x")
    git(repo, "add", "."); git(repo, "commit", "-qm", "unrelated")
    rep = cpl.run_check("HEAD~1", ["*.qmd"], [], False, 10, 5000)
    assert rep.findings == [] and not rep.skipped


def test_edit_to_an_included_file_flags_the_page(repo):
    page, sub = make_page(repo, 20)
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    sub.write_text(sub.read_text() + "One more $z$.\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "edit")
    rep = cpl.run_check("HEAD~1", ["*.qmd"], [], False, 10, 5000)
    assert [(r, f.kind) for r, f in rep.findings] == [("page.qmd", "math")]
    assert rep.findings[0][1].line == 1


def test_short_page_is_not_flagged_when_touched(repo):
    page, sub = make_page(repo, 3)
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    sub.write_text(sub.read_text() + "More $z$.\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "edit")
    assert cpl.run_check("HEAD~1", ["*.qmd"], [], False, 10, 5000).findings == []


def test_allow_marker_exempts_the_page(repo):
    page, sub = make_page(repo, 20, marker="<!-- check-page-length: allow -->\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    sub.write_text(sub.read_text() + "More $z$.\n")
    git(repo, "add", "."); git(repo, "commit", "-qm", "edit")
    assert cpl.run_check("HEAD~1", ["*.qmd"], [], False, 10, 5000).findings == []


def test_no_base_ref_skips_instead_of_scanning(repo):
    make_page(repo, 20)
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    assert cpl.run_check("", ["*.qmd"], [], False, 10, 5000).skipped


def test_whole_tree_measures_every_page(repo):
    make_page(repo, 20)
    git(repo, "add", "."); git(repo, "commit", "-qm", "base")
    rep = cpl.run_check("", ["*.qmd"], [], True, 10, 5000)
    assert len(rep.findings) == 1


def test_action_defaults_match_script():
    text = (_DIR / "action.yml").read_text()

    def default(name):
        m = re.search(rf"^  {name}:\n(?:    .*\n)*?    default: '?([^'\n]*)'?$",
                      text, re.MULTILINE)
        assert m, name
        return m.group(1)

    assert default("max-math") == str(cpl.DEFAULT_MAX_MATH)
    assert default("max-lines") == str(cpl.DEFAULT_MAX_LINES)
    assert default("fail") == "false"
