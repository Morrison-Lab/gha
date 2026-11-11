"""Unit tests for check-function-graphs.

Covers which definitions are candidates (the left-hand side, the arity and
the scalar-argument rule), what counts as a graph, the exemption comment and
its reason, diff scoping, the skip-not-fallback guard, and the defaults the
action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_function_graphs", _DIR / "check-function-graphs.py"
)
assert _spec is not None and _spec.loader is not None
fng = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fng)

NO_GRAPH = (
    "::: {#def-sigmoid}\n#### Sigmoid\n\nThe **sigmoid** is\n\n"
    "$$\n\\sigma(z) := \\frac{1}{1 + \\expf{-z}}.\n$$\n\n:::\n"
)


def missing(text: str):
    """(opening line, arity) of each candidate with no graph."""
    found, _ = fng.scan_file(text.split("\n"), None)
    return [(d.start, d.arity) for d in found]


def def_with(math: str) -> str:
    return f"::: {{#def-a}}\nText.\n\n$$\n{math}\n$$\n\n:::\n"


# -- which definitions are candidates ----------------------------------------

def test_one_input_definition_without_a_graph_is_flagged():
    assert missing(NO_GRAPH) == [(1, 1)]


@pytest.mark.parametrize("math, arity", [
    ("f(x) = x^2", 1),
    ("f(x, y) = x^2 + y^2", 2),
    ("L(\\beta_0, \\beta_1) = \\sum_i e_i^2", 2),
    ("\\relu\\paren{z} \\eqdef \\max(0, z)", 1),
    ("\\logitf{p} \\coloneqq \\logf{p / (1 - p)}", 1),
    ("F_X(x) = \\Pr(X \\le x)", 1),
    ("\\begin{aligned}\nS_\\tau(z) &= z - \\tau\n\\end{aligned}", 1),
    ("g\\left(t\\right) = t", 1),
])
def test_function_definitions_are_candidates(math, arity):
    assert defined_arity_of(math) == arity


@pytest.mark.parametrize("math", [
    "h(x, y, z) = x + y + z",
    "g(\\vx) = \\vx \\cdot \\vx",
    "\\det(\\mA) = 1",
    "\\Pr(A \\cup B) = \\Pr(A) + \\Pr(B)",
    "\\Pr(\\samplespace) = 1",
    "\\Pr(A) = 1",
    "\\E(X) = \\mu",
    "\\Pr(A, B) = \\Pr(A \\cap B)",
    "\\testset \\eqdef \\set{1, 2}",
    "e \\eqdef \\expf{1}",
    "\\forall x: f(x) = 0",
    "a \\star (b \\diamond c) = 0",
    "\\Var{X} = \\E{X^2}",
    "x + 1",
])
def test_non_function_definitions_are_not_candidates(math):
    assert defined_arity_of(math) is None


def defined_arity_of(math: str):
    return fng.defined_arity(math)


def test_only_definition_divs_are_checked():
    doc = NO_GRAPH.replace("#def-sigmoid", "#thm-sigmoid")
    assert missing(doc) == []


def test_definition_with_no_display_math_is_not_a_candidate():
    assert missing("::: {#def-a}\nThe sigmoid $\\sigma(z) = 1$.\n:::\n") == []


def test_math_inside_an_html_comment_is_not_the_defining_equation():
    doc = def_with("\\testset \\eqdef \\set{1}").replace(
        "Text.\n", "Text.\n<!--\n$$\nf(x) = x\n$$\n-->\n")
    assert missing(doc) == []


def test_only_the_first_display_equation_counts():
    doc = def_with("\\testset \\eqdef \\set{1}\n$$\n\n$$\nf(x) = x")
    assert missing(doc) == []


# -- what counts as a graph, and exemptions ----------------------------------

@pytest.mark.parametrize("figure", [
    "![Graph of the sigmoid](images/sigmoid.png)",
    "```{r}\n#| label: fig-sigmoid\ncurve(plogis, -5, 5)\n```",
    "See @fig-sigmoid.",
])
def test_figure_in_the_div_is_a_graph(figure):
    doc = NO_GRAPH.replace("\n\n:::\n", f"\n\n{figure}\n\n:::\n")
    assert missing(doc) == []


def test_figure_after_the_div_does_not_count():
    assert missing(NO_GRAPH + "\n![Graph](a.png)\n") == [(1, 1)]


def test_no_graph_comment_with_a_reason_exempts():
    doc = NO_GRAPH.replace("#### Sigmoid\n", "#### Sigmoid\n<!-- no-graph: defined on a finite set -->\n")
    assert missing(doc) == []


def test_no_graph_comment_without_a_reason_does_not_exempt():
    doc = NO_GRAPH.replace("#### Sigmoid\n", "#### Sigmoid\n<!-- no-graph: -->\n")
    assert missing(doc) == [(1, 1)]


def test_message_names_the_id_and_the_inputs():
    found, _ = fng.scan_file(def_with("f(x, y) = x y").split("\n"), None)
    msg = fng.format_message(found[0])
    assert "#def-a" in msg and "two inputs" in msg and "no-graph" in msg


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
    return fng.run_check(base, [fng.DEFAULT_GLOBS], [], False)


def test_untouched_definition_is_grandfathered(repo):
    _commit(repo, "old.qmd", NO_GRAPH)
    _write(repo, "other.qmd", "text\n")
    report = _run("HEAD")
    assert not report.skipped and report.findings == []


def test_new_definition_without_a_graph_is_flagged(repo):
    _commit(repo, "x.qmd", "text\n")
    _write(repo, "new.qmd", NO_GRAPH)
    assert [(f, d.start) for f, d in _run("HEAD").findings] == [("new.qmd", 1)]


def test_touching_an_old_definition_flags_it(repo):
    _commit(repo, "old.qmd", NO_GRAPH)
    _write(repo, "old.qmd", NO_GRAPH.replace("The **sigmoid**", "The **logistic sigmoid**"))
    assert [f for f, _ in _run("HEAD").findings] == ["old.qmd"]


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "old.qmd", NO_GRAPH)
    report = _run("")
    assert report.skipped and report.findings == []


def test_whole_tree_counts_candidates(repo):
    _commit(repo, "old.qmd", NO_GRAPH + "\n" + def_with("F_X(x) \\eqdef 1"))
    report = fng.run_check("", [fng.DEFAULT_GLOBS], [], True)
    assert (report.files, report.candidates, len(report.findings)) == (1, 2, 2)


def test_paths_ignore_is_honoured(repo):
    _commit(repo, "old.qmd", NO_GRAPH)
    ignores = fng.ods.compile_ignores(["old.qmd"])
    assert fng.run_check("", [fng.DEFAULT_GLOBS], ignores, True).findings == []


# -- defaults and exit codes --------------------------------------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-function-graphs.yml").read_text(encoding="utf-8")
    assert fng._DEFAULT_FAIL is False
    assert "default: 'false'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: false" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{fng.DEFAULT_GLOBS}'" in action
    assert f"default: '{fng.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"FNG_{name}" in action


def test_main_warns_by_default_and_fails_on_request(repo, monkeypatch, capsys):
    _commit(repo, "old.qmd", NO_GRAPH)
    monkeypatch.setenv("FNG_WHOLE_TREE", "true")
    assert fng.main() == 0
    assert "::warning file=old.qmd,line=1::" in capsys.readouterr().out
    monkeypatch.setenv("FNG_FAIL", "true")
    assert fng.main() == 1
    assert "::error file=old.qmd,line=1::" in capsys.readouterr().out
