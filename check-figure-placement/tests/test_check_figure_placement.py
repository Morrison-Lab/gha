"""Unit tests for check-figure-placement.

Covers the two findings (uncited, unnested), what is exempt, diff scoping,
the skip-not-fallback guard, and the warn-only default the action, the
reusable workflow and the script must agree on.
"""

import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_figure_placement", _DIR / "check-figure-placement.py"
)
assert _spec is not None and _spec.loader is not None
fpl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fpl)


def messages(text: str, keep=None):
    found, _ = fpl.scan_file(text.split("\n"), keep)
    return [(fig.ident, msg.split(" Fix")[0]) for fig, msg in found]


CITED = "See @fig-a.\n\n::: {#fig-a}\n![](a.png)\n:::\n"


def test_cited_figure_is_clean():
    assert messages(CITED) == []


def test_uncited_figure_is_flagged():
    got = messages("::: {#fig-a}\n![](a.png)\n:::\n")
    assert got == [("fig-a", "Figure fig-a is never cited.")]


def test_citation_inside_the_figure_does_not_count():
    assert len(messages("::: {#fig-a}\n![See @fig-a](a.png)\n:::\n")) == 1


def test_link_citation_counts():
    assert messages("See [the plot](#fig-a).\n\n::: {#fig-a}\n![](a.png)\n:::\n") == []


def test_prefix_of_another_id_does_not_count():
    assert len(messages("See @fig-ab.\n\n::: {#fig-a}\n![](a.png)\n:::\n")) == 1


def test_chunk_label_is_a_figure():
    text = "See @fig-p.\n\n```{r}\n#| label: fig-p\nplot(1)\n```\n"
    assert messages(text) == []
    assert len(messages("```{r}\n#| label: fig-p\nplot(1)\n```\n")) == 1


def test_inline_image_id_is_a_figure():
    assert len(messages("![cap](a.png){#fig-i}\n")) == 1


UNNESTED = (
    "See @fig-a.\n\n::: {#exm-a}\nCompute.\n:::\n\n"
    "::: {#fig-a}\n![](a.png)\n:::\n"
)


def test_figure_after_example_div_is_unnested():
    got = messages(UNNESTED)
    assert got == [("fig-a", "Figure fig-a sits directly after an example or "
                    "exercise div instead of inside it.")]


def test_figure_inside_example_div_is_clean():
    text = "See @fig-a.\n\n::: {#exm-a}\nCompute.\n\n::: {#fig-a}\n![](a.png)\n:::\n:::\n"
    assert messages(text) == []


def test_figure_inside_solution_div_is_clean():
    text = "See @fig-a.\n\n::: {#sol-a}\nAnswer.\n\n```{r}\n#| label: fig-a\nplot(1)\n```\n:::\n"
    assert messages(text) == []


def test_shared_figure_after_prose_is_clean():
    text = "See @fig-a.\n\nBoth examples use it.\n\n::: {#fig-a}\n![](a.png)\n:::\n"
    assert messages(text) == []


def test_figure_after_non_example_div_is_clean():
    text = "See @fig-a.\n\n::: {#def-a}\nTerm.\n:::\n\n::: {#fig-a}\n![](a.png)\n:::\n"
    assert messages(text) == []


def test_allow_comment_exempts_both_findings():
    text = UNNESTED.replace("![](a.png)", "![](a.png) <!-- figure-placement: allow -->")
    assert messages(text) == []


def test_figure_in_code_fence_or_comment_is_not_counted():
    assert messages("```\n::: {#fig-a}\n:::\n```\n") == []
    assert messages("<!-- ::: {#fig-a} -->\n") == []


def test_diff_scope_only_reports_touched_figures():
    text = "::: {#fig-a}\n![](a.png)\n:::\n\n::: {#fig-b}\n![](b.png)\n:::\n"
    assert [i for i, _ in messages(text, keep={6})] == ["fig-b"]
    assert messages(text, keep={4}) == []


def test_no_base_ref_skips_instead_of_scanning():
    report = fpl.run_check("", ["*.qmd"], [], False)
    assert report.skipped and report.findings == []


def test_defaults_agree_across_script_action_and_workflow():
    assert fpl._DEFAULT_FAIL is True
    action = (_DIR / "action.yml").read_text()
    assert "default: 'true'" in action.split("fail:")[1]
    wf = (_DIR.parent / ".github" / "workflows" / "check-figure-placement.yml").read_text()
    assert "default: true" in wf.split("      fail:")[1]
