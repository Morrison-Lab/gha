"""Unit tests for check-heading-siblings: grouping, includes, diff scoping, defaults."""

import importlib.util
import subprocess
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_heading_siblings", _DIR / "check-heading-siblings.py")
assert _spec is not None and _spec.loader is not None
chs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chs)


def lines(text):
    return [chs.Source("p.qmd", n, t) for n, t in enumerate(text.split("\n"), 1)]


def sections(n, level=2):
    return "\n\n".join(f"{'#' * level} S{i}\n\ntext" for i in range(n))


def test_default_limit_is_seven():
    assert chs.DEFAULT_MAX == 7


def test_seven_siblings_pass_and_eight_are_flagged():
    seven = chs.headings(lines(sections(7)))
    eight = chs.headings(lines(sections(8)))
    assert chs.crowded_groups(seven, 7) == []
    assert len(chs.crowded_groups(eight, 7)) == 1


def test_same_level_under_different_parents_are_separate_groups():
    text = "# A\n\n" + sections(5, 2) + "\n\n# B\n\n" + sections(5, 2)
    assert chs.crowded_groups(chs.headings(lines(text)), 7) == []


def test_nested_levels_are_not_added_to_the_parents_count():
    text = "\n".join(f"## S{i}\n\n### a\n\n### b\n" for i in range(5))
    assert chs.crowded_groups(chs.headings(lines(text)), 7) == []


def test_eight_children_under_one_parent_are_flagged():
    text = "# P\n\n" + sections(8, 2)
    groups = chs.crowded_groups(chs.headings(lines(text)), 7)
    assert [len(m) for _, m in groups] == [8]


def test_headings_in_code_and_comments_are_ignored():
    text = ("```r\n" + "\n".join(f"# c{i}" for i in range(10)) + "\n```\n"
            "<!--\n" + "\n".join(f"## x{i}" for i in range(10)) + "\n-->\n"
            "## Real\n")
    assert [h.title for h in chs.headings(lines(text))] == ["Real"]


def test_attributes_are_stripped_from_titles():
    assert chs.headings(lines("## Title {#sec-t .unnumbered}"))[0].title == "Title"


def test_includes_are_expanded_with_origin(tmp_path):
    sub = tmp_path / "_sub.qmd"
    sub.write_text(sections(8) + "\n")
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n{{< include _sub.qmd >}}\n')
    found = chs.headings(chs.expand(str(page), str(tmp_path)))
    assert len(found) == 8 and found[0].path.endswith("_sub.qmd")


def test_include_cycle_terminates(tmp_path):
    a = tmp_path / "a.qmd"
    a.write_text("{{< include a.qmd >}}\n## X\n")
    assert [h.title for h in chs.headings(chs.expand(str(a), str(tmp_path)))] == ["X"]


def test_allow_marker_exempts_a_page(tmp_path):
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n<!-- check-heading-siblings: allow -->\n'
                    + sections(9))
    assert chs.scan_page(str(page), str(tmp_path), None, 7) == []


def test_untouched_group_is_not_flagged_but_whole_tree_flags_it(tmp_path):
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n' + sections(9))
    assert chs.scan_page(str(page), str(tmp_path), {}, 7) == []
    assert len(chs.scan_page(str(page), str(tmp_path), None, 7)) == 1


def test_group_with_an_added_heading_is_flagged_on_it(tmp_path):
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n' + sections(9))
    found = chs.headings(chs.expand(str(page), str(tmp_path)))
    target = found[3]
    touched = {target.path: [target.line]}
    out = chs.scan_page(str(page), str(tmp_path), touched, 7)
    assert len(out) == 1 and out[0].line == target.line and out[0].count == 9


def test_added_body_line_does_not_flag(tmp_path):
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n' + sections(9))
    touched = {chs.os.path.normpath(str(page)): [7]}
    assert chs.scan_page(str(page), str(tmp_path), touched, 7) == []


def test_parse_diff_collects_added_lines():
    diff = "+++ b/a.qmd\n@@ -1,0 +2,2 @@\n+## One\n+\n"
    assert chs.parse_diff(diff) == {"a.qmd": [2]}


def test_end_to_end_in_a_git_repo(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    git("config", "user.name", "t")
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n' + sections(7) + "\n")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True,
                          capture_output=True, check=True).stdout.strip()
    page.write_text(page.read_text() + "\n## Extra\n")
    git("commit", "-qam", "add")
    monkeypatch.chdir(tmp_path)
    report = chs.run_check(base, ["*.qmd"], [], False, 7)
    assert not report.skipped and len(report.findings) == 1
    assert report.findings[0].count == 8
    assert chs.run_check("", ["*.qmd"], [], False, 7).skipped
