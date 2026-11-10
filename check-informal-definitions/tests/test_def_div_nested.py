"""Unit tests for the nested-definition rule of check-informal-definitions.

psw: "don't nest definitions" (Morrison-Lab/psw#569, gha#1823).
A def div that names further terms inside its own statement, by an italic
label in parentheses, a labelled list item, or "is called *X*", is flagged.
"""

import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_informal_definitions", _DIR / "check-informal-definitions.py"
)
assert _spec is not None and _spec.loader is not None
check_defs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_defs)

scan = check_defs.scan_def_div_terms


def nested(lines, added=None):
    return [
        f.term
        for f in scan(Path("t.qmd"), lines, added)
        if f.rule == "nested-definition"
    ]


def div(*body):
    return ["::: {#def-x}", "", "#### X", "", *body, "", ":::"]


def test_italic_paren_labels_flagged():
    # The cited antipattern, mds def-linear-map before mds#711.
    lines = div(
        "A [function](f.qmd#def-function) $f$ is a **linear map** if:",
        "",
        "1. $f(x + y) = f(x) + f(y)$ (*additivity*)",
        "2. $f(cx) = c f(x)$ (*homogeneity*)",
    )
    assert nested(lines) == ["additivity, homogeneity"]


def test_underscore_paren_label_flagged():
    lines = div("A map is **linear** if $f(cx) = c f(x)$ (_homogeneity_).")
    assert nested(lines) == ["homogeneity"]


def test_bold_list_label_flagged():
    lines = div(
        "A **proof by induction** has two parts:",
        "",
        "1. **Base case:** $P(0)$ holds.",
        "2. **Inductive step.** $P(n)$ implies $P(n + 1)$.",
    )
    assert nested(lines) == ["Base case, Inductive step"]


def test_italic_list_label_flagged():
    lines = div(
        "A **recursive definition** has:",
        "",
        "- *Base case:* a value at $0$.",
    )
    assert nested(lines) == ["Base case"]


def test_is_called_italic_flagged():
    # A bold name after "called" is an alias, which rule 5 judges, not this one.
    lines = div("A **graph** is a pair of sets, also called a **network**.")
    assert nested(lines) == []
    lines = div(
        "A **graph** is a pair of sets $(V, E)$.",
        "Each element of $V$ is called a *vertex*.",
    )
    assert nested(lines) == ["vertex"]


def test_split_definition_passes():
    # The fix: the parent links sibling divs, and names nothing itself.
    lines = div(
        "A [function](f.qmd#def-function) $f$ is a **linear map**",
        "if it is both [additive](#def-additive) and [homogeneous](#def-homogeneous).",
    )
    assert nested(lines) == []


def test_emphasis_mid_sentence_passes():
    # Italic emphasis that is not a label in parentheses or a list label.
    lines = div("A **set** is *any* collection of [objects](o.qmd#def-object).")
    assert nested(lines) == []


def test_plain_list_item_passes():
    lines = div(
        "A **norm** satisfies:",
        "",
        "1. $f(x) \\ge 0$ for every $x$",
        "2. $f(cx) = |c| f(x)$",
    )
    assert nested(lines) == []


def test_label_inside_math_or_code_passes():
    lines = div("A **map** satisfies $g(*a*)$ and `(*b*)`.")
    assert nested(lines) == []


def test_label_in_nested_callout_passes():
    lines = [
        "::: {#def-x}",
        "",
        "#### X",
        "",
        "An **x** is a [thing](t.qmd#def-thing).",
        "",
        "::: {.callout-note}",
        "1. **Aside:** text (*note*).",
        ":::",
        "",
        ":::",
    ]
    assert nested(lines) == []


def test_outside_def_div_passes():
    lines = ["Some prose (*additivity*).", "", "1. **Base case:** text."]
    assert nested(lines) == []


def test_allow_directive_opts_out():
    lines = div(
        "A **map** is linear if $f(cx) = c f(x)$ (*homogeneity*). "
        "<!-- check-informal-definitions: allow -->",
    )
    assert nested(lines) == []


def test_labels_do_not_carry_into_the_next_div():
    first = div("A **map** is linear if $f(cx) = c f(x)$ (*homogeneity*).")
    second = div("A **set** is a [collection](c.qmd#def-collection).")
    lines = first + [""] + second
    assert nested(lines) == ["homogeneity"]
    assert nested(lines, added={len(first) + 5}) == []


def test_diff_scoped_untouched_div_passes():
    lines = div("A **map** is linear if $f(cx) = c f(x)$ (*homogeneity*).")
    assert nested(lines, added={99}) == []
    assert nested(lines, added={5}) == ["homogeneity"]
