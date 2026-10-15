"""Unit tests for the one-term-per-definition-div rule of check-informal-definitions."""

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


def rules(lines, added=None):
    return [f.rule for f in scan(Path("t.qmd"), lines, added)]


def test_one_term_passes():
    lines = [
        "::: {#def-odds}",
        "",
        "#### Odds",
        "",
        "The **odds** of an event are p / (1 - p).",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_two_bold_terms_flagged():
    lines = [
        "::: {#def-odds}",
        "",
        "#### Odds",
        "",
        "The **odds** of an event are p / (1 - p),",
        "and the **log-odds** are their logarithm.",
        "",
        ":::",
    ]
    assert rules(lines) == ["multiple-terms-in-definition"]


def test_alias_after_cue_is_not_a_second_term():
    lines = [
        "::: {#def-log-odds}",
        "",
        "#### Log-odds (also called the logit)",
        "",
        "The **log-odds**, also called the **logit**, are log(odds).",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_alias_with_or_cue_is_not_a_second_term():
    lines = [
        "::: {#def-ppv}",
        "",
        "#### Precision (also called positive predictive value)",
        "",
        "**Precision**, or **positive predictive value**, is TP / (TP + FP).",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_title_joining_two_words_is_not_a_finding():
    # "Branch and bound" is one technique, so a title is never counted.
    lines = [
        "::: {#def-bnb}",
        "",
        "#### Branch and bound",
        "",
        "The **branch and bound** method prunes the search tree.",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_labels_and_colon_terms_ignored():
    lines = [
        "::: {#def-x}",
        "",
        "#### X",
        "",
        "The **x** is defined here. **Note:** see also **Figure 1**.",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_non_definition_div_ignored():
    lines = [
        "::: {#exm-x}",
        "",
        "#### X",
        "",
        "The **alpha** and the **beta**.",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_opt_out_comment_exempts_div():
    lines = [
        "::: {#def-x}",
        "",
        "#### X",
        "",
        "<!-- check-informal-definitions: allow -->",
        "The **alpha** and the **beta**.",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_nested_div_does_not_end_definition_early():
    lines = [
        "::: {#def-x}",
        "",
        "#### X",
        "",
        "The **alpha** holds.",
        "",
        ":::: {.callout-note}",
        "Inside.",
        "::::",
        "",
        "Also the **beta**.",
        "",
        ":::",
    ]
    assert rules(lines) == ["multiple-terms-in-definition"]


def test_diff_scope_skips_untouched_div():
    lines = [
        "::: {#def-x}",
        "",
        "#### X",
        "",
        "The **alpha** and the **beta**.",
        "",
        ":::",
    ]
    assert rules(lines, added={99}) == []
    assert rules(lines, added={1}) == ["multiple-terms-in-definition"]


def div(*body):
    return ["::: {#def-x}", "", "#### X", "", *body, "", ":::"]


def test_repeated_term_counts_once():
    assert rules(div("The **odds** are p / (1 - p). Again, the **Odds** are...")) == []


def test_bare_abbreviation_is_not_a_term():
    assert rules(div("The **odds** are p / (1 - p), abbreviated **OR** or **PPV**.")) == []


def test_quoted_and_parenthesized_gloss_is_not_a_term():
    assert rules(div('The **odds** (the **ratio**) are written "**odds**".')) == []


def test_symbol_bold_is_not_a_term():
    assert rules(div("The **odds** for a vector **x** and **b** are p.")) == []


def test_bold_inside_nested_callout_is_not_counted():
    lines = div(
        "The **odds** are p / (1 - p).",
        "",
        ":::: {.callout-note}",
        "A **warning** and a **caveat**.",
        "::::",
    )
    assert rules(lines) == []


def test_edit_inside_existing_div_is_in_scope():
    lines = div("The **odds** are p / (1 - p),", "and the **log-odds** are their logarithm.")
    assert rules(lines, added={6}) == ["multiple-terms-in-definition"]


def test_longer_tilde_fence_content_is_skipped():
    lines = div(
        "The **odds** are p / (1 - p).",
        "~~~~",
        "~~~",
        "**not a term** and **another**",
        "~~~~",
    )
    assert rules(lines) == []


def test_html_comment_content_is_skipped():
    lines = div(
        "The **odds** are p / (1 - p).",
        "<!-- a **second** and **third** -->",
        "<!--",
        "**fourth**",
        "-->",
    )
    assert rules(lines) == []


def test_yaml_front_matter_is_skipped():
    lines = ["---", "title: **a** and **b**", "---", ""] + div("The **odds** are p.")
    assert rules(lines) == []


def test_quoted_alias_after_cue_is_not_a_second_term():
    lines = div('The **odds**, also called the "**chance ratio**", are p / (1 - p).')
    assert rules(lines) == []
