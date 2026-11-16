r"""Unit tests for check-corollary-sources.

Fixtures: a corollary that cites a result in its statement, in a nested proof,
in a following proof, and in a proof inside a wrapper div; a link to a result
anchor; a corollary that cites nothing, only itself, only a definition, or
only a result inside a comment or code fence (flagged); the opt-out comment,
with and without a reason; other div kinds; and diff scoping.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_corollary_sources", _DIR / "check-corollary-sources.py")
assert _spec is not None and _spec.loader is not None
ccs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccs)


def cor(body="By @thm-pythagoras, the diagonal is $\\sqrt{2}$.", kind="cor"):
    return f"::: {{#{kind}-a}}\n{body}\n:::\n"


def run(text: str, touched=None):
    return ccs.check_file("a.qmd", text.split("\n"), touched)


@pytest.mark.parametrize("ref", ["@thm-x", "@lem-x", "@cor-x", "@prp-x", "[@thm-x]"])
def test_cross_reference_to_a_result_counts(ref):
    assert run(cor(body=f"By {ref}, it holds.")) == []


@pytest.mark.parametrize("target", [
    "#thm-x",
    "algebra.qmd#lem-x",
    "https://morrison-lab.github.io/pds/expectation.html#prp-x",
])
def test_link_to_a_result_anchor_counts(target):
    assert run(cor(body=f"By [the rule]({target}), it holds.")) == []


def test_corollary_citing_nothing_is_flagged():
    findings = run(cor(body="The diagonal of a unit square is $\\sqrt{2}$."))
    assert len(findings) == 1
    assert "#cor-a" in findings[0].message
    assert findings[0].line == 1


def test_citing_only_itself_is_flagged():
    assert len(run(cor(body="See @cor-a and [it](#cor-a)."))) == 1


@pytest.mark.parametrize("body", [
    "By @def-square, it holds.",
    "By @exr-square and @sol-square, it holds.",
    "By the complement rule, it holds.",
])
def test_citing_a_non_result_is_flagged(body):
    assert len(run(cor(body=body))) == 1


def test_handle_or_path_with_at_sign_is_not_a_reference():
    assert len(run(cor(body="Mail name@thm-x or see a/@thm-x."))) == 1


def test_citation_in_a_comment_or_fence_does_not_count():
    body = "<!-- @thm-x -->\n```\n@thm-x\n```\nIt holds."
    assert len(run(cor(body=body))) == 1


def test_nested_proof_citation_counts():
    body = "It holds.\n\n::: proof\nBy @thm-x.\n:::"
    assert run(cor(body=body)) == []


def test_following_proof_citation_counts():
    text = cor(body="It holds.") + "\n\n::: proof\nBy @thm-x.\n:::\n"
    assert run(text) == []


def test_braced_following_proof_counts():
    text = cor(body="It holds.") + "\n::: {.proof}\nBy @thm-x.\n:::\n"
    assert run(text) == []


def test_proof_inside_a_following_wrapper_counts():
    text = (cor(body="It holds.")
            + "\n::: {.content-hidden when-format=\"revealjs\"}\n\n"
            "::: proof\nBy @thm-x.\n:::\n\n:::\n")
    assert run(text) == []


def test_following_result_div_is_not_a_proof():
    text = cor(body="It holds.") + "\n::: {#exm-b}\nBy @thm-x.\n:::\n"
    assert len(run(text)) == 1


def test_proof_after_other_text_does_not_count():
    text = cor(body="It holds.") + "\nSome prose.\n\n::: proof\nBy @thm-x.\n:::\n"
    assert len(run(text)) == 1


def test_wrapper_with_no_proof_does_not_count():
    text = cor(body="It holds.") + "\n::: {.callout-note}\nBy @thm-x.\n:::\n"
    assert len(run(text)) == 1


def test_allow_with_reason_exempts():
    body = "<!-- check-corollary-sources: allow: follows from the definition -->\nIt holds."
    assert run(cor(body=body)) == []


def test_allow_in_following_proof_exempts():
    text = (cor(body="It holds.")
            + "\n::: proof\n<!-- check-corollary-sources: allow: from the axioms -->\n:::\n")
    assert run(text) == []


@pytest.mark.parametrize("pragma", [
    "<!-- check-corollary-sources: allow -->",
    "<!-- check-corollary-sources: allow: -->",
])
def test_allow_without_reason_does_not_exempt(pragma):
    assert len(run(cor(body=f"{pragma}\nIt holds."))) == 1


@pytest.mark.parametrize("kind", ["thm", "lem", "prp", "def", "exm"])
def test_other_div_kinds_are_not_checked(kind):
    assert run(cor(body="It holds.", kind=kind)) == []


def test_corollary_in_a_code_fence_is_not_checked():
    assert run("```\n" + cor(body="It holds.") + "```\n") == []


def test_untouched_corollary_is_skipped():
    text = "Intro.\n\n" + cor(body="It holds.")
    assert run(text, touched={1}) == []
    assert len(run(text, touched={4})) == 1


def test_touched_following_proof_checks_the_corollary():
    text = cor(body="It holds.") + "\n::: proof\nA step.\n:::\n"
    assert len(run(text, touched={6})) == 1
    assert run(text, touched={9}) == []
