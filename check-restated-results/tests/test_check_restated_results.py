"""Unit tests for check-restated-results.

Covers what counts as a derivation, where the theorem may sit (a later subfile,
after a split group), what is not flagged, and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_restated_results", _DIR / "check-restated-results.py"
)
assert _spec is not None and _spec.loader is not None
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)

EQ = "$$\nx = 1\n$$"


def div(ident: str, body: str) -> str:
    return f"::: {{#{ident}}}\n\n{body}\n\n:::\n\n"


def msgs(text: str):
    stream = rr.flatten("p.qmd", {"p.qmd": text.split("\n")})
    return [f.message for f in rr.check_page(stream, None)]


def test_derivation_without_theorem_is_flagged():
    out = msgs(div("exr-a", "Derive the mean.") + div("sol-a", EQ))
    assert len(out) == 1 and "#sol-a" in out[0]


@pytest.mark.parametrize("kind", ["thm", "lem", "cor", "prp"])
def test_restating_div_after_the_exercise_passes(kind):
    assert msgs(div("exr-a", "Derive the mean.") + div("sol-a", EQ)
                + div(f"{kind}-a", "The mean is 1.")) == []


@pytest.mark.parametrize("ask", [
    "Prove that it holds.", "Show that x is 1.", "Solve for x.",
    "Find an expression for x.", "Simplify the sum.", "Express y in terms of x."])
def test_derivation_verbs_are_recognized(ask):
    assert len(msgs(div("exr-a", ask) + div("sol-a", EQ))) == 1


def test_solution_without_display_math_is_not_a_derivation():
    assert msgs(div("exr-a", "Derive the mean.") + div("sol-a", "It is one.")) == []


def test_data_exercise_is_not_a_derivation():
    assert msgs(div("exr-a", "Fit the model to the data.") + div("sol-a", EQ)) == []


def test_exercise_citing_a_stated_result_is_a_proof_not_a_derivation():
    assert msgs(div("exr-a", "Prove @thm-mean.") + div("sol-a", EQ)) == []


def test_allow_comment_exempts():
    assert msgs(div("exr-a", "Derive it.")
                + div("sol-a", "<!-- restated-ok: stated above -->\n" + EQ)) == []


def test_next_exercise_of_another_group_ends_the_window():
    out = msgs(div("exr-a", "Derive it.") + div("sol-a", EQ)
               + div("exr-b", "Fit a model.") + div("thm-b", "T."))
    assert len(out) == 1


def test_split_group_may_restate_after_its_last_solution():
    assert msgs(div("exr-a", "Derive it.") + div("sol-a", EQ)
                + div("exr-a-part2", "Show that y.") + div("sol-a-part2", EQ)
                + div("thm-a", "T.")) == []


def test_theorem_before_the_exercise_does_not_count():
    assert len(msgs(div("thm-a", "T.") + div("exr-a", "Derive it.") + div("sol-a", EQ))) == 1


def test_theorem_in_a_later_subfile_counts():
    files = {
        "page.qmd": "{{< include _s/_exr.qmd >}}\n\n{{< include _s/_sol.qmd >}}\n\n"
                    "{{< include _s/_thm.qmd >}}\n".split("\n"),
        "_s/_exr.qmd": div("exr-a", "Derive it.").split("\n"),
        "_s/_sol.qmd": div("sol-a", EQ).split("\n"),
        "_s/_thm.qmd": div("thm-a", "T.").split("\n"),
    }
    assert rr.check_page(rr.flatten("page.qmd", files), None) == []
    del files["_s/_thm.qmd"]
    files["page.qmd"] = files["page.qmd"][:-2]
    assert len(rr.check_page(rr.flatten("page.qmd", files), None)) == 1


def test_include_inside_a_code_fence_is_not_expanded():
    files = {"p.qmd": "```\n{{< include q.qmd >}}\n```".split("\n"), "q.qmd": ["x"]}
    assert len(rr.flatten("p.qmd", files)) == 3


# -- diff scoping ------------------------------------------------------------

def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "p.qmd").write_text(div("exr-a", "Derive it.") + div("sol-a", EQ))
    (tmp_path / "q.qmd").write_text("Prose.\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(whole_tree=False, base="HEAD"):
    return rr.run_check(base, ["*.qmd"], [], whole_tree)


def test_old_violation_is_not_reflagged_in_diff_mode(repo):
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "q.qmd").write_text("Other.\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "other")
    assert run(base="main").findings == []


def test_whole_tree_reports_the_old_violation(repo):
    assert len(run(whole_tree=True).findings) == 1


def test_edited_solution_is_reported_in_diff_mode(repo):
    _git(repo, "checkout", "-q", "-b", "pr")
    (repo / "p.qmd").write_text(div("exr-a", "Derive it.") + div("sol-a", EQ + "\nMore."))
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "edit")
    assert len(run(base="main").findings) == 1


def test_no_base_skips(repo):
    assert run(base="").skipped


def test_warn_only_by_default(repo, monkeypatch, capsys):
    monkeypatch.setenv("RR_WHOLE_TREE", "true")
    assert rr.main() == 0
    assert "::warning" in capsys.readouterr().out
    monkeypatch.setenv("RR_FAIL", "true")
    assert rr.main() == 1
