"""Unit tests for check-self-contained-captions.

Covers which captions are found (div, chunk option, pipe table), what makes a
first sentence only a pointer, the exemption comment, code fences and
comments, and the diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_self_contained_captions", _DIR / "check-self-contained-captions.py"
)
assert _spec is not None and _spec.loader is not None
scc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scc)


def flagged(text: str):
    """Caption start lines flagged for a document string."""
    found, _ = scc.scan_file(text.split("\n"), None)
    return [line for line, _attrs, _reason in found]


def fig(caption: str, extra: str = "") -> str:
    return f"::: {{#fig-a}}\n\n```{{r}}\nplot(1)\n```\n{extra}\n{caption}\n:::\n"


def test_the_motivating_caption_is_flagged_and_names_the_dangling_word():
    doc = fig("The symmetry of @exm-logistic-symmetry.\nThe logistic function at -2 is as high as one minus its value at 2.")
    assert flagged(doc) == [7]
    reason = scc.first_sentence_problem("The symmetry of @exm-x.")
    assert reason is not None and "only 3 word" in reason


def test_a_dangling_preposition_is_flagged():
    cap = "The slope at the scores of @exm-logistic-derivative."
    assert "ends on 'of'" in scc.first_sentence_problem(cap)


@pytest.mark.parametrize("caption", [
    "The slope falls from its peak at 0 to near zero at 5, as in @exm-bound.",
    "The logistic function at -2 is as high as one minus its value at 2 (@exm-sym).",
    "Fitted line",
    "A scatter plot of height against weight.",
    "Two groups differ in their means [@smith2020, Fig. 2].",
    "Average percentage of words equal to each word (columns of Table 1.1 in @hastie2009esl).",
    "The residuals of the first five cars of @exm-residual.",
])
def test_self_contained_captions_pass(caption):
    assert scc.first_sentence_problem(caption) is None
    assert flagged(fig(caption)) == []


def test_a_caption_that_is_only_a_reference_is_flagged():
    assert flagged(fig("@exm-a.")) == [7]
    assert flagged(fig("See [@exm-a].")) == [7]


def test_a_table_title_ending_on_for_is_content_not_a_pointer():
    assert scc.first_sentence_problem("Estimated coefficients for [model @eq-lm]", table=True) is None
    assert scc.first_sentence_problem("Means of @tbl-a", table=True) is not None
    tbl = "::: {#tbl-a}\n| a |\n|---|\n| 1 |\n\nRegression estimates for [Model @eq-m]\n:::\n"
    assert flagged(tbl) == []


def test_a_link_keeps_its_text_but_drops_the_url():
    cap = "[Logistic function](https://x.org/a.html) of @exm-a."
    assert scc.first_sentence_problem(cap) is not None


def test_inline_code_is_not_a_reference():
    assert scc.first_sentence_problem("Mean of `r mean(x)` at the cutoff") is None


def test_only_the_first_sentence_counts():
    doc = fig("The symmetry of @exm-a. The curve is symmetric about zero.")
    assert flagged(doc) == [7]


def test_table_div_and_pipe_caption_and_chunk_option():
    tbl = "::: {#tbl-a}\n| a |\n|---|\n| 1 |\n\nMeans of @exm-a.\n:::\n"
    assert flagged(tbl) == [6]
    pipe = "| a |\n|---|\n| 1 |\n\n: Means of @exm-a {#tbl-b}\n"
    assert flagged(pipe) == [5]
    opt = "```{r}\n#| fig-cap: The slope at @exm-a\nplot(1)\n```\n"
    assert flagged(opt) == [2]


def test_exemption_needs_a_reason():
    cap = "The symmetry of @exm-a."
    assert flagged(fig(cap, "<!-- caption-ref: a deliberate pointer -->")) == []
    assert flagged(fig(cap, "<!-- caption-ref: -->")) == [7]


def test_nested_close_above_the_caption_means_no_caption():
    doc = "::: {#fig-a}\n\n::: {.panel-tabset}\ntext\n:::\n:::\n"
    assert flagged(doc) == []


def test_floats_in_code_fences_and_comments_are_ignored():
    fenced = "```markdown\n::: {#fig-a}\nThe symmetry of @exm-a.\n:::\n```\n"
    assert flagged(fenced) == []
    commented = "<!--\n::: {#fig-a}\nThe symmetry of @exm-a.\n:::\n-->\n"
    assert flagged(commented) == []


def test_diff_scope_only_reports_floats_holding_a_kept_line():
    doc = fig("The symmetry of @exm-a.")
    lines = doc.split("\n")
    found, seen = scc.scan_file(lines, {2})
    assert seen == 1 and len(found) == 1
    found, _ = scc.scan_file(lines, {50})
    assert found == []


# -- git: diff scoping end to end --------------------------------------------

BAD = "::: {#fig-a}\nplot\n\nThe symmetry of @exm-a.\n:::\n"


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
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)


def _commit(repo, name, text):
    _write(repo, name, text)
    _git(repo, "commit", "-q", "-m", "c")


def _run(base):
    return scc.run_check(base, [scc.DEFAULT_GLOBS], [], False)


def test_untouched_caption_is_grandfathered(repo):
    _commit(repo, "old.qmd", BAD)
    _write(repo, "other.qmd", "text\n")
    assert _run("HEAD").findings == []


def test_touching_a_float_flags_its_caption(repo):
    _commit(repo, "old.qmd", BAD)
    _write(repo, "old.qmd", BAD.replace("plot", "plot again"))
    assert [n for _, n, _, _ in _run("HEAD").findings] == [4]


def test_a_moved_line_is_not_new(repo):
    _commit(repo, "old.qmd", BAD + "\ntail\n")
    _write(repo, "old.qmd", "tail\n\n" + BAD)
    assert _run("HEAD").findings == []


def test_no_base_ref_skips_instead_of_scanning_the_tree(repo):
    _commit(repo, "old.qmd", BAD)
    report = _run("")
    assert report.skipped and report.findings == []


def test_unresolvable_base_ref_skips(repo):
    _commit(repo, "old.qmd", BAD)
    assert _run("no-such-ref").skipped


def test_whole_tree_and_paths_ignore(repo):
    _commit(repo, "old.qmd", BAD)
    report = scc.run_check("", [scc.DEFAULT_GLOBS], [], True)
    assert not report.skipped and len(report.findings) == 1
    assert (report.files, report.captions) == (1, 1)
    ignores = scc.ods.compile_ignores(["old.qmd"])
    assert scc.run_check("", [scc.DEFAULT_GLOBS], ignores, True).findings == []


def test_main_exit_codes(repo, monkeypatch):
    _commit(repo, "old.qmd", BAD)
    monkeypatch.setenv("SCC_WHOLE_TREE", "true")
    assert scc.main() == 1
    monkeypatch.setenv("SCC_FAIL", "false")
    assert scc.main() == 0


# -- defaults agree across script, action and workflow ----------------------

def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-self-contained-captions.yml").read_text(encoding="utf-8")
    assert scc._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("  fail:")[1].split("runs:")[0]
    assert "default: true" in workflow.split("      fail:")[1].split("jobs:")[0]
    assert f"default: '{scc.DEFAULT_GLOBS}'" in action
    assert f"default: '{scc.DEFAULT_GLOBS}'" in workflow
    for name in ("BASE_REF", "WHOLE_TREE", "GLOBS", "PATHS_IGNORE", "FAIL"):
        assert f"SCC_{name}" in action
