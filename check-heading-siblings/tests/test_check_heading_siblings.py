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


def test_yaml_comments_in_front_matter_are_not_headings():
    text = '---\ntitle: "P"\n# a yaml comment\n---\n\n## Real\n'
    assert [h.title for h in chs.headings(lines(text))] == ["Real"]
    assert chs.headings(lines(text))[0].parent == -1


def test_attributes_are_stripped_from_titles():
    assert chs.headings(lines("## Title {#sec-t .hl}"))[0].title == "Title"


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


def test_fails_by_default():
    root = Path(__file__).resolve().parent.parent
    action = (root / "action.yml").read_text()
    workflow = (root.parent / ".github" / "workflows" / "check-heading-siblings.yml").read_text()
    assert "default: 'true'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: true" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert 'fail = diffscope.env_flag("CHS_FAIL", True)' in (root / "check-heading-siblings.py").read_text()


def test_default_minimum_is_two():
    assert chs.DEFAULT_MIN == 2


def test_lone_top_heading_is_found_even_with_subsections():
    found = chs.headings(lines("# Only\n\ntext\n\n## A\n\n## B\n"))
    assert chs.lone_top_heading(found, 2).title == "Only"


def test_two_top_headings_and_no_headings_are_not_lone():
    two = chs.headings(lines(sections(2, 1)))
    assert chs.lone_top_heading(two, 2) is None
    assert chs.lone_top_heading([], 2) is None


def test_minimum_zero_turns_the_rule_off():
    found = chs.headings(lines("# Only\n"))
    assert chs.lone_top_heading(found, 0) is None


def test_lone_heading_is_flagged_only_when_the_diff_adds_it(tmp_path):
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n# Only\n\ntext\n')
    found = chs.headings(chs.expand(str(page), str(tmp_path)))
    assert chs.scan_page(str(page), str(tmp_path), {}, 7, 2) == []
    touched = {found[0].path: [found[0].line]}
    out = chs.scan_page(str(page), str(tmp_path), touched, 7, 2)
    assert len(out) == 1 and out[0].lone and out[0].line == found[0].line
    assert "only top-level heading" in chs.format_message(out[0])
    assert len(chs.scan_page(str(page), str(tmp_path), None, 7, 2)) == 1
    assert chs.scan_page(str(page), str(tmp_path), None, 7) == []


def test_callout_titles_and_unnumbered_headings_are_not_outline_entries():
    text = ("::: {.callout-note collapse=true}\n# Source\n\ntext\n:::\n\n"
            "# Body\n\n# References {#references .unnumbered}\n")
    assert [h.title for h in chs.headings(lines(text))] == ["Body"]
    assert chs.lone_top_heading(chs.headings(lines(text)), 2).title == "Body"


def test_unnumbered_headings_do_not_count_toward_the_max_rule():
    text = "# Body\n\n" + "\n\n".join(f"## U{i} {{.unnumbered}}" for i in range(9))
    assert chs.crowded_groups(chs.headings(lines(text)), 7) == []


def outline(text):
    return chs.headings(lines(text), outline=True)


def test_lone_numbered_subheading_is_found():
    found = outline("# One\n\n## Only child\n\n# Two\n\n## A\n\n## B\n")
    lone = chs.lone_subheadings(found)
    assert [(found[p].title, h.title) for p, h in lone] == [("One", "Only child")]


def test_two_numbered_children_and_top_level_are_not_lone():
    # A page's single top-level heading is the min rule's, not this one's.
    assert chs.lone_subheadings(outline("# One\n\n## A\n\n## B\n")) == []
    assert chs.lone_subheadings(outline("# Only\n")) == []


def test_unnumbered_and_unlisted_siblings_do_not_count_but_parent():
    text = ("# One\n\n## A\n\n## Notes {.unnumbered}\n\n## Hidden {.unlisted}\n\n"
            "# Reading {.unnumbered}\n\n### Lone under unnumbered\n")
    found = outline(text)
    lone = [(found[p].title, h.title) for p, h in chs.lone_subheadings(found)]
    assert lone == [("One", "A"), ("Reading", "Lone under unnumbered")]


def test_lone_unnumbered_child_is_not_flagged():
    assert chs.lone_subheadings(outline("# One\n\n## Notes {.unnumbered}\n")) == []


def test_headings_inside_divs_are_not_outline_entries():
    text = ("# One\n\n## A\n\n::: {#def-x}\n#### Term\n\ntext\n:::\n\n"
            "::: {.panel-tabset}\n### R\n\n### Python\n:::\n\n## B\n")
    found = outline(text)
    assert [h.title for h in found] == ["One", "A", "B"]
    assert chs.lone_subheadings(found) == []


def test_div_titles_still_count_for_the_max_rule_as_before():
    text = "::: {#def-x}\n## T\n:::\n"
    assert [h.title for h in chs.headings(lines(text))] == ["T"]


def test_lone_subheading_is_flagged_when_it_or_its_parent_is_touched(tmp_path):
    page = tmp_path / "page.qmd"
    page.write_text('---\ntitle: "P"\n---\n\n# A\n\n## Only\n\n# B\n\n## X\n\n## Y\n')
    path = chs.os.path.normpath(str(page))
    args = (str(tmp_path), )
    assert chs.scan_page(str(page), *args, {}, 7, 0, True) == []
    for line in (5, 7):  # the parent, then the lone heading itself
        out = chs.scan_page(str(page), *args, {path: [line]}, 7, 0, True)
        assert len(out) == 1 and out[0].subheading and out[0].line == 7
        message = chs.format_message(out[0])
        assert "only numbered heading" in message
        assert "add another sibling heading or promote a child" in message
    # A touched sibling group elsewhere does not flag it.
    assert chs.scan_page(str(page), *args, {path: [13]}, 7, 0, True) == []
    assert len(chs.scan_page(str(page), *args, None, 7, 0, True)) == 1
    assert chs.scan_page(str(page), *args, None, 7, 0, False) == []


def test_lone_rule_is_on_by_default():
    root = Path(__file__).resolve().parent.parent
    action = (root / "action.yml").read_text()
    workflow = (root.parent / ".github" / "workflows" / "check-heading-siblings.yml").read_text()
    assert "default: 'true'" in action.split("  lone:")[1].split("  fail:")[0]
    assert "default: true" in workflow.split("      lone:")[1].split("      fail:")[0]
    assert 'diffscope.env_flag("CHS_LONE", True)' in (root / "check-heading-siblings.py").read_text()
