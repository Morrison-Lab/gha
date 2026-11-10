r"""Unit tests for check-definition-expectation.

Covers what is flagged (a probability-weighted sum or integral in a definition
with no expectation operator), what is not (sample averages, a lone mass or
density, the definition of expectation itself, a definition that already uses
an expectation, the opt-out comment), diff scoping, and main()'s exit codes.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_definition_expectation", _DIR / "check-definition-expectation.py")
assert _spec is not None and _spec.loader is not None
dx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dx)


def definition(display: str, opener: str = "{#def-a}", extra: str = "") -> str:
    return f"::: {opener}\n{extra}Define the quantity.\n\n$$\n{display}\n$$\n:::\n"


def run(text: str, touched=None):
    return dx.check_file("a.qmd", text.split("\n"), touched)


@pytest.mark.parametrize("display", [
    r"H(X) := \sum_x p(x) \log \frac{1}{p(x)}",
    r"\mu := \sum_x x p(x)",
    r"\mu := \int x f(x) \, dx",
    r"\mu := \int x f_X(x) \, \mathrm{d}x",
    r"D(p \| q) := \sum_x p_X(x) \log \frac{p_X(x)}{q(x)}",
    r"\mu := \sum_{x} x \Pr(X = x)",
])
def test_weighted_sum_or_integral_is_flagged(display):
    findings = run(definition(display))
    assert len(findings) == 1
    assert "#def-a" in findings[0].message


@pytest.mark.parametrize("display", [
    r"H(X) := \E{\log \frac{1}{p(X)}}",
    r"H(X) := \mathbb{E}[\log \frac{1}{p(X)}]",
    r"\bar y := \frac{1}{n} \sum_{i=1}^n y_i",
    r"\hat\mu := \sum_{i=1}^n w_i y_i",
    r"\sum_x p(x) = 1",
    r"\int f(x) \, dx = 1",
    r"L(\theta) := \prod_{i=1}^n p(y_i \mid \theta)",
])
def test_expectations_sample_averages_and_lone_densities_are_not_flagged(display):
    assert run(definition(display)) == []


def test_div_titled_expectation_is_exempt():
    display = r"\mu := \sum_x x p(x)"
    assert run(definition(display, '{#def-ev title="Expectation"}')) == []
    assert run(definition(display, "{#def-ev}", extra="## Expected value\n\n")) == []
    assert len(run(definition(display, "{#def-ev}", extra="## Mean\n\n"))) == 1


def test_opt_out_comment_exempts_the_definition():
    display = r"\mu := \sum_x x p(x)"
    text = definition(display, extra="<!-- check-definition-expectation: allow -->\n")
    assert run(text) == []


def test_only_definitions_are_read():
    text = definition(r"\mu := \sum_x x p(x)", "{#thm-a}")
    assert run(text) == []


def test_sum_in_prose_without_a_display_is_not_flagged():
    text = "::: {#def-a}\nThe sum of x p(x) over x.\n:::\n"
    assert run(text) == []


def test_only_touched_definitions_are_checked():
    text = definition(r"\mu := \sum_x x p(x)")
    assert run(text, touched={99}) == []
    assert len(run(text, touched={4})) == 1


def test_default_is_warn_only():
    assert dx._DEFAULT_FAIL is False


# -- main(): exit codes and annotations ---------------------------------------

def _repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")  # phi-allow
    git("config", "user.name", "t")
    (tmp_path / "README.md").write_text("base\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    return tmp_path, git


def _env(monkeypatch, repo, **extra):
    monkeypatch.chdir(repo)
    for key in ("DX_BASE_REF", "DX_GLOBS", "DX_PATHS_IGNORE", "DX_FAIL",
                "DX_WHOLE_TREE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DX_BASE_REF", "HEAD")
    for key, value in extra.items():
        monkeypatch.setenv(key, value)


def test_main_warns_by_default_and_fails_when_asked(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(definition(r"\mu := \sum_x x p(x)"))
    git("add", "-A")
    _env(monkeypatch, repo)
    assert dx.main() == 0
    assert "::warning file=page.qmd,line=1::" in capsys.readouterr().out
    monkeypatch.setenv("DX_FAIL", "true")
    assert dx.main() == 1
    assert "::error file=page.qmd,line=1::" in capsys.readouterr().out


def test_main_passes_an_expectation(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(definition(r"\mu := \E{X}"))
    git("add", "-A")
    _env(monkeypatch, repo, DX_FAIL="true")
    assert dx.main() == 0
    assert "No touched definition writes" in capsys.readouterr().out


def test_main_skips_without_a_base(tmp_path, monkeypatch, capsys):
    repo, git = _repo(tmp_path)
    (repo / "page.qmd").write_text(definition(r"\mu := \sum_x x p(x)"))
    git("add", "-A")
    _env(monkeypatch, repo, DX_FAIL="true", DX_BASE_REF="")
    assert dx.main() == 0
    assert capsys.readouterr().out.startswith("Skipping the definition-expectation check")
