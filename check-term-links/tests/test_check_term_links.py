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
    def_words = {}
    for name, body in files.items():
        masked, _ = ctl.preprocess(body.splitlines())
        for k, ids in ctl.harvest_terms(masked, set()).items():
            terms.setdefault(k, set()).update(ids)
        for did, ws in ctl.harvest_def_words(masked).items():
            def_words.setdefault(did, set()).update(ws)
    rx = ctl.term_regex(list(terms)) if terms else None
    return ctl.scan_file(Path("page.qmd"), text.splitlines(), terms, rx, added, def_words)


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


LOGISTIC_DEFS = (
    "::: {#def-regression}\n\n#### Regression\n\nA **regression** predicts a value.\n\n:::\n"
    "\n::: {#def-logistic-regression}\n\n#### Logistic regression\n\n"
    "A **logistic regression** predicts a probability.\n\n:::\n"
)


def test_link_over_part_of_a_longer_defined_phrase_is_flagged():
    page = "::: {#exm-a}\n\nWe fit a logistic [regression](#def-regression).\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": LOGISTIC_DEFS})) == [
        ("partial-link", "logistic regression")
    ]


def test_link_over_the_leading_words_of_a_longer_phrase_is_flagged():
    page = "::: {#exm-a}\n\nWe fit a [logistic](#def-regression) regression.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": LOGISTIC_DEFS})) == [
        ("partial-link", "logistic regression")
    ]


def test_link_over_the_whole_longer_phrase_passes():
    page = "::: {#exm-a}\n\nWe fit a [logistic regression](#def-logistic-regression).\n\n:::\n"
    assert run_text(page, {"d.qmd": LOGISTIC_DEFS}) == []


def test_unlinked_longer_phrase_is_reported_as_the_phrase_not_its_tail():
    page = "::: {#exm-a}\n\nWe fit a logistic regression.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": LOGISTIC_DEFS})) == [
        ("unlinked-first-use", "logistic regression")
    ]


def test_shorter_term_alone_still_links_normally():
    page = "::: {#exm-a}\n\nA [regression](#def-regression) predicts.\n\n:::\n"
    assert run_text(page, {"d.qmd": LOGISTIC_DEFS}) == []


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
        "The risk. <!-- check-term-links: allow: test reason -->\n",
    ],
)
def test_non_prose_is_skipped(body):
    page = "::: {#exm-a}\n\n" + body + "\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_bare_allow_is_flagged_but_still_suppresses():
    page = "::: {#exm-a}\n\nThe risk is large. <!-- check-term-links: allow -->\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": RISK_DEF})) == [("bare-allow", "")]


def test_allow_with_an_empty_reason_is_bare():
    page = "::: {#exm-a}\n\nThe risk is large. <!-- check-term-links: allow:  -->\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": RISK_DEF})) == [("bare-allow", "")]


def test_allow_with_a_reason_is_clean():
    page = (
        "::: {#exm-a}\n\nThe risk is large. "
        "<!-- check-term-links: allow: risk here is ordinary English -->\n\n:::\n"
    )
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_allow_pragma_that_suppresses_nothing_is_stale():
    page = "::: {#exm-a}\n\nA plain sentence. <!-- check-term-links: allow: test reason -->\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": RISK_DEF})) == [("stale-allow", "")]


def test_allow_pragma_that_suppresses_a_finding_is_not_stale():
    page = "::: {#exm-a}\n\nThe risk is large. <!-- check-term-links: allow: test reason -->\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_stale_allow_is_scoped_to_added_lines():
    page = "::: {#exm-a}\n\nA plain sentence. <!-- check-term-links: allow: test reason -->\n\n:::\n"
    assert run_text(page, {"d.qmd": RISK_DEF}, added={1}) == []


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


TAYLOR_DEF = """\
:::{#def-linear-approximation}

#### Linear approximation (first-order Taylor approximation, first-order Taylor expansion)

The **linear approximation** (also called the **first-order Taylor expansion**) of $f$ is a line.

:::
"""


@pytest.fixture
def prereq_repo(tmp_path):
    """A repo whose page uses a term that only a prerequisite site defines."""
    site = tmp_path / "prereq-site"
    site.mkdir()
    (site / "calculus.qmd").write_text(TAYLOR_DEF)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "base.qmd").write_text("# Base\n\nText.\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "checkout", "-q", "-b", "pr")
    (repo / "ex.qmd").write_text(
        "::: {#exr-a}\n\nWrite the first-order Taylor expansion of the cost.\n\n:::\n"
    )
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "pr")
    return repo, site


