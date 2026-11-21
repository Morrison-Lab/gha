"""Unit tests for check-lone-subfloats.

Covers what a subfloat is (a nested float div, a labeled chunk, an inline
`{#fig-}` image or `{#tbl-}` table caption), the two float rules (one
subfloat in all, one per tab of a tabset) and the one-entry subcaption rule,
what does not count (a chunk that shows nothing, a float of the other kind,
code fences, comments), the allow pragma and its reason, diff scoping, the
skip-not-fallback guard, and the defaults the action, the reusable workflow
and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_lone_subfloats", _DIR / "check-lone-subfloats.py"
)
assert _spec is not None and _spec.loader is not None
cls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cls)


def chunk(label, lang="r", extra=""):
    return f"```{{{lang}}}\n#| label: {label}\n{extra}plot(1)\n```\n"


def tabset(r_body, py_body):
    return ('::: {.panel-tabset group="language"}\n\n### R\n\n' + r_body
            + "\n### Python\n\n" + py_body + "\n:::\n")


# The lds#fig-residual pattern: a figure wrapping a language tabset whose
# chunks keep their fig- labels, so each tab shows a lone (a) or (b).
PER_TAB = ("::: {#fig-res}\n\n"
           + tabset(chunk("fig-res-r"), chunk("fig-res-py", "python"))
           + "\nThe residuals.\n:::\n")


def found(text: str):
    """(line, rule) of each finding, for a document string."""
    return [(f.line, f.rule) for f in cls.scan_file(text.split("\n"))]


# -- the per-tab rule ----------------------------------------------------------

def test_figure_with_one_subfigure_per_tab_is_flagged():
    assert found(PER_TAB) == [(1, "per-tab")]


def test_unlabeled_chunks_in_the_tabs_are_clean():
    doc = PER_TAB.replace("label: fig-res-r", "label: res-r").replace(
        "label: fig-res-py", "label: res-py")
    assert found(doc) == []


def test_two_subfigures_in_each_tab_are_clean():
    doc = ("::: {#fig-a}\n"
           + tabset(chunk("fig-a-r1") + chunk("fig-a-r2"),
                    chunk("fig-a-p1", "python") + chunk("fig-a-p2", "python"))
           + "Cap.\n:::\n")
    assert found(doc) == []


def test_one_tab_with_a_lone_subfigure_is_flagged():
    doc = ("::: {#fig-a}\n"
           + tabset(chunk("fig-a-r1") + chunk("fig-a-r2"),
                    chunk("fig-a-p1", "python"))
           + "Cap.\n:::\n")
    assert found(doc) == [(1, "per-tab")]


def test_subfigure_outside_the_tabset_counts_in_every_view():
    doc = ("::: {#fig-a}\n" + chunk("fig-a-shared")
           + tabset(chunk("fig-a-r"), chunk("fig-a-py", "python"))
           + "Cap.\n:::\n")
    assert found(doc) == []


def test_tabs_inside_each_subfigure_are_clean():
    # psw's "Subfigures with language tabsets": a tabset inside each subfigure.
    def sub(n):
        return ("::: {#fig-s-" + n + "}\n"
                + tabset(chunk(f"s-{n}-r"), chunk(f"s-{n}-py", "python"))
                + f"Panel {n}.\n:::\n")
    doc = "::: {#fig-s layout-ncol=2}\n" + sub("a") + sub("b") + "Both.\n:::\n"
    assert found(doc) == []


def test_subfigure_divs_one_per_tab_are_flagged():
    doc = ("::: {#fig-a}\n"
           + tabset("::: {#fig-a-r}\n![x](r.png)\n:::\n",
                    "::: {#fig-a-py}\n![x](py.png)\n:::\n")
           + "Cap.\n:::\n")
    assert found(doc) == [(1, "per-tab")]


def test_tab_level_is_the_first_heading_in_the_tabset():
    # A level-4 heading inside a level-3 tab does not start a new tab.
    doc = ("::: {#fig-a}\n::: {.panel-tabset}\n### R\n" + chunk("fig-a-1")
           + "#### Detail\n" + chunk("fig-a-2") + "### Python\n"
           + chunk("fig-a-3", "python") + chunk("fig-a-4", "python")
           + ":::\nCap.\n:::\n")
    assert found(doc) == []


# -- the one-subfloat rule -------------------------------------------------------

def test_figure_with_one_subfigure_is_flagged():
    doc = "::: {#fig-a}\n" + chunk("fig-a-1") + "Cap.\n:::\n"
    assert found(doc) == [(1, "one")]


def test_figure_with_two_subfigures_is_clean():
    doc = "::: {#fig-a layout-ncol=2}\n" + chunk("fig-a-1") + chunk("fig-a-2") + "Cap.\n:::\n"
    assert found(doc) == []


def test_figure_with_no_subfigures_is_clean():
    doc = "::: {#fig-a}\n" + chunk("a-plot") + "Cap.\n:::\n"
    assert found(doc) == []


def test_inline_image_subfigure_counts():
    doc = "::: {#fig-a}\n![Left](l.png){#fig-a-l}\n\nCap.\n:::\n"
    assert found(doc) == [(1, "one")]


def test_table_with_one_subtable_is_flagged():
    doc = ("::: {#tbl-a}\n| x |\n|---|\n| 1 |\n\n: One {#tbl-a-1}\n\nCap.\n:::\n")
    assert found(doc) == [(1, "one")]


def test_table_with_one_subtable_per_tab_is_flagged():
    doc = ("::: {#tbl-a}\n"
           + tabset(chunk("tbl-a-r"), chunk("tbl-a-py", "python"))
           + "Cap.\n:::\n")
    assert found(doc) == [(1, "per-tab")]


def test_float_of_the_other_kind_is_not_a_subfloat():
    doc = "::: {#fig-a}\n" + chunk("tbl-a-1") + "Cap.\n:::\n"
    assert found(doc) == []


def test_chunk_that_shows_nothing_is_not_a_subfloat():
    # A data chunk outside the tabs would otherwise make every view two.
    doc = ("::: {#fig-a}\n" + chunk("fig-a-data", extra="#| include: false\n")
           + tabset(chunk("fig-a-r"), chunk("fig-a-p", "python"))
           + "Cap.\n:::\n")
    assert found(doc) == [(1, "per-tab")]


def test_nested_subfloats_count_for_the_innermost_float():
    inner = "::: {#fig-b}\n" + chunk("fig-b-1") + chunk("fig-b-2") + "Inner.\n:::\n"
    other = "::: {#fig-c}\n![x](c.png)\n:::\n"
    doc = "::: {#fig-a layout-ncol=2}\n" + inner + other + "Outer.\n:::\n"
    assert found(doc) == []


# -- the subcaption rule ----------------------------------------------------------

@pytest.mark.parametrize("opts", [
    '#| fig-subcap: ["Only"]\n',
    "#| fig-subcap:\n#|   - Only\n",
])
def test_one_subcaption_is_flagged(opts):
    assert found(chunk("fig-a", extra=opts)) == [(1, "subcap")]


@pytest.mark.parametrize("opts", [
    '#| fig-subcap: ["One", "Two"]\n',
    "#| fig-subcap:\n#|   - One\n#|   - Two\n",
    "#| fig-subcap: true\n",
])
def test_several_or_counted_subcaptions_are_clean(opts):
    assert found(chunk("fig-a", extra=opts)) == []


# -- what is not scanned, and the pragma --------------------------------------

def test_float_in_a_code_fence_is_ignored():
    assert found("````markdown\n" + PER_TAB + "````\n") == []


def test_float_in_an_html_comment_is_ignored():
    assert found("<!--\n" + PER_TAB + "-->\n") == []


def test_allow_pragma_with_a_reason_exempts():
    doc = PER_TAB.replace("The residuals.",
                          "<!-- check-lone-subfloats: allow: demo of the defect -->\nThe residuals.")
    assert found(doc) == []


def test_allow_pragma_without_a_reason_does_not_exempt():
    doc = PER_TAB.replace("The residuals.",
                          "<!-- check-lone-subfloats: allow: -->\nThe residuals.")
    assert found(doc) == [(1, "per-tab")]


def test_messages_name_the_fix():
    (f,) = cls.scan_file(PER_TAB.split("\n"))
    msg = cls.format_message(f)
    assert "#fig-res" in msg and "fig-alt" in msg and "lone subfigure" in msg


# -- diff scoping --------------------------------------------------------------

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


def _write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _commit(repo, name, text):
    _write(repo, name, text)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return cls.run_check(base, [cls.DEFAULT_GLOBS], [], False)


def test_untouched_figure_is_grandfathered(repo):
    _commit(repo, "old.qmd", PER_TAB)
    _write(repo, "other.qmd", "text\n")
    report = _run("HEAD")
    assert not report.skipped and report.findings == []


def test_touching_the_figure_flags_it(repo):
    _commit(repo, "old.qmd", PER_TAB)
    _write(repo, "old.qmd", PER_TAB.replace("The residuals.", "The residuals, revised."))
    assert [(p, f.line) for p, f in _run("HEAD").findings] == [("old.qmd", 1)]


def test_touching_text_outside_the_figure_does_not_flag_it(repo):
    _commit(repo, "old.qmd", PER_TAB + "\nIntro.\n")
    _write(repo, "old.qmd", PER_TAB + "\nIntro, revised.\n")
    assert _run("HEAD").findings == []


def test_dropping_the_labels_clears_the_finding(repo):
    _commit(repo, "old.qmd", PER_TAB)
    _write(repo, "old.qmd", PER_TAB.replace("label: fig-res-", "label: res-"))
    assert _run("HEAD").findings == []


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "old.qmd", PER_TAB)
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "old.qmd", PER_TAB)
    assert _run("no-such-ref").skipped


def test_whole_tree_flags_every_figure(repo):
    _commit(repo, "old.qmd", PER_TAB)
    report = cls.run_check("", [cls.DEFAULT_GLOBS], [], True)
    assert [(p, f.line) for p, f in report.findings] == [("old.qmd", 1)]
    assert report.files == 1


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "old.qmd", PER_TAB)
    ignores = cls.diffscope.compile_ignores(["old.qmd"])
    assert cls.run_check("", [cls.DEFAULT_GLOBS], ignores, True).findings == []


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-lone-subfloats.yml").read_text(encoding="utf-8")
    assert cls._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: true" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{cls.DEFAULT_GLOBS}'" in action
    assert f"default: '{cls.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"CLS_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "old.qmd", PER_TAB)
    monkeypatch.setenv("CLS_WHOLE_TREE", "true")
    assert cls.main() == 1
    monkeypatch.setenv("CLS_FAIL", "false")
    assert cls.main() == 0
