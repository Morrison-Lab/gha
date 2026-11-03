"""Unit tests for check-unexplained-choices (ai-config#4905).

The regression case is lds `fig-logistic-regression`: age cut into three-year
bins in a chunk whose caption never says why.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_unexplained_choices", _DIR / "check-unexplained-choices.py"
)
assert _spec is not None and _spec.loader is not None
uac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(uac)

FENCE = "`" * 3


def hits(text: str):
    return [(f.line, f.phrase) for f in uac.scan_choices(text.split("\n"))]


LDS_FIGURE = f"""::: {{#fig-logistic-regression}}

{FENCE}{{r}}
lrf_bins <- cut(wcgs_exm$age, breaks = c(38, 41, 44, 47))
{FENCE}

The groups are ages 39 to 41, 42 to 44 and 45 to 47.

:::
"""


def test_the_lds_binning_with_no_reason_is_flagged():
    assert hits(LDS_FIGURE) == [(4, "cut")]


def test_a_stated_reason_in_the_same_div_clears_it():
    text = LDS_FIGURE.replace(
        "The groups are ages 39 to 41, 42 to 44 and 45 to 47.",
        "Three-year groups are a compromise: wider ones hide the trend.",
    )
    assert hits(text) == []


def test_a_reason_inside_a_nested_tabset_div_counts_for_the_outer_unit():
    text = f"""::: {{#fig-a}}

::: {{.panel-tabset}}

{FENCE}{{r}}
x <- cut(a, breaks = 3)
{FENCE}

:::

We chose three groups because the data hold three clusters.

:::
"""
    assert hits(text) == []


def test_a_bin_outside_any_div_is_read_against_its_section():
    text = f"""# Simulation

{FENCE}{{r}}
x <- cut(a, breaks = 3)
{FENCE}

The draws are shown below.

# Next section

Because the seed matters here, it is stated.
"""
    assert hits(text) == [(4, "cut")]


def test_a_seed_is_not_a_recognized_choice():
    text = f"""{FENCE}{{r}}
set.seed(1)
{FENCE}
"""
    assert hits(text) == []


def test_the_default_fails_and_false_warns():
    assert uac._DEFAULT_FAIL is True


def test_ordinary_code_and_comments_are_not_flagged():
    text = f"""{FENCE}{{r}}
#| fig-height: 4
# cut(x, breaks = 3)
fit <- lm(y ~ x, data = d)
{FENCE}
"""
    assert hits(text) == []


def test_the_allow_marker_exempts_a_line():
    text = f"""{FENCE}{{r}}
x <- cut(a, breaks = 3)  # check-unexplained-choices: allow
{FENCE}
"""
    assert hits(text) == []


def test_a_reason_in_an_html_comment_or_math_does_not_count():
    text = f"""::: {{#fig-a}}

{FENCE}{{r}}
x <- cut(a, breaks = 3)
{FENCE}

<!-- because we like it -->

:::
"""
    assert hits(text) == [(4, "cut")]


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def test_run_check_reports_only_added_lines(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    page = tmp_path / "p.qmd"
    page.write_text(LDS_FIGURE)
    _git(tmp_path, "add", "p.qmd")
    _git(tmp_path, "commit", "-q", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD").strip()
    page.write_text(LDS_FIGURE + "\nA later paragraph.\n")
    _git(tmp_path, "commit", "-qam", "edit")
    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        edit_only = uac.run_check(base, ["*.qmd"], [], False)
        whole = uac.run_check("", ["*.qmd"], [], True)
    finally:
        os.chdir(cwd)
    assert edit_only.findings == []
    assert [(r, f.phrase) for r, f in whole.findings] == [("p.qmd", "cut")]
