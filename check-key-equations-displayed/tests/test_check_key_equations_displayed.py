"""Unit tests for check-key-equations-displayed.

Covers what is flagged (an inline equation in a proof that restates a displayed
equation of the theorem, or ends a concluding sentence), what is not (inline
symbols, equations outside a proof, display math, code, comments, the
inline-ok marker), diff scoping, and the defaults the script, the action and
the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_key_equations_displayed", _DIR / "check-key-equations-displayed.py"
)
assert _spec is not None and _spec.loader is not None
ked = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ked)

THEOREM = "::: {#thm-ne}\nThe normal equations are\n\n$$A x = b$$ {#eq-ne}\n:::\n"


def flagged(text: str):
    return [(n, why) for n, _, why in ked.inline_key_equations(text.split("\n"))]


def proof(body: str, opener: str = "::: proof") -> str:
    return f"{opener}\n{body}\n:::"


def test_restated_theorem_equation_is_flagged():
    text = THEOREM + "\n" + proof("Setting the gradient to zero gives $A x = b$.")
    assert flagged(text) == [(8, "restates a displayed equation of the theorem")]


def test_restated_ignores_spacing_and_sizing_and_label():
    text = THEOREM.replace("A x = b", r"\left( A \right) x = b") + "\n" + proof("So $(A)x=b$ holds.")
    assert [n for n, _ in flagged(text)] == [8]


def test_concluding_cue_before_equation_is_flagged():
    text = proof("The square is nonnegative, so $h \\ge 0$.")
    assert flagged(text) == [(2, "ends a concluding sentence")]


@pytest.mark.parametrize("cue", ["yields", "gives", "implies", "thus", "hence", "therefore", "forces"])
def test_each_cue_word_is_flagged(cue):
    assert len(flagged(proof(f"This {cue} $a = b$."))) == 1


def test_cue_on_next_line_is_flagged():
    text = proof("We have $a = b$.\nTherefore the claim holds.")
    assert [n for n, _ in flagged(text)] == [2]


def test_proof_by_id_is_checked():
    assert len(flagged(proof("so $a = b$.", opener="::: {#prf-x}"))) == 1
    assert len(flagged(proof("so $a = b$.", opener="::: {.proof}"))) == 1


@pytest.mark.parametrize("body", [
    "Let $x = 1$ and $y = 2$.",
    "Since $A$ is invertible, the matrix $A^{-1}$ exists.",
    "so $A$ is invertible.",
    "The result $a = b$ holds for every $x$ in the set.",
    "so $x \\in S$.",
    "Use `so $a = b$.` as an example.",
    "so\n\n$$a = b$$",
    "so $a = b$. <!-- inline-ok -->",
])
def test_not_flagged_inside_proof(body):
    assert flagged(proof(body)) == []


def test_equation_outside_proof_is_not_flagged():
    text = "::: {#exm-a}\nThis gives $a = b$.\n:::"
    assert flagged(text) == []
    assert flagged("So $a = b$.") == []


def test_display_math_in_proof_is_not_flagged_and_does_not_confuse_state():
    text = proof("so\n\n$$\nA x = b\n$$\n\nThen so $c = d$.")
    assert [n for n, _ in flagged(text)] == [8]


def test_code_fence_and_comment_skipped():
    assert flagged(proof("```\nso $a = b$.\n```")) == []
    assert flagged(proof("<!--\nso $a = b$.\n-->")) == []


def test_nested_div_in_proof_keeps_proof_scope():
    text = "::: proof\n::: {.callout-note}\nnote\n:::\nso $a = b$.\n:::"
    assert [n for n, _ in flagged(text)] == [5]
    assert flagged("::: proof\nok\n:::\nso $a = b$.") == []


def test_added_lines_scopes_a_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +2,2 @@\n+x\n+y\n+++ b/b.qmd\n@@ -3 +4 @@\n+z\n"
    assert ked.added_lines(diff) == {"a.qmd": {2, 3}, "b.qmd": {4}}


def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-key-equations-displayed.yml").read_text()
    assert "default: 'true'" in action and "default: true" in workflow
    assert "default: '*.qmd'" in action and "default: '*.qmd'" in workflow
    assert ked.DEFAULT_GLOBS == "*.qmd"
