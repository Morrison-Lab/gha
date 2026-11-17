"""Unit tests for check-geometric-figures: the claim vocabulary, what counts
as a nearby figure, the exemption, paragraph dedupe, math and code skipping."""

import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_geometric_figures", _DIR / "check-geometric-figures.py")
assert _spec is not None and _spec.loader is not None
geo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(geo)

CLAIM = "The loss term has elliptical contours.\n"


def missing(text, window=40, keep=None):
    return geo.check_lines(text.split("\n"), keep, window)[0]


def test_claim_without_figure_is_flagged():
    assert missing(CLAIM) == [1]


def test_circular_contours_flagged():
    assert missing("The penalty has circular contours centered at 0.") == [1]


def test_figure_reference_nearby_pairs_the_claim():
    assert missing(CLAIM + "See @fig-contours.\n") == []


def test_image_and_fig_include_count():
    assert missing(CLAIM + "\n![Contours](a.png)\n") == []
    assert missing(CLAIM + "\n{{< include _fig-x.qmd >}}\n") == []
    assert missing("{{< include _subfiles/r/_fig-x.qmd >}}\n\n" + CLAIM) == []


def test_figure_chunk_counts():
    assert missing(CLAIM + "\n```{r}\n#| label: fig-c\nplot(1)\n```\n") == []


def test_far_figure_does_not_count():
    far = CLAIM + "\n" * 60 + "![Far](a.png)\n"
    assert missing(far) == [1]
    assert missing(far, window=100) == []


def test_figure_in_enclosing_div_counts_beyond_window():
    text = "::: {#exm-a}\n" + CLAIM + "\n" * 60 + "![x](a.png)\n:::\n"
    assert missing(text) == []


def test_exemption_requires_reason():
    assert missing(CLAIM + "<!-- no-figure: a single number -->\n") == []
    assert missing(CLAIM + "<!-- no-figure: -->\n") == [1]


def test_one_finding_per_paragraph():
    text = "Contours are ellipses.\nThey are circular here.\n\nAnother circle.\n"
    assert missing(text) == [1, 4]


def test_math_code_and_comments_are_not_claims():
    text = "$\\text{contour}$ is math.\n```r\n# ellipse\n```\n<!-- circle -->\n"
    assert missing(text) == []


def test_ordinary_algebra_words_are_not_claims():
    assert missing("The function is convex and the angle is small.\n") == []


def test_keep_limits_to_added_lines():
    assert missing(CLAIM, keep={5}) == []
    assert missing(CLAIM, keep={1}) == [1]
