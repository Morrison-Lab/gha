"""Unit tests for check-solution-citations (gha#1234).

The regression case is Ezra's lds review comment (2026-10-26): the proof of
``thm-logistic-symmetry`` cited two solutions ("By Solution 9 and Solution 10")
instead of a result div.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_solution_citations", _DIR / "check-solution-citations.py"
)
assert _spec is not None and _spec.loader is not None
csc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csc)


def hits(text: str):
    return [(f.line, f.ref) for f in csc.scan_proofs(text.split("\n"))]


LDS_LOGISTIC = """::: {#thm-logistic-symmetry}
For every $z$, the logistic function satisfies a symmetry.
:::

::: proof
By @sol-sigmoid-properties-part2 and @sol-sigmoid-properties-part3.
:::"""


def test_regression_lds_logistic_symmetry_is_flagged():
    assert hits(LDS_LOGISTIC) == [(6, "@sol-sigmoid-properties-part2")]


@pytest.mark.parametrize("opener", [
    "::: proof", "::: {.proof}", "::: {#thm-x}", "::: {#lem-x}",
    "::: {#cor-x}", "::: {#prp-x}",
])
def test_each_scope_is_flagged(opener):
    assert hits(f"{opener}\nBy @sol-a.\n:::") == [(2, "@sol-a")]


def test_a_reference_outside_proofs_and_results_is_fine():
    assert hits("::: {#sol-b}\nAs in @sol-a.\n:::") == []
    assert hits("::: {#rem-x}\nSee @sol-a.\n:::") == []
    assert hits("::: {#exm-x}\nSee @sol-a.\n:::") == []
    assert hits("By @sol-a.") == []


def test_citing_a_result_div_is_fine():
    assert hits("::: proof\nBy @lem-a and @thm-b.\n:::") == []


def test_allow_marker_exempts_the_line():
    text = "::: proof\nBy @sol-a. <!-- check-solution-citations: allow -->\n:::"
    assert hits(text) == []


def test_solution_to_exercise_wording_is_the_exception():
    text = "::: {#thm-x}\nThis is the solution to @exr-x: see @sol-x.\n:::"
    assert hits(text) == []


def test_answer_to_exercise_wording_is_the_exception():
    text = "::: proof\nThis is the answer to @exr-x: see @sol-x.\n:::"
    assert hits(text) == []


def test_exception_wording_excuses_only_the_matching_slug():
    text = "::: proof\nThis is the solution to @exr-x, not @sol-y.\n:::"
    assert hits(text) == [(2, "@sol-y")]


def test_exception_wording_reads_a_bracketed_crossref():
    text = "::: proof\nThis is the solution to [@exr-x]; see @sol-x.\n:::"
    assert hits(text) == []


def test_proof_in_a_quoted_attribute_is_not_a_scope():
    text = '::: {#sol-1 title="Alternative proof" data-for="#thm-1"}\nSee @sol-a.\n:::'
    assert hits(text) == []


def test_an_email_address_is_not_a_solution_reference():
    text = "::: proof\nWrite to help@sol-lab.org.\n:::"
    assert hits(text) == []


def test_unspaced_dashes_do_not_join_the_slug():
    text = "::: proof\nThe solution to @exr-a---see @sol-a.\n:::"
    assert hits(text) == []


def test_chained_classes_still_scope_the_div():
    text = "::: {.proof.unlisted}\nSee @sol-a.\n:::"
    assert hits(text) == [(2, "@sol-a")]


def test_nested_div_inside_a_proof_is_read():
    text = "::: proof\n::: {.callout-note}\nSee @sol-a.\n:::\n:::"
    assert hits(text) == [(3, "@sol-a")]


def test_div_after_the_proof_closes_is_not_read():
    text = "::: proof\nBy @lem-a.\n:::\n\n::: {#sol-b}\nSee @sol-a.\n:::"
    assert hits(text) == []


def test_code_fence_math_comment_and_inline_code_are_skipped():
    text = "\n".join([
        "::: proof",
        "```r",
        "# @sol-a",
        "```",
        "$$",
        "@sol-b",
        "$$",
        "<!-- @sol-c -->",
        "Write `@sol-d` literally.",
        ":::",
    ])
    assert hits(text) == []


def test_proof_word_inside_an_id_is_not_a_scope():
    assert hits("::: {#rem-proofs}\nSee @sol-a.\n:::") == []


def test_parse_diff_scopes_to_added_lines():
    diff = (
        "diff --git a/a.qmd b/a.qmd\n--- a/a.qmd\n+++ b/a.qmd\n"
        "@@ -1,0 +2,1 @@\n+By @sol-a.\n"
    )
    added, deleted = csc.parse_diff(diff)
    assert added == {"a.qmd": {2: "By @sol-a."}}
    assert deleted == set()


def test_defaults_agree_between_script_and_action():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    assert csc._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("fail:")[1]
    assert csc.DEFAULT_GLOBS == "*.qmd"
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-solution-citations.yml").read_text(encoding="utf-8")
    assert "default: true" in workflow.split("fail:")[1]
    assert "default: '*.qmd'" in workflow.split("globs:")[1]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", *args], check=True,
                   stdout=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.qmd").write_text("::: proof\nBy @lem-a.\n:::\n")
    _git(tmp_path, "add", "a.qmd")
    _git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_run_check_flags_an_added_citation(repo):
    (repo / "a.qmd").write_text("::: proof\nBy @lem-a.\nAnd @sol-b.\n:::\n")
    report = csc.run_check("HEAD", ["*.qmd"], [], False)
    assert [(p, f.line) for p, f in report.findings] == [("a.qmd", 3)]


def test_run_check_ignores_a_citation_the_pr_did_not_add(repo):
    (repo / "a.qmd").write_text("::: proof\nBy @sol-b.\n:::\n")
    _git(repo, "commit", "-q", "-am", "old citation")
    (repo / "a.qmd").write_text("::: proof\nBy @sol-b.\nThen done.\n:::\n")
    assert csc.run_check("HEAD", ["*.qmd"], [], False).findings == []


def test_run_check_exempts_a_moved_line(repo):
    (repo / "a.qmd").write_text("::: proof\nBy @sol-b.\n:::\n")
    _git(repo, "commit", "-q", "-am", "citation")
    (repo / "a.qmd").write_text("::: proof\nFirst.\nBy @sol-b.\n:::\n")
    assert csc.run_check("HEAD", ["*.qmd"], [], False).findings == []


def test_run_check_whole_tree_reads_existing_citations(repo):
    (repo / "a.qmd").write_text("::: proof\nBy @sol-b.\n:::\n")
    _git(repo, "commit", "-q", "-am", "citation")
    report = csc.run_check("", ["*.qmd"], [], True)
    assert [(p, f.line) for p, f in report.findings] == [("a.qmd", 2)]


def test_run_check_skips_an_unresolvable_base(repo):
    assert csc.run_check("no-such-ref", ["*.qmd"], [], False).skipped


def test_run_check_skips_an_empty_base(repo):
    assert csc.run_check("", ["*.qmd"], [], False).skipped