def test_cli_terms_from_a_prerequisite_site_are_enforced(prereq_repo):
    repo, site = prereq_repo
    res = run_cli(repo, BASE_REF="main", FAIL="true", TERMS_DIRS=str(site))
    assert res.returncode == 1
    assert "ex.qmd:3" in res.stdout and "first-order taylor expansion" in res.stdout.lower()
    assert "calculus.qmd" not in res.stdout


def test_cli_without_terms_dirs_the_prerequisite_term_is_unknown(prereq_repo):
    repo, _ = prereq_repo
    res = run_cli(repo, BASE_REF="main", FAIL="true")
    assert res.returncode == 0


def test_cli_linked_prerequisite_term_passes(prereq_repo):
    repo, site = prereq_repo
    (repo / "ex.qmd").write_text(
        "::: {#exr-a}\n\nWrite the [first-order Taylor expansion](https://x.org/c.html#def-linear-approximation) of the cost.\n\n:::\n"
    )
    git(repo, "commit", "-q", "-am", "link")
    res = run_cli(repo, BASE_REF="main", FAIL="true", TERMS_DIRS=str(site))
    assert res.returncode == 0


def test_cli_missing_terms_dir_warns_and_continues(prereq_repo):
    repo, _ = prereq_repo
    res = run_cli(repo, BASE_REF="main", FAIL="true", TERMS_DIRS="/no/such/dir")
    assert res.returncode == 0 and "not found" in res.stderr


def test_function_words_and_generic_nouns_are_not_terms():
    # gha#1488: a prerequisite site tags "and", "not" and "number" as terms.
    for word in ("and", "not", "number", "values", "that", "also"):
        assert not ctl.usable_term(word, set()), word
    for word in ("therefore", "thus", "hence", "computes", "using"):  # gha#1498
        assert not ctl.usable_term(word, set()), word
    assert ctl.usable_term("risk", set())
    assert ctl.usable_term("test set", set())


def test_ordinary_words_defined_in_a_prerequisite_are_not_flagged():
    defs = (
        "::: {#def-conjunction}\n\n#### Conjunction\n\n"
        "A **conjunction** holds when both parts hold, written with **and**; "
        "a [number](#def-number) has a [value](#def-value).\n\n:::\n"
    )
    page = "::: {#exm-a}\n\nThe sum and the number of values are not equal.\n\n:::\n"
    assert run_text(page, {"d.qmd": defs}) == []


@pytest.mark.parametrize("div_id", ["sol-b", "exr-b", "exm-b", "thm-b", "prf-b"])
def test_worked_div_in_the_defining_file_is_checked(div_id):
    """gha#1316, gha#1539: a solution in the same file as the definition was never checked."""
    page = (
        RISK_DEF
        + f"\n::: {{#{div_id}}}\n\nThe risk is large here.\n\n:::\n"
    )
    assert rules(run_text(page)) == [("unlinked-first-use", "risk")]


def test_proof_class_div_in_the_defining_file_is_checked():
    page = RISK_DEF + "\n::: {.proof}\n\nThe risk is large here.\n\n:::\n"
    assert rules(run_text(page)) == [("unlinked-first-use", "risk")]


def test_source_callout_beside_the_definition_stays_exempt():
    page = RISK_DEF + "\n::: {#rem-source-risk}\n\nThe risk is defined as in the text.\n\n:::\n"
    assert run_text(page) == []


ENTROPY_DEF = """\
::: {#def-entropy}

#### Entropy

The **entropy** of a variable is its expected surprisal.

:::
"""


@pytest.mark.parametrize(
    "title,plural",
    [
        ("Entropy", "entropies"),
        ("Matrix", "matrices"),
        ("Hypothesis", "hypotheses"),
        ("Maximum", "maxima"),
        ("Criterion", "criteria"),
        ("Half", "halves"),
        ("Loss function", "loss functions"),
    ],
)
def test_irregular_plural_of_a_defined_term_is_flagged(title, plural):
    """gha#1630: only a trailing s or es used to count as a plural."""
    definition = f"::: {{#def-t}}\n\n#### {title}\n\nA **{title.lower()}** is x.\n\n:::\n"
    page = f"::: {{#sol-a}}\n\nAll finite {plural} are fine.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": definition})) == [("unlinked-first-use", title.lower())]


