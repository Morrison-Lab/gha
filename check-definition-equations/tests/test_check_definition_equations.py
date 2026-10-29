"""Unit tests for check-definition-equations.

Covers what counts as more than the defining equation, what is not flagged, the
exemption comment, and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_definition_equations", _DIR / "check-definition-equations.py"
)
assert _spec is not None and _spec.loader is not None
de = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(de)


def div(body: str, ident: str = "def-a") -> str:
    return f"::: {{#{ident}}}\n\n#### Term\n\n{body}\n\n:::\n"


def msgs(text: str, touched=None):
    return [f.message for f in de.check_file("p.qmd", text.split("\n"), touched)]


def test_single_defining_equation_passes():
    assert msgs(div("The **term** is\n\n$$\nf \\eqdef g(x).\n$$")) == []


def test_single_equality_without_definer_passes():
    assert msgs(div("The **term** is\n\n$$\nf = g(x).\n$$")) == []


def test_equal_sign_inside_brackets_is_not_a_chain():
    body = "The **term** is\n\n$$\n\\sigma \\eqdef \\Var{\\epsilon \\mid X = x}.\n$$"
    assert msgs(div(body)) == []


def test_escaped_braces_group_like_brackets():
    for rhs in (r"\{x : f(x) = 0\}", r"\indicator\{X = x\}", r"\left\{ x = 1 \right\}"):
        body = "The **term** is\n\n$$\nS \\eqdef " + rhs + ".\n$$"
        assert msgs(div(body)) == [], rhs


def test_chain_after_definer_is_flagged():
    out = msgs(div("The **term** is\n\n$$\nf \\eqdef g(x) = h(x).\n$$"))
    assert len(out) == 1 and "#def-a" in out[0] and "chains" in out[0]


def test_colon_equals_chain_is_flagged():
    assert len(msgs(div("$$\nf := g = h\n$$"))) == 1


def test_chain_without_definer_is_flagged():
    assert len(msgs(div("$$\nf = g = h\n$$"))) == 1


def test_aligned_chain_is_flagged():
    body = "$$\n\\ba\nf &= g \\\\\n&= h\n\\ea\n$$"
    assert len(msgs(div(body))) == 1


def test_inequality_signs_are_not_equalities():
    assert msgs(div("$$\nf \\eqdef g \\le h, \\quad g \\ge 0 \\ne 1\n$$")) == []


def test_text_and_cases_are_ignored():
    body = ("$$\nf(x) \\eqdef \\begin{cases} 1 & x = 0 \\\\ 0 & x \\ne 0 "
            "\\end{cases}\n$$")
    assert msgs(div(body)) == []


def test_two_displays_are_flagged():
    out = msgs(div("$$\nf = g\n$$\n\nand\n\n$$\nh = k\n$$"))
    assert len(out) == 1 and "2 equations" in out[0]


def test_two_displays_each_with_a_definer_pass():
    assert msgs(div("$$\nf \\eqdef g\n$$\n\n$$\nh \\eqdef k\n$$")) == []


def test_equivalence_prose_is_flagged():
    out = msgs(div("The **term** is $f$, or equivalently $g$.\n\n$$\nf \\eqdef g\n$$"))
    assert len(out) == 1 and "equivalence" in out[0]


@pytest.mark.parametrize("phrase", [
    "In other words, it is g.", "It is equivalent to g.", "It is the same as g.",
    "It is also written g.", "It equals g, which equals h."])
def test_equivalence_phrases(phrase):
    assert len(msgs(div(f"The **term** is f. {phrase}"))) == 1


def test_phrase_inside_math_or_comment_is_not_flagged():
    body = "$$\n\\text{equivalently} \\eqdef g\n$$\n\n<!-- equivalently -->"
    assert msgs(div(body)) == []


def test_exemption_comment():
    body = "<!-- def-equiv-ok: the chain is the definition -->\n\n$$\nf \\eqdef g = h\n$$"
    assert msgs(div(body)) == []


def test_only_definition_divs_are_checked():
    text = div("$$\nf = g = h\n$$", ident="thm-a")
    assert msgs(text) == []


def test_code_fence_is_ignored():
    assert msgs(div("```\n$$\nf = g = h\n$$\n```")) == []


def test_untouched_div_is_skipped_and_touched_div_is_checked():
    text = div("$$\nf \\eqdef g = h\n$$")
    assert msgs(text, touched=set()) == []
    assert len(msgs(text, touched={5})) == 1


def test_finding_points_at_the_div_opening():
    f = de.check_file("p.qmd", div("$$\nf = g = h\n$$").split("\n"), None)[0]
    assert (f.path, f.line) == ("p.qmd", 1)
