"""Unit tests for check-axis-titles.

Covers which strings count as a plain-word title, which calls are axis titles
(ggplot2, matplotlib, plotly; one line or spanning lines), the exemption
comment and its reason, diff scoping, and the defaults the action, the
reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_axis_titles", _DIR / "check-axis-titles.py"
)
assert _spec is not None and _spec.loader is not None
axt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(axt)


def bad(text: str):
    """Flagged title strings for a document string."""
    found, _ = axt.scan_file(text.split("\n"), None)
    return [t.text for t in found]


@pytest.mark.parametrize("title", [
    "x", "y", "z", "x1", "f(x)", "y h(x)", "p", r"$\hat{y}$", "$z$", "pi",
])
def test_bare_symbol_or_expression_has_no_plain_word(title):
    assert not axt.has_plain_word(title)


@pytest.mark.parametrize("title", [
    "mpg", "Log-odds, η", "Probability, π", "Weight (lb)", "RMSE",
    "horsepower", "Score $z$", "Body mass index (bmi)",
])
def test_title_with_a_word_is_fine(title):
    assert axt.has_plain_word(title)


# -- which calls are axis titles ---------------------------------------------

def test_matplotlib_labels():
    assert bad('ax.set_xlabel("x")\nax.set_ylabel("Miles per gallon")') == ["x"]


def test_ggplot_xlab_ylab():
    assert bad('p + xlab("z") + ylab("Probability")') == ["z"]


def test_labs_one_line():
    assert bad('labs(x = "x1", y = "x2", colour = "g")') == ["x1", "x2"]


def test_labs_spanning_lines():
    text = 'ggplot(d) +\n  labs(\n    x = "x",\n    y = "Probability, p",\n    colour = "z"\n  )'
    assert bad(text) == ["x"]


def test_x_equals_outside_labs_is_not_a_title():
    assert bad('aes(x = "x")\nlist(y = "y")') == []


def test_labs_depth_resets_after_the_call():
    text = 'labs(\n  x = "Weight (lb)"\n) +\n  other(x = "x")'
    assert bad(text) == []


def test_plotly_axis_titles():
    assert bad('fig.update_layout(xaxis_title="x", yaxis_title="Density")') == ["x"]
    assert bad('layout(xaxis = list(title = "z"), yaxis = list(title = "Rate"))') == ["z"]


def test_single_quotes():
    assert bad("ax.set_xlabel('x')") == ["x"]


def test_null_and_variable_titles_are_not_examined():
    assert bad("labs(x = NULL, y = NULL)\nax.set_xlabel(label)") == []


def test_empty_and_placeholder_titles_are_not_flagged():
    assert bad('ax.set_xlabel("")\nax.set_ylabel("...")') == []


def test_raw_string_prefix():
    assert bad('ax.set_xlabel(r"$\\eta$")') == [r"$\eta$"]


# -- exemptions --------------------------------------------------------------

def test_exemption_needs_a_reason():
    assert bad('ax.set_xlabel("x")  # axis-title-ok: the data column is named x') == []
    assert bad('ax.set_xlabel("x")  # axis-title-ok:') == ["x"]


# -- diff scoping ------------------------------------------------------------

def test_only_kept_lines_are_reported():
    lines = ['ax.set_xlabel("x")', 'ax.set_ylabel("y")']
    found, seen = axt.scan_file(lines, {2})
    assert [t.text for t in found] == ["y"]
    assert seen == 2


def test_multiline_labs_attributes_to_the_string_line():
    lines = ["labs(", '  x = "x",', '  y = "Probability"', ")"]
    found, _ = axt.scan_file(lines, {2})
    assert [(t.line, t.text) for t in found] == [(2, "x")]
    found, _ = axt.scan_file(lines, {3})
    assert found == []


# -- findings from the independent review ------------------------------------

@pytest.mark.parametrize("code", [
    'plt.xlabel("x")',
    'plt.xlabel("x")',
    'ax.set_xlabel(xlabel="x")',
    'ax.set(xlabel="x")',
    'fig.update_xaxes(title_text="x")',
    'fig.update_xaxes(title="x")',
    'fig.update_layout(xaxis=dict(title=dict(text="x")))',
    'layout(xaxis = list(title = list(text = "x")))',
    'p + scale_x_continuous(name = "x")',
    'fig.update_layout(xaxis2=dict(title="x"))',
    'layout(xaxis=list(range=list(1, 2), title="x"))',
    'layout(\n  xaxis = list(\n    title = "x"\n  )\n)',
])
def test_more_ways_to_title_an_axis(code):
    assert bad(code) == ["x"]


def test_unit_and_foreign_titles_are_judged_by_plain_words():
    assert bad(r'ax.set_xlabel(r"$\mathrm{time}$")') == []
    assert bad('labs(x = "$5 to $10 per hour")') == []


def test_aes_after_a_closed_labs_is_not_a_title():
    assert bad('labs(x = "Weight") + aes(x = "x")') == []


def test_commented_out_call_is_not_flagged():
    assert bad('# labs(x = "x")\n# xlab("x")') == []


def test_unclosed_labs_does_not_swallow_the_rest_of_the_file():
    text = "Use `labs(` to set titles.\n" + "\n".join(
        f"filler line {i}" for i in range(30)) + '\nplot(aes(x = "x"))\nfoo(y = "y")'
    assert bad(text) == []


def test_paren_and_quote_inside_a_title_string():
    text = 'labs(\n  x = "Weight (lb)",\n  y = "y"\n) + aes(x = "x")'
    assert bad(text) == ["y"]


def test_deleted_line_in_one_file_does_not_exempt_another(tmp_path, monkeypatch):
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "a.R").write_text('labs(\n  x = "x",\n  y = "Rate"\n)\n')
    git("add", ".")
    git("commit", "-q", "-m", "base")
    (tmp_path / "a.R").write_text('labs(\n  y = "Rate"\n)\n')
    (tmp_path / "b.R").write_text('labs(\n  x = "x",\n  y = "Rate"\n)\n')
    git("add", ".")
    git("commit", "-q", "-m", "change")
    monkeypatch.chdir(tmp_path)
    report = axt.run_check("HEAD~1", ["*.R"], [], False)
    assert [(rel, t.text) for rel, t in report.findings] == [("b.R", "x")]


def test_skips_without_a_base_ref():
    report = axt.run_check("", ["*.qmd"], [], False)
    assert report.skipped


# -- the action, workflow and script agree -----------------------------------

def test_defaults_agree():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-axis-titles.yml").read_text()
    default_globs = axt.DEFAULT_GLOBS
    assert f"default: '{default_globs}'" in action
    assert f"default: '{default_globs}'" in workflow
    assert axt._DEFAULT_FAIL is True
    assert re.search(r"fail:\s*\n(?:.*\n)*?\s*default: true", workflow)