def test_a_linked_singular_covers_a_plural_in_the_same_div():
    page = "::: {#sol-a}\n\nThe [entropy](d.qmd#def-entropy) of two entropies.\n\n:::\n"
    assert run_text(page, {"d.qmd": ENTROPY_DEF}) == []


def test_parenthetical_alias_and_dashed_term_are_learned():
    """gha#1631: the title's parenthetical is an alias, and an en dash is part of a term."""
    definition = (
        "::: {#def-kl}\n\n#### Kullback\u2013Leibler divergence (KL divergence)\n\nx\n\n:::\n"
    )
    masked, _ = ctl.preprocess(definition.splitlines())
    assert set(ctl.harvest_terms(masked, set())) == {
        "kullback leibler divergence",
        "kl divergence",
    }
    page = "::: {#sol-a}\n\nThe KL divergence is large.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": definition})) == [("unlinked-first-use", "kl divergence")]


POSITIVE_DEF = """::: {#def-positive-classification}

a **positive classification**
(also called **positive**) is a prediction of the target class.

:::
"""


def test_one_word_alias_of_a_multiword_term_is_not_learned():
    """gha#1635: "positive" for "positive classification" is an ordinary adjective elsewhere."""
    masked, _ = ctl.preprocess(POSITIVE_DEF.splitlines())
    assert set(ctl.harvest_terms(masked, set())) == {"positive classification"}
    page = "::: {#exm-a}\n\nEvery value has positive probability.\n\n:::\n"
    assert run_text(page, {"d.qmd": POSITIVE_DEF}) == []
    page = "::: {#exm-a}\n\nThis is a positive classification.\n\n:::\n"
    assert rules(run_text(page, {"d.qmd": POSITIVE_DEF})) == [
        ("unlinked-first-use", "positive classification")
    ]


def test_link_text_still_teaches_a_one_word_alias():
    text = "See the [affirmative](https://x.github.io/sds/c.html#def-positive-classification).\n"
    masked, _ = ctl.preprocess((POSITIVE_DEF + text).splitlines())
    assert "affirmative" in ctl.harvest_terms(masked, set())


@pytest.mark.parametrize("title", ["sample mean, mean", "mean, sample mean", "sample mean or mean"])
def test_listed_alias_is_learned_in_either_order(title):
    """gha#1636: a plainly listed alias is a term whichever side of the multi-word term it sits."""
    definition = "::: {#def-m}\n\nThe **" + title + "** is x.\n\n:::\n"
    masked, _ = ctl.preprocess(definition.splitlines())
    assert {"mean", "sample mean"} <= set(ctl.harvest_terms(masked, set()))


def test_drop_sibling_moves_keeps_original_file_split(tmp_path):
    (tmp_path / "orig.qmd").write_text("Setup text for the risk.\n  - The risk was here.\nOnly here.\n")
    (tmp_path / "part.qmd").write_text("Setup text for the risk.\n1. The risk was here.\nBrand new line.\n")
    added = {tmp_path / "part.qmd": {1, 2, 3}}
    assert ctl.drop_sibling_moves(added) == {tmp_path / "part.qmd": {3}}


def test_drop_sibling_moves_ignores_other_directories(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "orig.qmd").write_text("Setup text for the risk.\n")
    (tmp_path / "sub" / "part.qmd").write_text("Setup text for the risk.\n")
    added = {tmp_path / "sub" / "part.qmd": {1}}
    assert ctl.drop_sibling_moves(added) == added


def test_drop_sibling_moves_ignores_lines_the_sibling_also_adds(tmp_path):
    (tmp_path / "a.qmd").write_text("A brand new sentence.\n")
    (tmp_path / "b.qmd").write_text("A brand new sentence.\n")
    added = {tmp_path / "a.qmd": {1}, tmp_path / "b.qmd": {1}}
    assert ctl.drop_sibling_moves(added) == added

MARGINAL_DEF = """
::: {#def-marginal-density}

#### Marginal density

The **marginal density** of a variable is its density with the others integrated out.

:::

::: {#def-fitted-value}

#### Fitted value

A **fitted value** is a model's prediction.

:::
"""


PDF_DEF = """
::: {#def-pdf}

#### Probability density function

A **probability density function** integrates to a probability.

:::
"""


def test_link_on_part_of_target_title_is_partial_link():
    page = "A [probability](d.qmd#def-pdf) density is used.\n"
    assert rules(run_text(page, {"d.qmd": PDF_DEF})) == [("partial-link", "probability")]


