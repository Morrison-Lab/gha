"""Unit tests for check-common/spelling.py and the spelling-only exemption (gha#2095)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diffscope  # noqa: E402
import spelling  # noqa: E402


@pytest.mark.parametrize("british, american", [
    ("colour", "color"), ("Coloured", "Colored"), ("neighbourhoods", "neighborhoods"),
    ("behaviour", "behavior"), ("normalise", "normalize"), ("Regularisation", "Regularization"),
    ("analysed", "analyzed"), ("centre", "center"), ("centres", "centers"),
    ("centred", "centered"), ("millimetres", "millimeters"), ("labelled", "labeled"),
    ("modelling", "modeling"), ("cancelled", "canceled"), ("grey", "gray"),
    ("greyscale", "grayscale"), ("judgement", "judgment"), ("defence", "defense"),
    ("licence", "license"), ("tumours", "tumors"), ("realisable", "realizable"),
])
def test_americanize(british, american):
    assert spelling.BRITISH_RE.fullmatch(british)
    assert spelling.americanize(british) == american


@pytest.mark.parametrize("word", [
    "otherwise", "noise", "exercise", "precise", "analyses", "four", "tour",
    "characteristic", "organism", "parameter", "emphasis", "color",
])
def test_not_british(word):
    assert not spelling.BRITISH_RE.search(word)


def test_american_variants_keeps_or_respells_code_spans():
    line = "the colour is set by `colour = x`"
    assert spelling.american_variants(line) == {
        "the color is set by `color = x`",
        "the color is set by `colour = x`",
    }
    assert spelling.american_variants("no British word here") == set()


def _diff(old, new):
    return f"--- a/a.qmd\n+++ b/a.qmd\n@@ -1 +1 @@\n-{old}\n+{new}\n"


def test_a_spelling_only_change_reads_as_moved():
    _added, deleted = diffscope.parse_diff(_diff("A coloured map.", "A colored map."))
    assert "A colored map." in deleted


def test_a_spelling_change_with_another_edit_is_still_added():
    _added, deleted = diffscope.parse_diff(_diff("A coloured map.", "Just a colored map."))
    assert "Just a colored map." not in deleted


def test_spelling_only_lines_leaves_out_a_pure_move():
    diff = ("--- a/a.qmd\n+++ b/a.qmd\n@@ -1,2 +1,2 @@\n"
            "-A coloured map.\n-Same line.\n+A colored map.\n+Same line.\n")
    assert diffscope.spelling_only_lines(diff) == {"a.qmd": {1}}
