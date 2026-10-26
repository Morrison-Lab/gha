"""Unit tests for check-visualization-figures.

Covers which divs are checked (a visualization title on an exercise, example,
definition, result or remark div; not a figure or a solution), where the title
comes from, what counts as a figure, the paired solution of an exercise, the
exemption comment, diff scoping, the skip-not-fallback guard and the defaults.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_visualization_figures", _DIR / "check-visualization-figures.py"
)
assert _spec is not None and _spec.loader is not None
viz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(viz)

NO_FIG = "::: {#exr-a}\n#### Visualize the cost\n\nPlot it.\n:::\n"


def missing(text: str, solution=None, path: str = "x.qmd"):
    """Opening lines of the visualization divs with no figure."""
    found, _ = viz.check_lines(
        text.split("\n"), path, None,
        solution=solution.split("\n") if solution else None,
    )
    return [d.start for d in found]


# -- which divs are checked --------------------------------------------------

def test_visualization_title_without_figure_is_flagged():
    assert missing(NO_FIG) == [1]


@pytest.mark.parametrize("word", ["Visualize", "visualizing", "Visualization",
                                  "visualise", "VISUALIZED"])
def test_every_form_of_the_word_matches(word):
    assert missing(f"::: {{#exm-a}}\n#### {word} the data\n:::\n") == [1]


def test_title_without_the_word_is_not_checked():
    assert missing("::: {#exr-a}\n#### Sketch the level sets\n:::\n") == []


def test_word_in_the_body_but_not_the_title_is_not_checked():
    assert missing("::: {#exr-a}\n#### Sketch\n\nVisualize it.\n:::\n") == []


def test_title_attribute_is_read():
    assert missing('::: {#exm-a title="Visualizing a surface"}\nText.\n:::\n') == [1]


@pytest.mark.parametrize("prefix", ["exr", "exm", "def", "thm", "lem", "prp",
                                    "cor", "rem"])
def test_subject_prefixes(prefix):
    assert missing(f"::: {{#{prefix}-a}}\n#### Visualization\n:::\n") == [1]


@pytest.mark.parametrize("prefix", ["fig", "sol", "tbl"])
def test_figures_and_solutions_are_not_subjects(prefix):
    assert missing(f"::: {{#{prefix}-a}}\n#### Visualization\n:::\n") == []


def test_div_in_a_code_fence_or_comment_is_ignored():
    assert missing("```\n" + NO_FIG + "```\n") == []
    assert missing("<!--\n" + NO_FIG + "-->\n") == []


# -- what counts as a figure -------------------------------------------------

@pytest.mark.parametrize("figure", [
    "![Scatter plot](images/scatter.png)",
    "::: {#fig-a}\nplot\n:::",
    "```{r}\n#| label: fig-scatter\nplot(1)\n```",
    "```{r}\n#| fig-alt: A scatter plot\nplot(1)\n```",
    "See @fig-scatter.",
    "{{< include _subfiles/ch/_fig-scatter.qmd >}}",
])
def test_figure_forms_are_accepted(figure):
    doc = f"::: {{#exr-a}}\n#### Visualize it\n{figure}\n:::\n"
    assert missing(doc) == []


def test_plain_chunk_is_not_a_figure():
    doc = "::: {#exr-a}\n#### Visualize it\n```{r}\nplot(1)\n```\n:::\n"
    assert missing(doc) == [1]


# -- the solution of an exercise ---------------------------------------------

def test_solution_div_in_the_same_file_with_a_figure_satisfies():
    doc = NO_FIG + "\n::: {#sol-a}\n::: {#fig-p}\nplot\n:::\n:::\n"
    assert missing(doc) == []


def test_solution_div_in_the_same_file_without_a_figure_does_not():
    doc = NO_FIG + "\n::: {#sol-a}\nThe answer.\n:::\n"
    assert missing(doc) == [1]


def test_solution_with_another_slug_does_not_satisfy():
    doc = NO_FIG + "\n::: {#sol-b}\nSee @fig-p.\n:::\n"
    assert missing(doc) == [1]


def test_sibling_solution_file_with_a_figure_satisfies():
    assert missing(NO_FIG, solution="::: {#sol-a}\nSee @fig-p.\n:::\n") == []


def test_sibling_solution_file_without_a_figure_does_not():
    assert missing(NO_FIG, solution="::: {#sol-a}\nText.\n:::\n") == [1]


def test_solution_never_satisfies_an_example():
    doc = "::: {#exm-a}\n#### Visualization\n:::\n\n::: {#sol-a}\n@fig-p\n:::\n"
    assert missing(doc) == [1]


def test_sibling_solution_is_found_by_file_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "_sol-a-part2.qmd").write_text("::: {#sol-a-part2}\n@fig-p\n:::\n")
    exercise = "::: {#exr-a-part2}\n#### Visualize it (part 2)\n:::\n"
    found, _ = viz.check_lines(exercise.split("\n"), "_exr-a-part2.qmd", None)
    assert found == []
    found, _ = viz.check_lines(exercise.split("\n"), "_exr-b.qmd", None)
    assert [d.start for d in found] == [1]


# -- exemption ---------------------------------------------------------------

def test_no_figure_comment_with_a_reason_exempts():
    doc = "::: {#exr-a}\n#### Visualize it\n<!-- no-figure: a table -->\n:::\n"
    assert missing(doc) == []


def test_no_figure_comment_without_a_reason_does_not():
    doc = "::: {#exr-a}\n#### Visualize it\n<!-- no-figure: -->\n:::\n"
    assert missing(doc) == [1]


# -- diff scoping and defaults -----------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_untouched_div_is_not_reflagged_and_a_touched_one_is(repo):
    (repo / "a.qmd").write_text(NO_FIG)
    _git(repo, "add", "."), _git(repo, "commit", "-qm", "base")
    (repo / "b.qmd").write_text(NO_FIG)
    _git(repo, "add", "."), _git(repo, "commit", "-qm", "new")
    report = viz.run_check("HEAD~1", ["*.qmd"], [], False)
    assert [f[0] for f in report.findings] == ["b.qmd"]


def test_whole_tree_flags_everything(repo):
    (repo / "a.qmd").write_text(NO_FIG)
    _git(repo, "add", "."), _git(repo, "commit", "-qm", "base")
    report = viz.run_check("", ["*.qmd"], [], True)
    assert [f[0] for f in report.findings] == ["a.qmd"]


def test_changed_solution_puts_its_exercise_in_scope(repo):
    (repo / "_exr-a.qmd").write_text(NO_FIG)
    (repo / "_sol-a.qmd").write_text("::: {#sol-a}\n@fig-p\n:::\n")
    _git(repo, "add", "."), _git(repo, "commit", "-qm", "base")
    (repo / "_sol-a.qmd").write_text("::: {#sol-a}\nNo figure now.\n:::\n")
    _git(repo, "add", "."), _git(repo, "commit", "-qm", "drop figure")
    report = viz.run_check("HEAD~1", ["*.qmd"], [], False)
    assert [f[0] for f in report.findings] == ["_exr-a.qmd"]


def test_no_base_ref_skips(repo):
    assert viz.run_check("", ["*.qmd"], [], False).skipped


def test_defaults_agree():
    assert viz._DEFAULT_FAIL is True
    action = (_DIR / "action.yml").read_text()
    assert "default: 'true'" in action
    assert "VIZ_FAIL" in action
