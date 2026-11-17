"""Unit tests for check-common/spelling.py, the shared British word list (gha#2095)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import spelling  # noqa: E402


@pytest.mark.parametrize("british, american", [
    ("unlabelled", "unlabeled"), ("Recoloured", "Recolored"), ("re-centred", "re-centered"),
    ("enrolment", "enrollment"), ("fulfilment", "fulfillment"),
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
