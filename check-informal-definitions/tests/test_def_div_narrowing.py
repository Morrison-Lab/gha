"""Tests for the narrowing of two def-div rules of check-informal-definitions (gha#1482)."""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_informal_definitions", _DIR / "check-informal-definitions.py"
)
assert _spec is not None and _spec.loader is not None
check_defs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_defs)


@pytest.fixture(autouse=True)
def reset_defined_stems():
    check_defs.DEFINED_STEMS = None
    yield
    check_defs.DEFINED_STEMS = None


def rules(lines):
    return [f.rule for f in check_defs.scan_def_div_terms(Path("t.qmd"), lines, None)]


FOUNDATION = [
    "::: {#def-unit}",
    "#### Unit",
    "A **unit** is a thing that is counted.",
    ":::",
]


def test_without_a_corpus_every_unlinked_def_is_flagged():
    assert rules(FOUNDATION) == ["no-link-in-definition"]


def test_unlinked_def_using_no_defined_term_is_not_flagged():
    check_defs.DEFINED_STEMS = {"gradi"}
    assert rules(FOUNDATION) == []


def test_unlinked_def_using_a_defined_term_is_flagged():
    check_defs.DEFINED_STEMS = {"count"}
    assert rules(FOUNDATION) == ["no-link-in-definition"]


def test_the_divs_own_title_does_not_count_as_a_defined_term():
    check_defs.DEFINED_STEMS = {"count"}
    lines = ["::: {#def-count}", "#### Counted", "A **counted** thing is a counted item.", ":::"]
    assert rules(lines) == []


def test_defined_title_stems_reads_titles_and_title_attributes():
    corpus = [["::: {#def-a}", "#### Gradient descent", ":::"],
              ['::: {#def-b title="Learning rate"}', ":::"]]
    assert check_defs.defined_title_stems(corpus) == {"gradi", "desce", "learn"}


@pytest.mark.parametrize("cue", ["Other names:", "Synonyms:", "Also called"])
def test_a_list_of_aliases_after_a_cue_is_one_term(cue):
    lines = ["::: {#def-a}", "#### Anomaly detection",
             "**Anomaly detection** flags [inputs](x.qmd#def-i).",
             f"{cue} **novelty detection**, **outlier detection**.", ":::"]
    assert "multiple-terms-in-definition" not in rules(lines)


def test_two_new_terms_without_a_cue_are_still_flagged():
    lines = ["::: {#def-a}", "#### Pair", "A **slope** and an **intercept** [x](y.qmd#def-z).", ":::"]
    assert "multiple-terms-in-definition" in rules(lines)


def test_a_variant_of_a_counted_term_is_not_a_second_term():
    lines = ["::: {#def-a}", "#### Convergence",
             "A sequence **converges** to $L$ if [its terms](x.qmd#def-t) approach $L$.",
             "Such a sequence is **convergent**.", ":::"]
    assert "multiple-terms-in-definition" not in rules(lines)


def test_a_term_that_adds_a_word_is_not_a_variant():
    lines = ["::: {#def-a}", "#### Descent",
             "**Gradient descent** follows [the gradient](x.qmd#def-g).",
             "**Stochastic gradient descent** samples [a batch](x.qmd#def-b).", ":::"]
    assert "multiple-terms-in-definition" in rules(lines)
