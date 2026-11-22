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


# --- Geometric definitions: the next example needs a figure ---------------

DEF = ("::: {#def-pr-curve}\n\n#### Precision-recall curve\n\n"
       "The **precision-recall curve** plots recall against precision.\n\n:::\n")
EXM_TABLE = "::: {#exm-pr-curve}\n\n#### A curve\n\nA table.\n\n:::\n"
EXM_FIG = "::: {#exm-pr-curve}\n\n#### A curve\n\n![Curve](a.png)\n\n:::\n"


def def_findings(files, wanted=None):
    corpus = {k: v.split("\n") for k, v in files.items()}
    return geo.check_definitions(corpus, wanted)[0]


def test_geometric_definition_needs_example_figure_same_file():
    assert len(def_findings({"a.qmd": DEF + "\n" + EXM_TABLE})) == 1
    assert def_findings({"a.qmd": DEF + "\n" + EXM_FIG}) == []


def test_example_no_figure_pragma_does_not_exempt_the_definition():
    exm = EXM_TABLE.replace("A table.", "<!-- no-figure: a table -->\nA table.")
    assert len(def_findings({"a.qmd": DEF + "\n" + exm})) == 1


def test_definition_pragma_exempts():
    d = DEF.replace("plots", "<!-- no-figure: nothing to draw -->\nplots")
    assert def_findings({"a.qmd": d + "\n" + EXM_TABLE}) == []


def test_non_geometric_definition_is_ignored():
    d = DEF.replace("Precision-recall curve", "Precision").replace(
        "precision-recall curve", "precision")
    assert def_findings({"a.qmd": d + "\n" + EXM_TABLE}) == []


def test_link_target_in_bold_term_does_not_count():
    d = ("::: {#def-dm}\n\n#### Design matrix\n\n"
         "The **[design matrix](https://x.org/projections.html#d)** is X.\n\n:::\n")
    assert def_findings({"a.qmd": d + "\n" + EXM_TABLE}) == []


def test_subfiles_through_parent_includes():
    parent = ("{{< include _s/_def-pr-curve.qmd >}}\n\n{{< slidebreak >}}\n\n"
              "{{< include _s/_exm-pr-curve.qmd >}}\n")
    files = {"ch/p.qmd": parent, "ch/_s/_def-pr-curve.qmd": DEF,
             "ch/_s/_exm-pr-curve.qmd": EXM_TABLE}
    found = def_findings(files)
    assert [(f[0], f[1]) for f in found] == [("ch/_s/_def-pr-curve.qmd", 1)]
    files["ch/_s/_exm-pr-curve.qmd"] = EXM_FIG
    assert def_findings(files) == []


def test_fig_subfile_include_in_example_counts():
    exm = EXM_TABLE.replace("A table.", "{{< include _fig-pr.qmd >}}")
    assert def_findings({"a.qmd": DEF + "\n" + exm}) == []


def test_another_result_before_any_example_stops_the_search():
    thm = "::: {#thm-x}\n\n#### T\n\nA result.\n\n:::\n"
    assert def_findings({"a.qmd": DEF + "\n" + thm + "\n" + EXM_TABLE}) == []


def test_diff_scope_reports_when_definition_or_example_is_touched():
    parent = ("{{< include _s/_def-pr-curve.qmd >}}\n\n"
              "{{< include _s/_exm-pr-curve.qmd >}}\n")
    files = {"p.qmd": parent, "_s/_def-pr-curve.qmd": DEF,
             "_s/_exm-pr-curve.qmd": EXM_TABLE}
    assert def_findings(files, {"other.qmd": {1}}) == []
    assert len(def_findings(files, {"_s/_exm-pr-curve.qmd": {5}})) == 1
    assert len(def_findings(files, {"_s/_def-pr-curve.qmd": {5}})) == 1
    assert def_findings(files, {"_s/_def-pr-curve.qmd": {99}}) == []
