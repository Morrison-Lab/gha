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


# Findings from the second cross-harness review of gha#1072.


def terms_of(lines):
    return [f.term for f in scan(Path("t.qmd"), lines)]


def test_word_ending_in_or_is_not_an_alias_cue():
    assert terms_of(div("The **odds** of the event, for the **log-odds**, are...")) == [
        "odds, log-odds"
    ]
    assert terms_of(div("The **odds** of a vector **log-odds** are...")) == ["odds, log-odds"]
    assert terms_of(div("The **odds** and, prior **log-odds**, are...")) == ["odds, log-odds"]


def test_real_or_cue_still_makes_an_alias():
    assert terms_of(div("The **odds**, or **chance ratio**, are p / (1 - p).")) == []


def test_inline_math_does_not_unbalance_parentheses():
    lines = div("The **odds** lie in $(0, 1]$ and the **log-odds** are real.")
    assert terms_of(lines) == ["odds, log-odds"]


def test_double_star_in_math_is_not_bold():
    lines = div("The **odds** involve $x^{**}$ and then the **log-odds**.")
    assert terms_of(lines) == ["odds, log-odds"]


def test_plural_of_a_term_counts_once():
    assert rules(div("The **residual** and the **residuals** are...")) == []


def test_parenthesized_alias_is_remembered():
    lines = div("The **odds** (also **chance**) are p / (1 - p).", "Later the **chance** is 4.")
    assert rules(lines) == []


def test_alias_cue_wrapped_onto_the_next_line():
    lines = div("The **log-odds**, also called", "the **logit**, are log(odds).")
    assert rules(lines) == []
    lines = div("The **log-odds**, also called the", "**logit**, are log(odds).")
    assert rules(lines) == []


def test_text_after_a_closing_html_comment_is_prose():
    lines = div("The **odds** are p.", "<!--", "hidden **x** y", "--> Then the **log-odds** are real.")
    assert terms_of(lines) == ["odds, log-odds"]


def test_text_before_an_opening_html_comment_is_prose():
    lines = div("The **odds** are p, <!--", "hidden -->", "and the **log-odds** are real.")
    assert terms_of(lines) == ["odds, log-odds"]


def test_bare_class_nested_div_is_nested():
    lines = div(
        "The **odds** are p.",
        "::: callout-note",
        "A **caveat** and a **warning**.",
        ":::",
    )
    assert rules(lines) == []


def test_shorter_fence_does_not_close_a_longer_nested_div():
    lines = div(
        "The **odds** are p.",
        ":::: {.callout-note}",
        "Inner **warning**.",
        ":::",
        "More **caveat** inside.",
        "::::",
    )
    assert rules(lines) == []


def test_content_after_a_nested_div_is_back_in_the_definition():
    lines = div(
        "The **odds** are p.",
        "::: callout-note",
        "Inner **warning**.",
        ":::",
        "Then the **log-odds** are real.",
    )
    assert terms_of(lines) == ["odds, log-odds"]


def test_module_docstring_describes_the_current_rule():
    doc = check_defs.__doc__
    assert "title joining" not in doc
    assert "more than one" in doc


def test_markdown_report_covers_bundled_defs(tmp_path, monkeypatch):
    page = tmp_path / "page.qmd"
    page.write_text("\n".join(div("The **odds** and the **log-odds** are...")) + "\n")
    out = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["check-informal-definitions.py", "--path", str(page), "--output-markdown", str(out)],
    )
    check_defs.main()
    text = out.read_text()
    assert "more than one term" in text