def test_link_before_a_defined_longer_phrase_is_reported_once():
    page = "A [marginal](d.qmd#def-marginal-density) density is used.\n"
    assert rules(run_text(page, {"d.qmd": MARGINAL_DEF})) == [("partial-link", "marginal density")]


def test_link_on_whole_target_title_is_clean():
    page = "A [marginal density](d.qmd#def-marginal-density) is used.\n"
    assert rules(run_text(page, {"d.qmd": MARGINAL_DEF})) == []


def test_following_word_outside_target_title_is_clean():
    page = "A [fitted](d.qmd#def-fitted-value) probability is used.\n"
    assert rules(run_text(page, {"d.qmd": MARGINAL_DEF})) == []


def test_partial_link_on_untouched_line_is_not_reported():
    page = "A [marginal](d.qmd#def-marginal-density) density estimate is used.\n"
    assert rules(run_text(page, {"d.qmd": MARGINAL_DEF}, added={5})) == []


def test_common_word_from_link_only_is_not_a_term():
    masked, _ = ctl.preprocess("See a [linear](https://x.io/m.html#def-linear-map) map.\n".splitlines())
    assert "linear" not in ctl.harvest_terms(masked, set())


def test_common_word_from_def_title_is_still_a_term():
    masked, _ = ctl.preprocess("::: {#def-linear}\n\n#### Linear\n\nA **linear** function.\n\n:::\n".splitlines())
    assert "linear" in ctl.harvest_terms(masked, set())


def test_uncommon_one_word_link_term_is_still_learned():
    masked, _ = ctl.preprocess("See the [estimator](https://x.io/m.html#def-estimator).\n".splitlines())
    assert "estimator" in ctl.harvest_terms(masked, set())


FENCE = "`" * 3


def test_a_code_fence_is_not_prose():
    page = f"{FENCE}\nThe risk is code.\n{FENCE}\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


@pytest.mark.parametrize("prefix", ["> ", ">", "> > ", "  > "])
def test_a_code_fence_inside_a_blockquote_is_not_prose(prefix):
    # gha#1905: the quote marker hid the fence, so the code was read as prose.
    page = f"{prefix}{FENCE}\n{prefix}The risk is code.\n{prefix}{FENCE}\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_a_lazy_line_stays_inside_a_quoted_fence():
    # Pandoc carries an unquoted line into a quoted fence as a lazy continuation,
    # so the fence still closes at the next quoted fence and the prose after it is read.
    page = f"> {FENCE}\n> code\nlazy\n> {FENCE}\n> The risk is prose.\n"
    assert [f.line for f in run_text(page, {"d.qmd": RISK_DEF})] == [5]


def test_a_blank_line_ends_a_quoted_fence():
    # The blank line ends the blockquote and clears the fence, so line 4 is prose,
    # even though a later unquoted fence pair follows.
    page = f"> {FENCE}\n> code\n\nThe risk is prose.\n\n{FENCE}\nx\n{FENCE}\n"
    assert [f.line for f in run_text(page, {"d.qmd": RISK_DEF})] == [4]


def test_a_line_blank_inside_a_shallower_quote_ends_a_quoted_fence():
    # ">" alone ends the inner ">>" quote and clears its fence, so line 3 is prose.
    page = f">> {FENCE}\n>\n>> The risk is prose.\n>> {FENCE}\n"
    assert [f.line for f in run_text(page, {"d.qmd": RISK_DEF})] == [3]


def test_a_line_blank_at_the_fence_depth_stays_code():
    # ">" alone inside a ">" fence is a blank code line, not the end of the quote.
    page = f"> {FENCE}\n>\n> The risk is code.\n> {FENCE}\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_a_quote_marker_inside_an_unquoted_fence_does_not_end_it():
    page = f"{FENCE}\ncode\n\nThe risk is code.\n> quoted code\n{FENCE}\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_a_quoted_fence_line_inside_an_unquoted_fence_does_not_close_it():
    # Pandoc keeps `> ```` inside an unquoted block as code.
    page = f"{FENCE}\ncode\n> {FENCE}\nThe risk is code.\n{FENCE}\n"
    assert run_text(page, {"d.qmd": RISK_DEF}) == []


def test_an_unquoted_fence_closes_a_quoted_one():
    # Pandoc reads a bare fence as closing a quoted one, so the next line is prose.
    page = f"> {FENCE}\n> code\n{FENCE}\nThe risk is after.\n"
    assert [f.line for f in run_text(page, {"d.qmd": RISK_DEF})] == [4]
