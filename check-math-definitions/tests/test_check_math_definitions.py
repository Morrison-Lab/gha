import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Add parent directory to path so we can import check_math_definitions
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_math_definitions as cmd


def test_parse_math_divs_basic():
    text = """
# Chapter 1

::: {#def-variance}
#### Variance

The variance of a random variable $X$ is defined as $\\operatorname{Var}(X) = \\mathbb{E}[(X - \\mathbb{E}[X])^2]$.
:::

Some text in between.

::: {#thm-bayes}
#### Bayes' Theorem

For any events $A$ and $B$, $\\mathbb{P}(A \\mid B) = \\frac{\\mathbb{P}(B \\mid A) \\mathbb{P}(A)}{\\mathbb{P}(B)}$.
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="ch01.qmd",
        repo_name="rme",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 2

    d1 = divs[0]
    assert d1.div_id == "def-variance"
    assert d1.prefix == "def"
    assert d1.title == "Variance"
    assert "Var" in d1.raw_content
    assert not d1.opted_out

    d2 = divs[1]
    assert d2.div_id == "thm-bayes"
    assert d2.prefix == "thm"
    assert d2.title == "Bayes' Theorem"


def test_parse_math_divs_with_classes_and_nesting():
    text = """
:::: {#exr-ols .exercise}
#### OLS Estimator

Derive the OLS estimator.

::: {#sol-ols}
#### Solution
Use normal equations.
:::

::::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="exercises.qmd",
        repo_name="pds",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 2
    ids = {d.div_id for d in divs}
    assert ids == {"exr-ols", "sol-ols"}


def test_non_math_divs_ignored():
    text = """
::: {#fig-plot}
![Plot](plot.png)
:::

::: {.callout-note}
Remember to normalize data.
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="notes.qmd",
        repo_name="mln",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 0


def test_opt_out_directives():
    text = """
::: {#def-custom}
<!-- check-math-definitions: opt-out -->
#### Custom Def
Local definition.
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="doc.qmd",
        repo_name="mln",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 1
    assert divs[0].opted_out


def test_compare_identical_definitions_clean():
    d1 = cmd.MathDiv(
        div_id="def-variance",
        prefix="def",
        title="Variance",
        repo="rme",
        file_path="ch01.qmd",
        start_line=1,
        end_line=5,
        raw_content="Var(X) = E[(X - E[X])^2]",
        normalized_content="Var(X) = E[(X - E[X])^2]",
    )
    d2 = cmd.MathDiv(
        div_id="def-variance",
        prefix="def",
        title="Variance",
        repo="pds",
        file_path="ch02.qmd",
        start_line=10,
        end_line=15,
        raw_content="Var(X) = E[(X - E[X])^2]",
        normalized_content="Var(X) = E[(X - E[X])^2]",
    )
    findings = cmd.compare_math_definitions([d1, d2], check_titles=True)
    assert len(findings) == 0


def test_compare_exact_id_divergence():
    d1 = cmd.MathDiv(
        div_id="def-variance",
        prefix="def",
        title="Variance",
        repo="pds",
        file_path="ch01.qmd",
        start_line=5,
        end_line=10,
        raw_content="Var(X) = E[(X - E[X])^2]",
        normalized_content="Var(X) = E[(X - E[X])^2]",
    )
    d2 = cmd.MathDiv(
        div_id="def-variance",
        prefix="def",
        title="Variance",
        repo="rme",
        file_path="stats.qmd",
        start_line=20,
        end_line=25,
        raw_content="Var(X) is defined via devn(X)^2 macro",
        normalized_content="Var(X) is defined via devn(X)^2 macro",
    )
    findings = cmd.compare_math_definitions([d1, d2], check_titles=True)
    assert len(findings) == 1
    f = findings[0]
    assert f.kind == "exact_id_divergence"
    assert f.key == "def-variance"
    assert f.diff is not None
    assert "pds:ch01.qmd#def-variance" in f.diff
    assert "rme:stats.qmd#def-variance" in f.diff


def test_compare_in_repo_duplicate():
    d1 = cmd.MathDiv(
        div_id="thm-central-limit",
        prefix="thm",
        title="CLT",
        repo="rme",
        file_path="a.qmd",
        start_line=1,
        end_line=5,
        raw_content="CLT definition 1",
        normalized_content="CLT definition 1",
    )
    d2 = cmd.MathDiv(
        div_id="thm-central-limit",
        prefix="thm",
        title="CLT",
        repo="rme",
        file_path="b.qmd",
        start_line=10,
        end_line=15,
        raw_content="CLT definition 1",
        normalized_content="CLT definition 1",
    )
    findings = cmd.compare_math_definitions([d1, d2], check_titles=True)
    assert any(f.kind == "in_repo_duplicate" for f in findings)


def test_compare_title_collision():
    d1 = cmd.MathDiv(
        div_id="def-variance-standard",
        prefix="def",
        title="Variance",
        repo="pds",
        file_path="prob.qmd",
        start_line=1,
        end_line=5,
        raw_content="Formulation A",
        normalized_content="Formulation A",
    )
    d2 = cmd.MathDiv(
        div_id="def-var",
        prefix="def",
        title="Variance",
        repo="rme",
        file_path="ch01.qmd",
        start_line=10,
        end_line=15,
        raw_content="Formulation B",
        normalized_content="Formulation B",
    )
    findings = cmd.compare_math_definitions([d1, d2], check_titles=True)
    assert any(f.kind == "title_collision" for f in findings)


def test_cli_execution_clean(tmp_path):
    repo_dir = tmp_path / "repo1"
    repo_dir.mkdir()
    f1 = repo_dir / "math.qmd"
    f1.write_text(
        """::: {#def-norm}
#### L2 Norm
The L2 norm is defined as ||x||_2 = sqrt(sum(x_i^2)).
:::
""",
        encoding="utf-8",
    )

    script = Path(cmd.__file__).resolve()
    res = subprocess.run(
        [sys.executable, str(script), "--path", str(repo_dir), "--fail", "true"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0
    assert "All math definitions, theorems, and concepts are clean" in res.stdout


def test_cli_execution_divergence_reports_and_fails(tmp_path):
    repo1 = tmp_path / "repo1"
    repo1.mkdir()
    (repo1 / "a.qmd").write_text(
        """::: {#def-variance}
#### Variance
Var(X) = E[(X - E[X])^2]
:::
""",
        encoding="utf-8",
    )

    repo2 = tmp_path / "repo2"
    repo2.mkdir()
    (repo2 / "b.qmd").write_text(
        """::: {#def-variance}
#### Variance
Var(X) = devn(X)^2 with expanded theorem
:::
""",
        encoding="utf-8",
    )

    json_report = tmp_path / "report.json"
    md_report = tmp_path / "report.md"

    script = Path(cmd.__file__).resolve()
    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "--paths",
            f"{repo1}, {repo2}",
            "--output-json",
            str(json_report),
            "--output-markdown",
            str(md_report),
            "--fail",
            "true",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 1
    assert "Divergence" in res.stdout
    assert json_report.exists()
    assert md_report.exists()

    data = json.loads(json_report.read_text(encoding="utf-8"))
    assert data["total_divs"] == 2
    assert len(data["findings"]) >= 1
    assert data["findings"][0]["kind"] == "exact_id_divergence"
