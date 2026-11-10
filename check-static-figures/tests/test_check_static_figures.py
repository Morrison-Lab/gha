"""Unit tests for check-static-figures.

Covers the placeholder finding, what counts as an interactive call, which
fences run only in HTML (an eval option or a format div), what counts as a
static version, the exemption comment and its reason, diff scoping, and the
defaults the action and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_static_figures", _DIR / "check-static-figures.py"
)
assert _spec is not None and _spec.loader is not None
csf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(csf)

HTML_EVAL = "#| eval: !expr knitr::is_html_output()"
STATIC_EVAL = "#| eval: !expr isFALSE(knitr::is_html_output())"
NOTE = "the HTML or slide"


def chunk(*body: str, lang: str = "r") -> str:
    return "```{" + lang + "}\n" + "\n".join(body) + "\n```\n"


def flagged(text: str):
    found, _ = csf.scan_file(text.split("\n"), None)
    return [(f.line, f.kind) for f in found]


def note_chunk() -> str:
    # Built from parts so this test file does not itself read as a placeholder.
    return chunk(STATIC_EVAL, "#| results: asis",
                 'cat("*(Interactive; see ' + NOTE + ' version of this page.)*")')


def test_placeholder_in_a_chunk_is_flagged():
    assert flagged(note_chunk()) == [(4, "placeholder")]


@pytest.mark.parametrize("text", [
    "See the HTML version for the interactive plot.",
    "see the web version",
    "see the website version",
    "see the online version",
    "see the HTML or slides version",
])
def test_placeholder_wordings_are_flagged(text):
    assert flagged(text + "\n") == [(1, "placeholder")]


def test_placeholder_in_an_html_comment_is_not_flagged():
    assert flagged("<!-- see the HTML version -->\n") == []


@pytest.mark.parametrize("call", [
    "plot_ly(z = z)",
    "plotly::add_surface(p, z = z)",
    "ggplotly(p)",
    "fig = go.Figure()",
    "fig = px.scatter(df)",
    "htmlwidgets::saveWidget(w, f)",
    "leaflet(d)",
    "rglwidget()",
])
def test_html_only_interactive_calls_are_flagged(call):
    assert flagged(chunk(HTML_EVAL, call)) == [(3, "html-only")]


def test_import_plotly_is_an_interactive_call():
    assert flagged(chunk(HTML_EVAL, "import plotly.graph_objects as go",
                         lang="python")) == [(3, "html-only")]


def test_interactive_fence_in_every_format_is_not_flagged():
    assert flagged(chunk("plot_ly(z = z)")) == []


def test_in_chunk_branch_is_not_flagged():
    doc = chunk("if (knitr::is_html_output()) {", "  plotly::ggplotly(p)",
                "} else {", "  p", "}")
    assert flagged(doc) == []


def test_negated_html_eval_is_not_html_only():
    assert flagged(chunk(STATIC_EVAL, "plot_ly(z = z)")) == []


@pytest.mark.parametrize("attrs", [
    '{.content-visible when-format="html"}',
    '{.content-visible when-format="revealjs"}',
    '{.content-hidden unless-format="html"}',
])
def test_html_only_div_makes_a_fence_html_only(attrs):
    doc = "::: " + attrs + "\n" + chunk("plot_ly(z = z)") + ":::\n"
    assert flagged(doc) == [(3, "html-only")]


def test_a_closed_html_div_does_not_reach_later_fences():
    doc = ('::: {.content-visible when-format="html"}\nText.\n:::\n'
           + chunk("plot_ly(z = z)"))
    assert flagged(doc) == []


@pytest.mark.parametrize("static", [
    chunk(STATIC_EVAL, "persp(x, y, z)"),
    chunk(STATIC_EVAL, "ggplot(d) + geom_point()"),
    chunk("#| eval: !expr knitr::is_latex_output()", "plot(x, y)"),
    chunk(STATIC_EVAL, "ax.plot_surface(X, Y, Z)", lang="python"),
    chunk(STATIC_EVAL, "plotly::save_image(p, f)"),
    '::: {.content-visible when-format="pdf"}\n' + chunk("persp(x, y, z)") + ":::\n",
    '::: {.content-visible unless-format="html"}\n' + chunk("persp(x, y, z)") + ":::\n",
])
def test_a_static_plot_in_the_file_satisfies_it(static):
    doc = chunk(HTML_EVAL, "plot_ly(z = z)") + "\n" + static
    assert flagged(doc) == []


def test_a_note_chunk_is_not_a_static_version():
    doc = chunk(HTML_EVAL, "plot_ly(z = z)") + "\n" + note_chunk()
    assert flagged(doc) == [(3, "html-only"), (9, "placeholder")]


def test_a_static_plot_does_not_excuse_a_placeholder():
    doc = (chunk(HTML_EVAL, "plot_ly(z = z)") + "\n" + note_chunk() + "\n"
           + chunk(STATIC_EVAL, "persp(x, y, z)"))
    assert flagged(doc) == [(9, "placeholder")]


def test_a_plot_running_only_in_html_is_not_a_static_version():
    doc = chunk(HTML_EVAL, "plot_ly(z = z)", "plot(x, y)")
    assert flagged(doc) == [(3, "html-only")]


def test_exemption_with_a_reason_satisfies_it():
    doc = ("<!-- static-version: an animation with no still frame -->\n"
           + chunk(HTML_EVAL, "plot_ly(z = z)") + note_chunk())
    assert flagged(doc) == []


def test_exemption_without_a_reason_does_not():
    doc = "<!-- static-version: -->\n" + chunk(HTML_EVAL, "plot_ly(z = z)")
    assert flagged(doc) == [(4, "html-only")]


def test_scope_keeps_only_findings_with_an_added_line():
    doc = chunk(HTML_EVAL, "plot_ly(z = z)") + "\n" + chunk(HTML_EVAL, "plot_ly(a)")
    lines = doc.split("\n")
    found, seen = csf.scan_file(lines, {8})
    assert seen == 2
    assert [f.line for f in found] == [8]
    found, _ = csf.scan_file(lines, set())
    assert found == []


def test_scope_reports_a_placeholder_only_on_its_own_line():
    lines = note_chunk().split("\n")
    assert csf.scan_file(lines, {2})[0] == []
    assert [f.line for f in csf.scan_file(lines, {4})[0]] == [4]


def _input_default(text, indent, name):
    # The default line inside one input's block, which ends at the next line
    # indented no deeper than the input's own key.
    block = text.split(f"\n{indent}{name}:\n", 1)[1]
    block = re.split(rf"\n(?!{indent} )(?=\s{{0,{len(indent)}}}\S)", block, maxsplit=1)[0]
    defaults = [line.strip() for line in block.split("\n") if line.strip().startswith("default:")]
    assert len(defaults) == 1, (name, defaults)
    return defaults[0]


def test_defaults_agree():
    action = (_DIR / "action.yml").read_text()
    assert csf._DEFAULT_FAIL is False
    assert csf.DEFAULT_GLOBS == "*.qmd"
    assert _input_default(action, "  ", "fail") == "default: 'false'"
    assert _input_default(action, "  ", "globs") == "default: '*.qmd'"


def test_reusable_workflow_defaults_agree():
    workflow = (_DIR.parent / ".github" / "workflows" / "check-static-figures.yml").read_text()
    assert _input_default(workflow, "      ", "fail") == "default: false"
    assert "type: boolean" in workflow.split("\n      fail:\n", 1)[1].split("default:", 1)[0]
    assert _input_default(workflow, "      ", "globs") == "default: '*.qmd'"


def test_an_html_div_decides_over_a_static_eval_inside_it():
    # The div keeps the fence out of static output, so its plot is no static version.
    doc = ('::: {.content-visible when-format="html"}\n'
           + chunk(STATIC_EVAL, "persp(x, y, z)") + ":::\n"
           + chunk(HTML_EVAL, "plot_ly(z = z)"))
    assert flagged(doc) == [(9, "html-only")]


def test_an_exemption_inside_a_code_fence_does_not_exempt():
    # A fenced example of the comment, as in documentation, is not an exemption.
    doc = ("```\n<!-- static-version: shown as an example -->\n```\n"
           + chunk(HTML_EVAL, "plot_ly(z = z)"))
    assert flagged(doc) == [(6, "html-only")]
