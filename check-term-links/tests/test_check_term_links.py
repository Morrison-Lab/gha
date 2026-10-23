"""Tests for check-term-links.py: term harvesting, first-use scoping and diff scoping."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check-term-links.py"
spec = importlib.util.spec_from_file_location("check_term_links", SCRIPT)
ctl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ctl)

RISK_DEF = """\
::: {#def-risk}

#### Risk

The **risk** (also called **population risk**) of a rule is its expected loss.

:::
"""


def run_text(text, extra_files=None, added=None):
    """Findings for `text` as page.qmd, with `extra_files` (name -> text) in the corpus."""
    files = dict(extra_files or {})
    files["page.qmd"] = text
    terms = {}
    for name, body in files.items():
        masked, _ = ctl.preprocess(body.splitlines())
        for k, ids in ctl.harvest_terms(masked, set()).items():
            terms.setdefault(k, set()).update(ids)
    rx = ctl.term_regex(list(terms)) if terms else None
    return ctl.scan_file(Path("page.qmd"), text.splitlines(), terms, rx, added)


def rules(findings):
    return [(f.rule, f.term) for f in findings]


def test_harvest_title_bold_and_alias():
    masked, _ = ctl.preprocess(RISK_DEF.splitlines())
    terms = ctl.harvest_terms(masked, set())
    assert set(terms) == {"risk", "population risk"}
    assert terms["risk"] == {"def-risk"}


def test_harvest_from_link_to_def_anchor_on_another_site():
    text = "See the [validation set](https://x.github.io/sds/ch.html#def-validation-set).\n"
    masked, _ = ctl.preprocess(text.splitlines())
    assert "validation set" in ctl.harvest_terms(masked, set())


def test_unlinked_first_use_in_div_is_flagged():
    page = "::: {#exm-a}\n\nThe risk is large here.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": RISK_DEF})) == [("unlinked-first-use", "risk")]


def test_linked_first_use_passes_even_when_a_later_use_is_bare():
    page = "::: {#exm-a}\n\nThe [risk](#def-risk) is large; the risk shrinks.\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_crossref_counts_as_a_link():
    page = "::: {#exm-a}\n\nThe risk (@def-risk) is large.\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_only_the_first_use_is_reported_per_div():
    page = "::: {#exm-a}\n\nThe risk is large.\nThe risk is small.\n\n:::\n"
    assert len(run_text(page, {"d.qmd": RISK_DEF})) == 1


def test_each_div_starts_over():
    page = (
        "::: {#exm-a}\n\nThe [risk](#def-risk) is large.\n\n:::\n\n"
        "::: {#exm-b}\n\nThe risk is small.\n\n:::\n"
    )
    found = run_text(page, {"d.qmd": RISK_DEF})
    assert [f.line for f in found] == [9]


def test_each_paragraph_outside_a_div_starts_over():
    page = "The [risk](#def-risk) is large.\n\nThe risk is small.\n"
    assert [f.line for f in run_text(page, {"d.qmd": RISK_DEF})] == [3]


def test_a_terms_own_def_div_is_skipped():
    assert run_text(RISK_DEF) == []


def test_a_callout_in_the_same_file_as_the_def_div_is_skipped():
    page = RISK_DEF + "\n::: {.callout-note}\n\nThe risk was introduced in 1990.\n\n:::\n"
    assert rules(run_text(page)) == []


def test_prose_after_the_def_div_in_the_same_file_is_still_checked():
    page = RISK_DEF + "\nThe risk was introduced in 1990.\n"
    assert rules(run_text(page)) == [("unlinked-first-use", "risk")]


def test_source_label_is_not_a_term():
    kappa = "::: {#def-kappa}\n\n**Source**: a note on kappa.\n\n:::\n"
    page = "::: {#exm-a}\n\nSource of the data.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": kappa})) == []


def test_the_longer_term_wins_over_its_prefix():
    defs = RISK_DEF + "\n::: {#def-test-set}\n\n#### Test set\n\nA **test set** is held out.\n\n:::\n"
    defs += "\n::: {#def-set}\n\n#### Set\n\nA **set** is a collection.\n\n:::\n"
    page = "::: {#exm-a}\n\nThe [test set](#def-test-set) is held out.\n\n:::\n"
    assert run_text(page, {"d.qmd": defs}) == []


def test_plural_and_case_are_matched():
    page = "::: {#exm-a}\n\nRisks differ.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": RISK_DEF})) == [("unlinked-first-use", "risk")]


def test_a_word_inside_another_word_or_hyphenated_name_is_not_a_use():
    page = "::: {#exm-a}\n\nThe brisk walk and the risk-free rate.\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


@pytest.mark.parametrize(
    "body",
    [
        "Inline code `risk` here.\n",
        "Math $\\text{risk}$ here.\n",
        "<!-- risk -->\n",
        "```r\nrisk <- 1\n```\n",
        "![risk](fig.png)\n",
        "Link [elsewhere](https://x/risk.html).\n",
        "The risk. <!-- check-term-links: allow -->\n",
    ],
)
def test_non_prose_is_skipped(body):
    page = "::: {#exm-a}\n\n" + body + "\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_ignore_file_directive():
    page = "<!-- check-term-links: ignore-file -->\n\nThe risk is large.\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_bold_term_with_no_definition_is_flagged():
    page = "::: {#exm-a}\n\nThe **partial residual** is useful.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": RISK_DEF})) == [("no-definition", "partial residual")]


def test_bold_emphasis_and_labels_are_not_undefined_terms():
    page = "::: {#exm-a}\n\nDo **not** repeat. **Note:** here. **Example**\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_bold_term_defined_elsewhere_is_known():
    page = "::: {#exm-a}\n\nThe **risk** is [defined](#def-risk).\n\n:::\n"
    assert [f.rule for f in run_text(page, {"d.qmd": RISK_DEF})] == ["unlinked-first-use"]


def test_only_added_lines_are_reported():
    page = "::: {#exm-a}\n\nThe risk is large.\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}, added={99}) == []
    assert len(run_text(page, {"d.qmd": RISK_DEF}, added={3})) == 1


def test_glob_to_regex_matches_nested_paths():
    rx = ctl.glob_to_regex("chapters/outtakes/**")
    assert rx.match("chapters/outtakes/_a.qmd")
    assert not rx.match("chapters/a.qmd")


def test_defaults_agree_across_script_action_and_workflow():
    action = (SCRIPT.parent / "action.yml").read_text()
    workflow = (SCRIPT.parents[1] / ".github/workflows/check-term-links.yml").read_text()
    for text in (action, workflow):
        assert "default: '*.qmd'" in text
        assert "default: false" in text or "default: 'false'" in text
    assert ctl.DEFAULT_GLOBS == "*.qmd"


# End to end, in a throwaway git repository.


def git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def run_cli(repo, **env):
    full = {k: v for k, v in os.environ.items() if not k.startswith("TERM_LINKS_")}
    full.update({f"TERM_LINKS_{k}": v for k, v in env.items()})
    return subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=repo, env=full,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "d.qmd").write_text(RISK_DEF)
    (tmp_path / "old.qmd").write_text("::: {#exm-o}\n\nThe risk was here.\n\n:::\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "pr")
    (tmp_path / "new.qmd").write_text("::: {#exm-n}\n\nThe risk is new.\n\n:::\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "pr")
    return tmp_path


def test_cli_diff_scope_reports_only_the_pr(repo):
    res = run_cli(repo, BASE_REF="main", FAIL="true")
    assert res.returncode == 1
    assert "new.qmd:3" in res.stdout
    assert "old.qmd" not in res.stdout
    assert "::error file=new.qmd" in res.stdout


def test_cli_blocks_with_error_annotations_by_default(repo):
    res = run_cli(repo, BASE_REF="main")
    assert res.returncode == 1
    assert "::error file=new.qmd" in res.stdout


def test_cli_fail_false_warns_without_failing(repo):
    res = run_cli(repo, BASE_REF="main", FAIL="false")
    assert res.returncode == 0
    assert "::warning file=new.qmd" in res.stdout


def test_cli_no_base_skips_rather_than_scanning_the_whole_tree(repo):
    res = run_cli(repo, FAIL="true")
    assert res.returncode == 0
    assert "skipping" in res.stderr


def test_cli_whole_tree_reports_old_findings_too(repo):
    res = run_cli(repo, WHOLE_TREE="true", FAIL="true")
    assert res.returncode == 1
    assert "old.qmd:3" in res.stdout and "new.qmd:3" in res.stdout


def test_cli_allow_file_and_terms_file(repo):
    (repo / "allow.txt").write_text("# ordinary English here\nrisk\n")
    res = run_cli(repo, WHOLE_TREE="true", FAIL="true", ALLOW_FILE="allow.txt")
    assert res.returncode == 0
    (repo / "terms.txt").write_text("new thing\n")
    (repo / "t.qmd").write_text("::: {#exm-t}\n\nA new thing.\n\n:::\n")
    git(repo, "add", "t.qmd")
    res = run_cli(repo, WHOLE_TREE="true", FAIL="true", ALLOW_FILE="allow.txt", TERMS_FILE="terms.txt")
    assert res.returncode == 1 and "t.qmd:3" in res.stdout


def test_cli_paths_ignore(repo):
    res = run_cli(repo, WHOLE_TREE="true", FAIL="true", PATHS_IGNORE="old.qmd, new.qmd")
    assert res.returncode == 0


def test_cli_moved_line_is_not_new(repo):
    # Splitting a file moves lines; a first use the base already carried is not reflagged.
    text = (repo / "old.qmd").read_text()
    (repo / "moved.qmd").write_text(text)
    (repo / "old.qmd").write_text("Nothing left here.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "move")
    res = run_cli(repo, BASE_REF="main", FAIL="true")
    assert "moved.qmd" not in res.stdout and "new.qmd:3" in res.stdout


def test_cli_edited_line_with_the_same_first_use_is_still_flagged(repo):
    (repo / "old.qmd").write_text("::: {#exm-o}\n\nThe risk was here, and still is.\n\n:::\n")
    git(repo, "commit", "-q", "-am", "edit")
    res = run_cli(repo, BASE_REF="main", FAIL="true")
    assert "old.qmd:3" in res.stdout


def test_parse_added_lines_ignores_body_lines_that_look_like_headers(tmp_path):
    diff = (
        "diff --git a/a.qmd b/a.qmd\n--- a/a.qmd\n+++ b/a.qmd\n"
        "@@ -1,0 +2,2 @@\n++ not a header\n+++ b/also not a header\n"
    )
    assert ctl.parse_added_lines(diff, tmp_path) == {tmp_path / "a.qmd": {2, 3}}


def test_parse_added_lines_drops_lines_the_diff_also_deletes(tmp_path):
    diff = (
        "--- a/a.qmd\n+++ b/a.qmd\n@@ -3,1 +0,0 @@\n-The risk was here.\n"
        "--- a/b.qmd\n+++ b/b.qmd\n@@ -0,0 +1,2 @@\n+The risk was here.\n+A new line.\n"
    )
    out = ctl.parse_added_lines(diff, tmp_path)
    assert out[tmp_path / "b.qmd"] == {2}
