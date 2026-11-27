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


def missing(text: str, default_fold: bool = False):
    return ccf.missing_summaries(text.split("\n"), default_fold)


@pytest.mark.parametrize("option", [
    "#| code-fold: true", "#| code-fold: show", '#| code-fold: "true"',
    "#| code-fold: TRUE",
])
def test_a_folded_chunk_without_a_summary_is_flagged(option):
    assert missing(chunk(option)) == [1]


@pytest.mark.parametrize("options", [
    '#| code-fold: true\n#| code-summary: "Code: fit the model"',
    "#| code-fold: false",
    "#| code-fold: true\n#| echo: false",
    "#| code-fold: true\n#| include: false",
    "#| label: a",
])
def test_unfolded_hidden_or_summarized_chunks_pass(options):
    assert missing(chunk(options)) == []


def test_default_fold_makes_a_chunk_with_no_code_fold_fold():
    assert missing(chunk("#| label: a"), default_fold=True) == [1]
    assert missing(chunk("#| code-fold: false"), default_fold=True) == []


def test_an_empty_summary_counts_as_missing():
    assert missing(chunk('#| code-fold: true\n#| code-summary: ""')) == [1]


def test_options_after_the_code_do_not_count():
    text = chunk("#| code-fold: true", body='x <- 1\n#| code-summary: "late"')
    assert missing(text) == [1]


def test_a_plain_fence_is_not_a_chunk():
    assert missing("```r\n#| code-fold: true\n```", default_fold=True) == []


def test_each_chunk_is_reported_at_its_fence():
    text = chunk("#| code-fold: true") + "\n\n" + chunk(
        '#| code-fold: show\n#| code-summary: "Code: plot"', "python")
    assert missing(text) == [1]
    assert missing(text + "\n\n" + chunk("#| code-fold: show")) == [1, 12]


def test_main_flags_only_a_new_chunk(tmp_path, monkeypatch, capsys):
    import subprocess

    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "ci@example.com")  # phi-allow
    git("config", "user.name", "ci")
    page = tmp_path / "page.qmd"
    page.write_text(chunk("#| code-fold: true") + "\n")
    git("add", "page.qmd")
    git("commit", "-qm", "base")
    page.write_text(chunk("#| code-fold: true") + "\n\n"
                    + chunk("#| code-fold: true", "python") + "\n")
    git("commit", "-qam", "add a chunk")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CCF_BASE_REF", "HEAD^1")
    monkeypatch.setenv("CCF_REQUIRE_SUMMARY", "true")
    assert ccf.main() == 1
    out = capsys.readouterr().out
    assert "line=6::New chunk folds" in out
    assert "line=1::" not in out
    monkeypatch.setenv("CCF_REQUIRE_SUMMARY", "false")
    assert ccf.main() == 0


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
    for name, var in (("require-summary", "CCF_REQUIRE_SUMMARY"),
                      ("default-fold", "CCF_DEFAULT_FOLD")):
        assert ccf._flag(var, False) is False
        assert "default: 'false'" in input_block(action, name)
        assert "default: false" in input_block(workflow, name)
        assert f"{name}: ${{{{ inputs.{name} }}}}" in workflow
        assert f"{var}: ${{{{ inputs.{name} }}}}" in action
