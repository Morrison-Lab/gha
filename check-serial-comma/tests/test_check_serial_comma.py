"""Unit tests for check-serial-comma.

Covers what is flagged (a list of three or more items with no comma before
the final "and" or "or", also across a semantic line break and with math
items), what is not (a serial comma, a pair after an introductory phrase,
code, comments, tables, the allow marker), diff scoping, and the defaults
the script, the action and the reusable workflow must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_serial_comma", _DIR / "check-serial-comma.py"
)
assert _spec is not None and _spec.loader is not None
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def flagged(text: str):
    return [n for n, _ in sc.findings(text.split("\n"))]


@pytest.mark.parametrize("text", [
    "We fit linear models, trees and forests.",
    "We fit linear models, trees or forests.",
    "Report the mean, median and mode of the sample.",
    "Let $a$, $b$ and $c$ be real numbers.",
    "The `lm`, `glm` and `nls` functions fit models.",
    "The data have 1, 2 and 3 as values.",
    "- Fit the model, check the residuals and report the result.",
    "The rows are sorted, filtered or grouped.",
    "We tried walking, jogging and running.",
    "# Bias, variance and noise",
    "In practice, we use means, medians and modes.",
])
def test_missing_serial_comma_is_flagged(text):
    assert flagged(text) == [1]


@pytest.mark.parametrize("text", [
    "We fit linear models, trees, and forests.",
    "We fit linear models, trees, or forests.",
    "We fit linear models and trees.",
    "However, x and y differ.",
    "In practice, a and b differ.",
    "The check skips a pair (\"However, x and y\") after a phrase.",
    "The means differ, however, x and y agree.",
    "If the sample is large, the mean and median agree.",
    "For example, a and b differ.",
    "Use e.g., means and medians.",
    "Say whether the sample is large, or not.",
    "It is large, and it is small.",
    "The values are 1,000 and 2,000.",
    "Ask whether it holds, whether or not it is true.",
    "| a, b and c | d |",
    "It now cancels a PR's older preview deploy, queued or running, first.",
    "It cancels the same PR's older deploy, queued or running.",
    "We fit linear models, trees and forests. <!-- check-serial-comma: allow -->",
])
def test_other_prose_is_not_flagged(text):
    assert flagged(text) == []


def test_sentence_split_across_lines_is_flagged_on_the_conjunction_line():
    assert flagged("We compare the mean,\nthe median\nand the mode.") == [3]


def test_two_sentences_are_checked_separately():
    assert flagged("We fit trees. Then, a and b differ.") == []
    assert flagged("We fit trees. We fit means, medians and modes.") == [1]


@pytest.mark.parametrize("body", [
    "```r\nx <- c(a, b and c)\n```",
    "<!-- means, medians and modes -->",
    "---\ntitle: Means, medians and modes\n---",
])
def test_non_prose_is_skipped(body):
    assert flagged(body) == []


def test_added_lines_scope():
    diff = "+++ b/a.qmd\n@@ -0,0 +2,2 @@\n+x\n+y\n+++ b/b.qmd\n@@ -3 +3 @@\n+z\n"
    assert sc.added_lines(diff) == {"a.qmd": {2, 3}, "b.qmd": {3}}


def test_split_list_accepts_commas_and_newlines():
    assert sc.split_list("a/**, b\n\nc ,") == ["a/**", "b", "c"]
    assert sc.split_list("") == []


def test_exclude_specs_use_glob_magic_only_for_wildcards():
    assert sc.exclude_specs(["vendor/", "a/**"]) == [
        ":(exclude)vendor/", ":(exclude,glob)a/**"]


def test_paths_ignore_skips_files_in_a_whole_tree_run(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       stdout=subprocess.DEVNULL)

    git("init", "-q")
    for name in ("own.qmd", "vendor/other.qmd"):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("We fit trees, means and modes.\n", encoding="utf-8")
    git("add", ".")
    monkeypatch.chdir(tmp_path)
    kept = sc.wanted_lines("", ["*.qmd"], True, ["vendor/**"])
    assert sorted(kept) == ["own.qmd"]
    assert sorted(sc.wanted_lines("", ["*.qmd"], True)) == ["own.qmd", "vendor/other.qmd"]


def test_defaults_agree():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    workflow = (_DIR.parent / ".github/workflows/check-serial-comma.yml").read_text(
        encoding="utf-8"
    )
    for text in (action, workflow):
        assert "default: '*.qmd *.md'" in text
    fail_default = re.compile(r"\n( +)fail:\n(?:\1  .*\n)*?\1  default: '?true'?\n")
    assert fail_default.search(action)
    assert fail_default.search(workflow)
    assert sc._flag("SC_FAIL_UNSET_FOR_TEST", True) is True
    assert sc.DEFAULT_GLOBS == "*.qmd *.md"
