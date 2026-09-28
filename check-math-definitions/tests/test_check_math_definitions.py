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


def test_code_block_fence_ignores_internal_divs():
    text = """
# Tutorial

Here is how to write a definition in Quarto:

```markdown
::: {#def-fake}
#### Fake Title
Fake content inside code block.
:::
```

And now the real definition:

::: {#def-real}
#### Real Definition
Real mathematical content.
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="tutorial.qmd",
        repo_name="demo",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 1
    assert divs[0].div_id == "def-real"
    assert divs[0].title == "Real Definition"


def test_html_comments_preceding_heading():
    text = """
::: {#def-variance}
<!-- check-math-definitions: allow-divergence -->
<!-- Some note before heading -->
#### Variance
The variance is E[(X - E[X])^2].
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="ch1.qmd",
        repo_name="demo",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 1
    assert divs[0].title == "Variance"
    assert divs[0].opted_out


def test_bold_label_title_extraction():
    text1 = """
::: {#def-var1}
**Definition 1.1** (Variance)
Let X be a random variable.
:::
"""
    divs1 = cmd.parse_math_divs_from_text(
        text=text1,
        file_path="ch1.qmd",
        repo_name="demo",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs1) == 1
    assert divs1[0].title == "Variance"

    text2 = """
::: {#thm-ltp}
**Theorem 2.1**: Law of Total Probability
P(A) = sum_n P(A | B_n) P(B_n).
:::
"""
    divs2 = cmd.parse_math_divs_from_text(
        text=text2,
        file_path="ch2.qmd",
        repo_name="demo",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs2) == 1
    assert divs2[0].title == "Law of Total Probability"


def test_title_collision_prefix_scoped_and_generic_exempted():
    # exr and sol sharing the same concept title should NOT collide
    d_exr = cmd.MathDiv(
        div_id="exr-ols",
        prefix="exr",
        title="OLS Estimator",
        repo="repo1",
        file_path="ex.qmd",
        start_line=1,
        end_line=5,
        raw_content="Derive OLS",
        normalized_content="Derive OLS",
    )
    d_sol = cmd.MathDiv(
        div_id="sol-ols",
        prefix="sol",
        title="OLS Estimator",
        repo="repo1",
        file_path="ex.qmd",
        start_line=6,
        end_line=10,
        raw_content="Solution to OLS",
        normalized_content="Solution to OLS",
    )
    findings = cmd.compare_math_definitions([d_exr, d_sol], check_titles=True)
    assert len(findings) == 0

    # Generic titles like "Remark 1" vs "Remark 2" should NOT collide
    d_rem1 = cmd.MathDiv(
        div_id="rem-1",
        prefix="rem",
        title="Remark 1",
        repo="repo1",
        file_path="r1.qmd",
        start_line=1,
        end_line=5,
        raw_content="First remark",
        normalized_content="First remark",
    )
    d_rem2 = cmd.MathDiv(
        div_id="rem-2",
        prefix="rem",
        title="Remark 2",
        repo="repo1",
        file_path="r2.qmd",
        start_line=1,
        end_line=5,
        raw_content="Second remark",
        normalized_content="Second remark",
    )
    findings_rem = cmd.compare_math_definitions([d_rem1, d_rem2], check_titles=True)
    assert len(findings_rem) == 0


def test_cli_execution_fail_false_warns_without_error(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.qmd").write_text(
        """::: {#def-x}
#### Concept X
Formulation A
:::
""",
        encoding="utf-8",
    )
    (repo / "b.qmd").write_text(
        """::: {#def-x}
#### Concept X
Formulation B (divergent)
:::
""",
        encoding="utf-8",
    )

    script = Path(cmd.__file__).resolve()
    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "--path",
            str(repo),
            "--fail",
            "false",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert res.returncode == 0
    assert "Divergence" in res.stdout or "Divergence" in res.stderr


def test_div_opt_out_does_not_leak_to_sibling_divs():
    """A div's own opt-out comment exempts that div only, not the rest of the file."""
    text = """
::: {#def-custom}
<!-- check-math-definitions: opt-out -->
#### Custom Def
Local definition.
:::

::: {#def-variance}
#### Variance
The variance is E[(X - E[X])^2].
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="doc.qmd",
        repo_name="mln",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    by_id = {d.div_id: d for d in divs}
    assert set(by_id) == {"def-custom", "def-variance"}
    assert by_id["def-custom"].opted_out
    assert not by_id["def-variance"].opted_out


def test_nested_div_opt_out_does_not_leak_to_enclosing_div():
    """An opt-out inside a nested math div exempts the nested div, not its parent."""
    text = """
::::: {#thm-outer}
#### Outer
Outer statement.

::: {#lem-inner}
<!-- check-math-definitions: opt-out -->
Inner statement.
:::
:::::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="doc.qmd",
        repo_name="mln",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    by_id = {d.div_id: d for d in divs}
    assert by_id["lem-inner"].opted_out
    assert not by_id["thm-outer"].opted_out


def test_file_level_opt_out_directive_exempts_every_div():
    """The separate file-level directive exempts every div in the file."""
    text = """
<!-- check-math-definitions: ignore-file -->

::: {#def-custom}
#### Custom Def
Local definition.
:::

::: {#def-variance}
#### Variance
The variance is E[(X - E[X])^2].
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="doc.qmd",
        repo_name="mln",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 2
    assert all(d.opted_out for d in divs)


# -- defaults agree across the script, action.yml and the reusable workflow --

_DIR = Path(__file__).resolve().parent.parent
_ACTION = _DIR / "action.yml"
_WORKFLOW = _DIR.parent / ".github" / "workflows" / "check-math-definitions.yml"

# Every input both files declare. A drift between them would hand a caller
# of the reusable workflow different defaults than a caller of the composite.
_SHARED_INPUTS = [
    "path",
    "paths",
    "repos",
    "paths-ignore",
    "extensions",
    "prefixes",
    "check-titles",
    "fail",
    "python-version",
]


def _yaml_default(path: Path, name: str) -> str:
    """Read one input's `default:` with a line scan, so the check does not
    depend on a YAML library being installed."""
    import re

    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^\s+{re.escape(name)}:\s*$", line):
            for follow in lines[i + 1:]:
                m = re.match(r"^\s+default:\s*(.*)$", follow)
                if m:
                    return m.group(1).strip().strip("'\"")
                if re.match(r"^\s{0,6}[a-z-]+:\s*$", follow):
                    break
    raise AssertionError(f"{path.name} declares no default for {name}")


@pytest.mark.parametrize("name", _SHARED_INPUTS)
def test_action_and_workflow_defaults_agree(name):
    assert _yaml_default(_ACTION, name) == _yaml_default(_WORKFLOW, name)


@pytest.mark.parametrize("path", [_ACTION, _WORKFLOW], ids=["action", "workflow"])
def test_yaml_defaults_agree_with_script(path):
    assert _yaml_default(path, "paths-ignore") == ", ".join(cmd.DEFAULT_PATHS_IGNORE)
    assert _yaml_default(path, "extensions") == ", ".join(cmd.DEFAULT_EXTENSIONS)
    assert _yaml_default(path, "prefixes") == ", ".join(cmd.DEFAULT_PREFIXES)


# -- cloning sibling repositories --


class _FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")


def test_clone_keeps_token_off_argv(tmp_path, monkeypatch):
    fake = _FakeRun()
    monkeypatch.setattr(cmd.subprocess, "run", fake)
    monkeypatch.setenv("GH_TOKEN", "sekrit-token-value")
    cloned = cmd.clone_github_repos(["Morrison-Lab/rme"], tmp_path)
    assert cloned == {"rme": tmp_path / "rme"}
    (args, kwargs), = fake.calls
    assert not any("sekrit-token-value" in a for a in args)
    assert "https://github.com/Morrison-Lab/rme.git" in args
    env = kwargs["env"]
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert "sekrit-token-value" not in env["GIT_CONFIG_VALUE_0"]


@pytest.mark.parametrize("spec", ["..", "owner/..", ".", "owner/.git"])
def test_clone_refuses_unsafe_repo_names(tmp_path, monkeypatch, spec):
    fake = _FakeRun()
    monkeypatch.setattr(cmd.subprocess, "run", fake)
    assert cmd.clone_github_repos([spec], tmp_path) == {}
    assert fake.calls == []


def test_directives_quoted_in_code_blocks_do_not_opt_out():
    """A directive quoted in a code block is an example, not a directive."""
    text = """
```markdown
<!-- check-math-definitions: ignore-file -->
```

::: {#def-variance}
#### Variance
The variance is E[(X - E[X])^2].

```markdown
<!-- check-math-definitions: opt-out -->
```
:::
"""
    divs = cmd.parse_math_divs_from_text(
        text=text,
        file_path="doc.qmd",
        repo_name="mln",
        allowed_prefixes=set(cmd.DEFAULT_PREFIXES),
    )
    assert len(divs) == 1
    assert not divs[0].opted_out
