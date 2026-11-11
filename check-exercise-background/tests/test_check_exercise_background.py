"""Unit tests for check-exercise-background.

Covers what is flagged (a title word the body never mentions), what is not
(a word the body repeats or shares a stem with, generic task verbs, math in the
title, text outside an exercise, code, comments), and diff scoping.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_exercise_background", _DIR / "check-exercise-background.py"
)
assert _spec is not None and _spec.loader is not None
exb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exb)


def exercise(title: str, body: str, attrs: str = "{#exr-a}") -> str:
    return f"::: {attrs}\n#### {title}\n\n{body}\n:::"


def found(text: str):
    return [(f.line, f.missing) for f in exb.exercises(text.split("\n"))]


def test_title_word_missing_from_the_body_is_flagged():
    text = exercise("Maximizing a gamma-family kernel",
                    "Find the maximum value of $f(x) = x^4 e^{-x}$.")
    assert found(text) == [(2, ["gamma", "family", "kernel"])]


def test_background_in_the_body_clears_the_finding():
    body = ("The gamma distributions form a family. Its kernel is the part "
            "that depends on $x$. Find the maximum.")
    assert found(exercise("Maximizing a gamma-family kernel", body)) == []


@pytest.mark.parametrize("title, body", [
    ("Maximizing a function", "Find the maximum of the function."),
    ("Classifying a point", "Classify the point."),
    ("Plot the data", "Show the data."),
])
def test_a_word_sharing_five_letters_with_the_body_counts_as_present(title, body):
    assert found(exercise(title, body)) == []


@pytest.mark.parametrize("title", [
    "Find it", "Compute and check", "Differentiate", "Show that",
])
def test_generic_task_titles_are_not_flagged(title):
    assert found(exercise(title, "Do the thing.")) == []


def test_only_defined_terms_are_reported():
    text = exercise("Maximizing a gamma-family kernel", "Find the maximum.")
    defined = exb.defined_stems(["::: {#def-kernel}", "#### Kernel", ":::"])
    out = [(f.line, f.missing) for f in exb.exercises(text.split("\n"), defined)]
    assert out == [(2, ["kernel"])]


def test_defined_stems_reads_a_title_attribute():
    assert "gamma" in exb.defined_stems(['::: {#def-g title="Gamma family"}'])


def test_a_plural_title_word_matches_its_singular_in_the_body():
    assert found(exercise("Slope for the means", "The slope uses the mean of $x$.")) == []


def test_a_part_that_reuses_an_earlier_setup_is_not_flagged():
    body = "Use the setup of @exr-a.\nFind the kernel."
    assert found(exercise("The kernel (part 2)", body)) == []


def test_math_in_the_title_is_ignored():
    assert found(exercise("Slope at $w = 1$ of the curve", "The slope of the curve.")) == []


def test_a_link_target_is_not_body_text():
    assert found(exercise("Kernel", "See [x](kernel.qmd).")) == [(2, ["kernel"])]


def test_text_outside_an_exercise_is_not_checked():
    assert found("::: {#exm-a}\n#### Gamma kernel\n\nNothing.\n:::") == []


def test_solution_div_is_not_the_exercise_body():
    text = exercise("Gamma kernel", "Nothing.") + "\n\n::: {#sol-a}\nGamma kernel.\n:::"
    assert found(text) == [(2, ["gamma", "kernel"])]


def test_nested_div_counts_as_body():
    text = ("::: {#exr-a}\n#### Gamma kernel\n\nText.\n\n"
            "::: {.callout-note}\nA gamma kernel.\n:::\n:::")
    assert found(text) == []


def test_a_nested_solution_does_not_supply_the_background():
    text = ("::: {#exr-a}\n#### Gamma kernel\n\nFind it.\n\n"
            "::: {#sol-a}\nThe gamma kernel.\n:::\n:::")
    assert found(text) == [(2, ["gamma", "kernel"])]


def test_a_title_attribute_is_read():
    text = '::: {#exr-a title="Gamma kernel"}\nFind the maximum.\n:::'
    assert found(text) == [(1, ["gamma", "kernel"])]
    assert found('::: {#exr-a title="Gamma kernel"}\nThe gamma kernel.\n:::') == []


def test_code_and_comments_are_skipped():
    text = ("::: {#exr-a}\n#### Gamma kernel\n\n```r\ngamma kernel\n```\n"
            "<!-- gamma kernel -->\nNothing.\n:::")
    assert found(text) == [(2, ["gamma", "kernel"])]


def test_an_exercise_without_a_heading_is_not_flagged():
    assert found("::: {#exr-a}\nFind the maximum.\n:::") == []


def test_added_lines_scopes_the_diff():
    diff = "+++ b/a.qmd\n@@ -1,0 +5,2 @@\n+x\n+y\n+++ /dev/null\n"
    assert exb.added_lines(diff) == {"a.qmd": {5, 6}}


def test_a_finding_needs_an_added_line_inside_the_exercise():
    finding = exb.Finding(line=3, title="t", missing=["x"], start=2, end=8)
    assert exb.touched(finding, {5}) is True
    assert exb.touched(finding, {20}) is False
    assert exb.touched(finding, None) is True


def test_defaults_agree_across_script_action_and_workflow():
    def input_block(text: str, name: str) -> str:
        start = text.index(f"\n      {name}:" if "workflow_call" in text else f"\n  {name}:")
        return text[start:].split("\n\n")[0]

    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github/workflows/check-exercise-background.yml").read_text()
    assert exb._flag("EXB_FAIL", False) is False  # the script's default, with the variable unset
    assert "default: 'false'" in input_block(action, "fail")
    assert "default: false" in input_block(workflow, "fail")
    assert "default: '*.qmd'" in input_block(action, "globs")
    assert "default: '*.qmd'" in input_block(workflow, "globs")


def test_corpus_reads_tracked_files_and_is_empty_without_defs(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "a.qmd").write_text("::: {#def-g}\n#### Gamma kernel\n:::\n")
    (tmp_path / "b.qmd").write_text("Nothing defined here.\n")
    subprocess.run(["git", "add", "a.qmd", "b.qmd"], check=True)
    assert exb.corpus(["*.qmd"])[0] == {"gamma", "kerne"}
    assert exb.corpus(["b.qmd"])[0] == set()


def test_main_notes_when_no_definitions_exist(tmp_path, monkeypatch, capsys):
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "a.qmd").write_text(exercise("Gamma kernel", "Find it."))
    subprocess.run(["git", "add", "a.qmd"], check=True)
    monkeypatch.setenv("EXB_WHOLE_TREE", "true")
    assert exb.main() == 0
    assert "::notice::No #def- titles" in capsys.readouterr().out


# False-positive classes found by the whole-tree runs on lds, mds, pds, sds
# and psw (gha#1481). Each case passes only through the rule named.


def defs(*titles):
    lines = []
    for i, t in enumerate(titles):
        lines += [f"::: {{#def-t{i}}}", f"#### {t}", ":::"]
    return exb.defined_stems(lines)


def found_with(text, defined):
    lines = text.split("\n")
    return [f.missing for f in exb.exercises(lines, defined, exb.div_texts(lines))]


def test_a_cited_exercise_supplies_background_transitively():
    d = defs("Kernel")
    first = exercise("A start", "Here is the kernel.", "{#exr-one}")
    second = exercise("Next", "Continue @exr-one.", "{#exr-two}")
    third = exercise("The kernel", "Use @exr-two.", "{#exr-three}")
    text = "\n".join([first, second, third])
    assert found_with(text, d) == []


def test_an_unknown_cited_exercise_skips_the_exercise():
    d = defs("Kernel")
    assert found_with(exercise("The kernel", "Use @exr-elsewhere."), d) == []


def test_a_linked_definition_supplies_background():
    d = defs("Kernel")
    text = ("::: {#def-kernel}\n#### Kernel\nA kernel is ...\n:::\n"
            + exercise("The kernel", "See [this](#def-kernel)."))
    assert found_with(text, d) == []


def test_a_solution_counts_only_when_cited():
    d = defs("Kernel")
    sol = "::: {#sol-k}\nThe kernel.\n:::"
    uncited = exercise("The kernel", "Find it.") + "\n" + sol
    cited = exercise("The kernel", "Use @sol-k.") + "\n" + sol
    assert found_with(uncited, d) == [["kernel"]]
    assert found_with(cited, d) == []


def test_a_cited_exercise_lends_its_text_but_not_its_solution():
    d = defs("Kernel")
    first = ("::: {#exr-one}\n#### A start\n\nFind it.\n\n"
             "::: {#sol-one}\nThe kernel.\n:::\n:::")
    second = exercise("The kernel", "Continue @exr-one.", "{#exr-two}")
    assert found_with(first + "\n" + second, d) == [["kernel"]]


def test_corpus_returns_the_div_texts_of_every_file(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "a.qmd").write_text("::: {#def-g}\n#### Gamma kernel\nA kernel.\n:::\n")
    subprocess.run(["git", "add", "a.qmd"], check=True)
    assert "kernel" in exb.corpus(["*.qmd"])[1]["def-g"]


def test_a_definition_cited_from_another_file_supplies_background(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "a.qmd").write_text("::: {#def-k}\n#### Kernel\nA kernel is ...\n:::\n")
    (tmp_path / "b.qmd").write_text(exercise("The kernel", "Use @def-k."))
    subprocess.run(["git", "add", "a.qmd", "b.qmd"], check=True)
    defined, index = exb.corpus(["*.qmd"])
    lines = (tmp_path / "b.qmd").read_text().split("\n")
    assert [f.missing for f in exb.exercises(lines, defined, index)] == []
    assert [f.missing for f in exb.exercises(lines, defined)] == [["kernel"]]


def test_a_citation_cycle_terminates():
    d = defs("Kernel")
    first = exercise("The kernel", "Continue @exr-two.", "{#exr-one}")
    second = exercise("Next", "Continue @exr-one.", "{#exr-two}")
    assert found_with(first + "\n" + second, d) == [["kernel"]]
