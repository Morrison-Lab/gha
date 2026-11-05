"""Unit tests for check-code-fold.

Covers what is flagged (``code-fold: false`` in the option block of an
executed chunk), what is not (``show``, ``true``, plain fences, option text
after the code, front matter), diff scoping, and the defaults the script, the
action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_code_fold", _DIR / "check-code-fold.py"
)
assert _spec is not None and _spec.loader is not None
ccf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccf)


def flagged(text: str):
    return [n for n, _ in ccf.fold_false_options(text.split("\n"))]


def chunk(options: str, engine: str = "r", body: str = "x <- 1") -> str:
    return f"```{{{engine}}}\n{options}\n{body}\n```"


@pytest.mark.parametrize("engine", ["r", "python", "julia", "r, echo=TRUE"])
def test_false_in_an_executed_chunk_is_flagged(engine):
    assert flagged(chunk("#| code-fold: false", engine)) == [2]


@pytest.mark.parametrize("option", [
    "#| code-fold: FALSE", "#|code-fold: false", '#| code-fold: "false"',
    "#| code-fold:   false  ",
])
def test_spelling_variants_are_flagged(option):
    assert flagged(chunk(option)) == [2]


@pytest.mark.parametrize("option", [
    "#| code-fold: show", "#| code-fold: true", "#| code-fold: TRUE",
    "#| echo: false", "#| code-fold-x: false", "#| code-folded: false",
])
def test_other_options_are_not_flagged(option):
    assert flagged(chunk(option)) == []


def test_option_among_others_is_flagged_at_its_line():
    assert flagged(chunk("#| label: a\n#| code-fold: false\n#| echo: true")) == [3]


def test_a_plain_fence_is_not_flagged():
    assert flagged("```\n#| code-fold: false\n```") == []
    assert flagged("```r\n#| code-fold: false\n```") == []


def test_option_text_after_the_code_is_not_flagged():
    assert flagged(chunk("#| label: a", body="x <- 1\n#| code-fold: false")) == []


def test_front_matter_is_not_examined():
    assert flagged("---\ncode-fold: false\n---\n\ntext") == []


def test_chunks_in_a_tabset_are_flagged_and_closing_fence_resets():
    text = "::: {.panel-tabset}\n" + chunk("#| code-fold: false") + "\n\n" \
           + chunk("#| code-fold: true", "python") + "\n:::"
    assert flagged(text) == [3]


def test_indented_chunk_is_flagged():
    assert flagged("  ```{r}\n  #| code-fold: false\n  x\n  ```") == [2]


def test_added_lines_scopes_the_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +5,2 @@\n+x\n+y\n+++ /dev/null\n"
    assert ccf.added_lines(diff) == {"a.qmd": {5, 6}}


def test_defaults_agree_across_script_action_and_workflow():
    def input_block(text: str, name: str) -> str:
        start = text.index(f"\n      {name}:" if "workflow_call" in text else f"\n  {name}:")
        return text[start:].split("\n\n")[0]

    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-code-fold.yml").read_text()
    assert ccf._flag("CCF_FAIL", True) is True  # the script's default, with the variable unset
    assert "default: 'true'" in input_block(action, "fail")
    assert "default: true" in input_block(workflow, "fail")
    assert "default: '*.qmd'" in input_block(action, "globs")
    assert "default: '*.qmd'" in input_block(workflow, "globs")
