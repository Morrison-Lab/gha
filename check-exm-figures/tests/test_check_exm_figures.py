"""Unit tests for check-exm-figures.

Covers what counts as a figure, the exemption comment and its reason, which
divs are examples (code fences, comments and non-example divs are not), diff
scoping (an untouched example is not reflagged, a touched one is), the
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
    "check_exm_figures", _DIR / "check-exm-figures.py"
)
assert _spec is not None and _spec.loader is not None
exf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exf)

NO_FIG = "::: {#exm-a}\nCompute the mean.\n:::\n"


def missing(text: str):
    """Opening lines of the examples with no figure, for a document string."""
    found, _ = exf.scan_file(text.split("\n"), None)
    return [ex.start for ex in found]


# -- what counts as a figure -------------------------------------------------

def test_example_without_a_figure_is_flagged():
    assert missing(NO_FIG) == [1]


@pytest.mark.parametrize("figure", [
    "![Scatter plot](images/scatter.png)",
    '<img src="a.png" alt="plot">',
    "::: {#fig-a}\nplot\n:::",
    "```{r}\n#| label: fig-scatter\nplot(1)\n```",
    "```{r}\n#| fig-cap: A scatter plot\nplot(1)\n```",
    "```{r}\n#| fig-alt: A scatter plot\nplot(1)\n```",
    "See @fig-scatter.",
    "{{< include _subfiles/ch/_scatter_fig.qmd >}}",
])
def test_figure_forms_are_accepted(figure):
    assert missing(f"::: {{#exm-a}}\nText.\n{figure}\n:::\n") == []


def test_plain_chunk_without_a_figure_label_is_not_a_figure():
    doc = "::: {#exm-a}\n```{r}\nmean(1:3)\n```\n:::\n"
    assert missing(doc) == [1]


def test_figure_outside_the_div_does_not_count():
    doc = NO_FIG + "\n![Plot](a.png)\n"
    assert missing(doc) == [1]


# -- exemptions --------------------------------------------------------------

def test_no_figure_comment_with_a_reason_exempts():
    doc = "::: {#exm-a}\n<!-- no-figure: a single number, nothing to plot -->\nText.\n:::\n"
    assert missing(doc) == []


def test_no_figure_comment_without_a_reason_does_not_exempt():
    doc = "::: {#exm-a}\n<!-- no-figure: -->\nText.\n:::\n"
    assert missing(doc) == [1]


# -- which divs are examples -------------------------------------------------

def test_other_div_types_are_not_examples():
    assert missing("::: {#def-a}\nText.\n:::\n::: {#exr-a}\nAsk.\n:::\n") == []


def test_example_in_a_code_fence_is_ignored():
    assert missing("```\n::: {#exm-a}\nText.\n:::\n```\n") == []


def test_example_in_an_html_comment_is_ignored():
    assert missing("<!--\n::: {#exm-a}\nText.\n:::\n-->\n") == []


def test_every_example_is_checked_separately():
    doc = NO_FIG + "\n::: {#exm-b}\nText.\n![Plot](a.png)\n:::\n\n::: {#exm-c}\nText.\n:::\n"
    assert missing(doc) == [1, 10]


def test_nested_closing_fence_ends_the_right_div():
    doc = "::: {#exm-a}\n::: {.callout-note}\nNote.\n:::\n![Plot](a.png)\n:::\n"
    assert missing(doc) == []


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


def _write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _commit(repo, name, text):
    _write(repo, name, text)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return exf.run_check(base, [exf.DEFAULT_GLOBS], [], False)


def test_untouched_example_is_grandfathered(repo):
    _commit(repo, "old.qmd", NO_FIG)
    _write(repo, "other.qmd", "text\n")
    report = _run("HEAD")
    assert not report.skipped and report.findings == []


def test_new_example_without_a_figure_is_flagged(repo):
    _commit(repo, "x.qmd", "text\n")
    _write(repo, "new.qmd", NO_FIG)
    report = _run("HEAD")
    assert [(f, n) for f, n, _ in report.findings] == [("new.qmd", 1)]


def test_touching_an_old_example_flags_it(repo):
    _commit(repo, "old.qmd", NO_FIG)
    _write(repo, "old.qmd", NO_FIG.replace("mean", "median"))
    assert [(f, n) for f, n, _ in _run("HEAD").findings] == [("old.qmd", 1)]


def test_touching_text_outside_the_example_does_not_flag_it(repo):
    _commit(repo, "old.qmd", NO_FIG + "\nIntro.\n")
    _write(repo, "old.qmd", NO_FIG + "\nIntro, revised.\n")
    assert _run("HEAD").findings == []


def test_adding_the_figure_clears_the_finding(repo):
    _commit(repo, "old.qmd", NO_FIG)
    _write(repo, "old.qmd", "::: {#exm-a}\nCompute the mean.\n![Plot](a.png)\n:::\n")
    assert _run("HEAD").findings == []


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "old.qmd", NO_FIG)
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "old.qmd", NO_FIG)
    assert _run("no-such-ref").skipped


def test_whole_tree_flags_every_example_without_a_figure(repo):
    _commit(repo, "old.qmd", NO_FIG)
    report = exf.run_check("", [exf.DEFAULT_GLOBS], [], True)
    assert not report.skipped
    assert [n for _, n, _ in report.findings] == [1]
    assert (report.files, report.examples) == (1, 1)


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "old.qmd", NO_FIG)
    ignores = exf.ods.compile_ignores(["old.qmd"])
    assert exf.run_check("", [exf.DEFAULT_GLOBS], ignores, True).findings == []


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-exm-figures.yml").read_text(encoding="utf-8")
    assert exf._DEFAULT_FAIL is False
    assert "default: 'false'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: false" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{exf.DEFAULT_GLOBS}'" in action
    assert f"default: '{exf.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"EXF_{name}" in action


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "old.qmd", NO_FIG)
    monkeypatch.setenv("EXF_WHOLE_TREE", "true")
    assert exf.main() == 0
    monkeypatch.setenv("EXF_FAIL", "true")
    assert exf.main() == 1
