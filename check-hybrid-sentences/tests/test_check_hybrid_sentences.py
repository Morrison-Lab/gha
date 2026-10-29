"""Unit tests for check-hybrid-sentences.

Covers what counts as a hybrid sentence, what is not flagged, the exemption
comment, and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_hybrid_sentences", _DIR / "check-hybrid-sentences.py"
)
assert _spec is not None and _spec.loader is not None
hs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hs)


def msgs(text: str, touched=None):
    return [f.message for f in hs.check_file("p.qmd", text.split("\n"), touched)]


def test_words_then_math_condition_is_flagged():
    text = ("The reducible risk is zero if and only if "
            "$\\P(\\predfnf{\\Predvar} = \\E{\\Outvar \\mid \\Predvar}) = 1$.")
    out = msgs(text)
    assert len(out) == 1 and "hybrid" in out[0]


def test_comma_before_connective_is_flagged():
    assert msgs("The risk is zero, and $x = 1$.")
    assert msgs("The risk is zero, if and only if $x = 1$.")


def test_relation_inside_escaped_braces_is_not_flagged():
    assert not msgs(r"The set is nonempty if and only if $\{x : x = 1\}$ is nonempty.")


def test_math_condition_then_words_is_flagged():
    assert len(msgs("We have $f = g$ and the risk is zero everywhere.")) == 1


def test_or_connective_is_flagged():
    assert len(msgs("The sample is not empty or $n \\ge 1$ holds here.")) == 1


def test_two_sentences_pass():
    text = ("The reducible risk is zero if and only if the prediction function "
            "equals the conditional mean with probability 1.\n\n"
            "$$\nR = 0 \\iff \\P(f = g) = 1\n$$")
    assert msgs(text) == []


def test_single_inline_symbol_in_words_passes():
    text = "The prediction function $\\predfn$ equals the conditional mean and is unique."
    assert msgs(text) == []


def test_two_relations_joined_by_and_pass():
    assert msgs("Take a sample with $a = 1$ and $b = 2$ for the example.") == []


def test_relation_inside_brackets_is_not_a_relation():
    text = "The estimate is stable and $\\Var{\\epsilon \\mid X = x}$ is constant."
    assert msgs(text) == []


def test_command_prefix_is_not_a_relation():
    text = "The sample is nonempty and $\\left( a \\right)$ is large here."
    assert msgs(text) == []


def test_counter_example_mark_is_skipped():
    text = "> ❌ The risk is zero if and only if $f = g$."
    assert msgs(text) == []


def test_allow_comment_exempts():
    text = ("The risk is zero if and only if $f = g$. "
            "<!-- hybrid-ok: quoted from the source -->")
    assert msgs(text) == []


def test_code_fence_is_skipped():
    text = "```\nThe risk is zero if and only if $f = g$.\n```"
    assert msgs(text) == []


def test_only_touched_paragraphs_are_checked():
    text = ("Intro line one.\n\n"
            "The risk is zero if and only if $f = g$.\n\n"
            "Closing line.")
    assert len(msgs(text)) == 1
    assert msgs(text, touched={1}) == []
    assert len(msgs(text, touched={3})) == 1


def test_finding_reports_paragraph_start_line():
    text = "Intro.\n\nThe risk is zero if and only if $f = g$."
    findings = hs.check_file("p.qmd", text.split("\n"), None)
    assert [f.line for f in findings] == [3]


def test_membership_declaration_is_not_a_condition():
    text = "Let the sample be nonempty and $x \\in S$ for the example here."
    assert msgs(text) == []
