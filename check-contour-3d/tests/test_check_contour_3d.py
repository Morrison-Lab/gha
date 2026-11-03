"""Unit tests for check-contour-3d.

Covers what counts as a contour call and a 3D plot, the three ways a file is
satisfied (a 3D call, a 3D include or sibling, the exemption comment and its
reason), code fences and comments, diff scoping, and the defaults the action,
the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_contour_3d", _DIR / "check-contour-3d.py"
)
assert _spec is not None and _spec.loader is not None
c3d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c3d)


def chunk(body: str) -> str:
    return "```{r}\n" + body + "\n```\n"


def flagged(text: str, rel=None):
    """First contour-call lines of the figures with no 3D plot."""
    found, _ = c3d.scan_file(text.split("\n"), None, rel)
    return [f.first_call for f in found]


@pytest.mark.parametrize("call", [
    "ggplot(d, aes(x, y, z = z)) + geom_contour()",
    "ggplot(d) + geom_contour_filled()",
    "stat_contour(aes(z = z))",
    "plotly::add_contour(p, z = z)",
    "contour(x, y, z)",
    "filled.contour(x, y, z)",
    "ax.contour(X, Y, Z)",
    "plt.contourf(X, Y, Z)",
    "Plot.contour(data)",
    'plot_ly(z = z, type = "contour")',
])
def test_contour_calls_are_flagged(call):
    assert flagged(chunk(call)) == [2]


def test_plotly_contours_argument_is_not_a_contour_plot():
    assert flagged(chunk("add_surface(z = z, contours = list(z = zc))")) == []


def test_contour_in_prose_is_not_flagged():
    assert flagged("A contour plot of the loss.\n") == []


def test_contour_in_html_comment_is_not_flagged():
    assert flagged("<!--\n" + chunk("contour(x, y, z)") + "-->\n") == []


@pytest.mark.parametrize("call", [
    "add_surface(x = x, y = y, z = z)",
    "ax.plot_surface(X, Y, Z)",
    "ax.plot_trisurf(x, y, z)",
    "persp(x, y, z)",
    "persp3d(x, y, z)",
    'plot_ly(z = z, type = "surface")',
])
def test_a_3d_call_in_the_file_satisfies_it(call):
    doc = chunk("contour(x, y, z)") + "\n" + chunk(call)
    assert flagged(doc) == []


@pytest.mark.parametrize("line", [
    "{{< include pds/_subfiles/_fig-a-3d.qmd >}}",
    "{{< include _subfiles/_fig_a_3d.qmd >}}",
])
def test_a_3d_include_satisfies_it(line):
    assert flagged(chunk("contour(x, y, z)") + "\n" + line + "\n") == []


def test_exemption_with_a_reason_satisfies_it():
    doc = "<!-- no-3d: a density estimated from data -->\n" + chunk("contour(x, y, z)")
    assert flagged(doc) == []


def test_exemption_without_a_reason_does_not():
    doc = "<!-- no-3d: -->\n" + chunk("contour(x, y, z)")
    assert flagged(doc) == [3]


def test_sibling_3d_subfile_satisfies_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "_fig-a.qmd").write_text("x")
    assert flagged(chunk("contour(x, y, z)"), "_fig-a.qmd") == [2]
    (tmp_path / "_fig-a-3d.qmd").write_text("x")
    assert flagged(chunk("contour(x, y, z)"), "_fig-a.qmd") == []


def test_scope_keeps_only_figures_with_an_added_line():
    doc = chunk("contour(x, y, z)") + "\n" + chunk("contour(a, b, c)")
    found, seen = c3d.scan_file(doc.split("\n"), {7}, None)
    assert seen == 2
    assert [f.first_call for f in found] == [6]
    found, _ = c3d.scan_file(doc.split("\n"), set(), None)
    assert found == []


def test_defaults_agree():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github" / "workflows" / "check-contour-3d.yml").read_text()
    assert c3d._DEFAULT_FAIL is False
    assert "default: 'false'" in action.split("fail:")[1]
    assert "default: false" in workflow.split("fail:")[1]
