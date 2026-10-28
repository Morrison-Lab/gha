"""Unit tests for check-split-solutions.

Covers the pairing rule, part labels in a solution, the figure that answers a
sibling's question (the Boston lab case), what is not flagged (unsplit
exercises, numbered answer lists, code, the allow comment), and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_split_solutions", _DIR / "check-split-solutions.py"
)
assert _spec is not None and _spec.loader is not None
ssp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ssp)


def div(ident: str, body: str) -> str:
    return f"::: {{#{ident}}}\n\n{body}\n\n:::\n"


def findings(*files: str):
    """Messages for the divs in ``files`` (each file is one subfile)."""
    divs = []
    for i, text in enumerate(files):
        divs.extend(ssp.find_divs(f"f{i}.qmd", text.split("\n")))
    return [f.message for fs in ssp.check_groups(divs).values() for f in fs]


FIG = "```{python}\n#| label: fig-a\n#| fig-cap: A plot.\nplt.plot(x)\n```"


def test_fully_split_group_passes():
    assert findings(
        div("exr-a", "Fit a model."), div("sol-a", "Fitted."),
        div("exr-a-part2", "Predict."), div("sol-a-part2", "Predicted."),
    ) == []


def test_unsplit_exercise_is_not_a_group():
    assert findings(div("exr-a", "Fit it. Then predict."), div("sol-a", "Done.")) == []


def test_exercise_without_solution_is_flagged():
    out = findings(div("exr-a", "Fit."), div("sol-a", "Fitted."),
                   div("exr-a-part2", "Predict."))
    assert len(out) == 1 and "#exr-a-part2" in out[0] and "no #sol-a-part2" in out[0]


def test_solution_without_exercise_is_flagged():
    out = findings(div("exr-a", "Fit."), div("sol-a", "Fitted."),
                   div("exr-a-part2", "Predict."), div("sol-a-part2", "P."),
                   div("sol-a-part3", "Orphan."))
    assert len(out) == 1 and "#sol-a-part3" in out[0]


@pytest.mark.parametrize("body", [
    "(a) First.\n\n(b) Second.",
    "a. First.\n\nb. Second.",
    "**Part 2:** the second answer.",
    "Part 2. The second answer.",
])
def test_part_labels_in_a_solution_are_flagged(body):
    out = findings(div("exr-a", "Q."), div("sol-a", body),
                   div("exr-a-part2", "R."), div("sol-a-part2", "S."))
    assert len(out) == 1 and "labels several parts" in out[0]


def test_numbered_answer_list_is_not_a_part_label():
    assert findings(
        div("exr-a", "Name three."), div("sol-a", "1. One.\n2. Two.\n3. Three."),
        div("exr-a-part2", "Which count?"), div("sol-a-part2", "Two.")) == []


def test_prose_mentioning_parts_is_not_a_label():
    assert findings(
        div("exr-a", "Q."), div("sol-a", "Parts 2 and 3 reuse this."),
        div("exr-a-part2", "R."), div("sol-a-part2", "S.")) == []


def test_labels_inside_code_and_math_are_ignored():
    body = "```{r}\n# (a) first\n# (b) second\n```\n\n$$\n(a) + (b)\n$$"
    assert findings(div("exr-a", "Q."), div("sol-a", body),
                    div("exr-a-part2", "R."), div("sol-a-part2", "S.")) == []


def test_figure_for_a_sibling_exercise_is_flagged():
    out = findings(
        div("exr-a", "Fit the line."), div("sol-a", "Fitted.\n\n" + FIG),
        div("exr-a-part2", "Draw a scatter plot."), div("sol-a-part2", "See the figure."))
    assert len(out) == 1 and "sol-a draws a figure" in out[0]


def test_figure_in_the_solution_that_asks_for_it_passes():
    assert findings(
        div("exr-a", "Fit the line."), div("sol-a", "Fitted."),
        div("exr-a-part2", "Draw a scatter plot."),
        div("sol-a-part2", FIG)) == []


def test_figure_when_no_sibling_asks_for_a_plot_passes():
    assert findings(
        div("exr-a", "Fit the line."), div("sol-a", FIG),
        div("exr-a-part2", "Predict."), div("sol-a-part2", "P.")) == []


def test_allow_comment_exempts_a_solution():
    body = "<!-- split-solutions-ok: one combined figure -->\n(a) x\n\n(b) y"
    assert findings(div("exr-a", "Q."), div("sol-a", body),
                    div("exr-a-part2", "R."), div("sol-a-part2", "S.")) == []


def test_groups_are_kept_apart_by_slug():
    out = findings(
        div("exr-a", "Q."), div("sol-a", "A."),
        div("exr-a-part2", "R."), div("sol-a-part2", "B."),
        div("exr-b", "Q."), div("exr-c", "Q."))
    assert out == []


# -- diff scoping ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "exr.qmd").write_text(div("exr-a", "Q.") + div("exr-a-part2", "R."))
    (tmp_path / "sol.qmd").write_text(div("sol-a", "(a) x\n\n(b) y"))
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(whole_tree=False, base="HEAD"):
    return ssp.run_check(base, ["*.qmd"], [], whole_tree)


def test_old_violation_is_not_reflagged_in_diff_mode(repo):
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "other.qmd").write_text("Unrelated.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "other")
    assert run(base="main").findings == []


def test_touched_group_is_reported_in_diff_mode(repo):
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "exr.qmd").write_text(div("exr-a", "Q2.") + div("exr-a-part2", "R."))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "edit")
    report = run(base="main")
    assert {f.path for f in report.findings} == {"exr.qmd", "sol.qmd"}


def test_whole_tree_reports_everything(repo):
    assert len(run(whole_tree=True).findings) == 2  # no sol-a-part2, labels in sol-a


def test_no_base_ref_skips(repo):
    assert run(base="").skipped
