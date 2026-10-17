"""Unit tests for the link-in-definition-div rule of check-informal-definitions."""

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


def test_def_without_link_flagged():
    lines = [
        "::: {#def-fit}",
        "",
        "A **fitting procedure** is a function from data sets to models.",
        "",
        ":::",
    ]
    assert rules(lines) == ["no-link-in-definition"]


def test_hyperlink_passes():
    lines = [
        "::: {#def-fit}",
        "",
        "A **fitting procedure** is a [function](functions.qmd#def-function).",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_cross_reference_passes():
    lines = [
        "::: {#def-fit}",
        "",
        "A **fitting procedure** produces a @def-fitted-model.",
        "",
        ":::",
    ]
    assert rules(lines) == []


def test_link_in_title_only_does_not_count_as_prose_only_div():
    lines = ["::: {#def-fit}", "", "#### Fitting procedure", "", ":::"]
    assert rules(lines) == []


def test_opt_out_directive_skips():
    lines = [
        "::: {#def-fit}",
        "<!-- check-informal-definitions: allow -->",
        "A **set** is a collection of objects.",
        ":::",
    ]
    assert rules(lines) == []


def test_diff_scoped_ignores_untouched_div():
    lines = [
        "::: {#def-fit}",
        "A **set** is a collection of objects.",
        ":::",
    ]
    assert rules(lines, added={10}) == []
    assert rules(lines, added={2}) == ["no-link-in-definition"]
