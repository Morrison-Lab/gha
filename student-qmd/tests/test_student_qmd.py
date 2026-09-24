# check-one-function-per-file: allow-multiple
"""Tests for make_student_qmd.py and check_student_qmd.py.

Every fixture is written into tmp_path at test time: a committed .qmd holding
answers would be swept into other jobs' scans, and a committed student file
would go stale against the generator.

The negative controls are the ones ported from Morrison-Lab/mlg#22. Each takes
a correctly generated student file, damages it in one way, and asserts the
check fails and says why; without them, a check that passed everything would
look the same as one that works. Tests that read documents with Quarto's
Pandoc skip when quarto is not installed, unless STUDENT_QMD_REQUIRE_QUARTO=1,
which CI sets so a missing Quarto cannot turn the suite into a skip.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_student_qmd  # noqa: E402
import make_student_qmd  # noqa: E402
from student_qmd_common import (  # noqa: E402
    Config,
    StudentQmdError,
    expand_includes,
    find_sources,
    resolve_include,
)
from student_qmd_macros import MacroDef, MacroError, brace_depth, macro_groups, prune_macros  # noqa: E402

HAVE_QUARTO = shutil.which("quarto") is not None
needs_quarto = pytest.mark.skipif(
    not HAVE_QUARTO and os.environ.get("STUDENT_QMD_REQUIRE_QUARTO") != "1",
    reason="quarto is not installed",
)

ANSWER_A = "Overfitting is when a model fits the noise in its training data."
ANSWER_B = "42"

FRAGMENT = f"""---
# names the assign filter, so the fragment rendered alone hides its answer
filters:
  - ../../_extensions/coatless-quarto/assign/assign.lua
---

::: {{#exr-a}}
Define overfitting.
:::

::: {{.sol}}
{ANSWER_A}
:::
"""

HOMEWORK = f"""---
title: "Homework 1"
# a whole-line comment, which the generator drops
format: html
---

Answer every question.

<!-- instructor note: grade leniently -->

{{{{< include /exercises/topic/_exr-a.qmd >}}}}

::: {{#exr-b}}
What is 6 times 7?
:::

::: {{.sol}}
{ANSWER_B}
:::
"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A Quarto project with one homework including one fragment."""
    write(tmp_path / "_quarto.yml", "project:\n  type: default\n")
    write(tmp_path / "exercises" / "topic" / "_exr-a.qmd", FRAGMENT)
    write(tmp_path / "hw" / "hw1.qmd", HOMEWORK)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def generate(*extra: str, sources: tuple[str, ...] = ("hw/*.qmd",)) -> int:
    return make_student_qmd.main([*sources, "--output-dir", "out", *extra])


def check(*extra: str, sources: tuple[str, ...] = ("hw/*.qmd",)) -> int:
    return check_student_qmd.main([*sources, "--output-dir", "out", *extra])


def student(project: Path) -> Path:
    return project / "out" / "hw1.qmd"


# --- the generator, which needs no Quarto -----------------------------------


def test_generator_inlines_includes_and_drops_answers(project):
    assert generate() == 0
    text = student(project).read_text()
    assert "Define overfitting." in text
    assert "What is 6 times 7?" in text
    assert ANSWER_A not in text
    assert "\n42\n" not in text
    assert "include" not in text
    assert "assign.lua" not in text


def test_generator_drops_fragment_filters_silently(project, capsys):
    assert generate() == 0
    assert "front matter" not in capsys.readouterr().out


def test_generator_warns_about_other_fragment_metadata(project, capsys):
    # Quarto merges an included file's front matter into the document, so a
    # key other than `filters` would change the render; dropping it is
    # warned about rather than silent.
    write(project / "exercises" / "topic" / "_exr-a.qmd", FRAGMENT.replace("filters:", "bibliography: refs.bib\nfilters:", 1))
    assert generate() == 0
    out = capsys.readouterr().out
    assert "::warning::" in out and "sets bibliography" in out
    assert "bibliography" not in student(project).read_text()


def test_generator_drops_whole_line_yaml_comment_and_html_comment(project):
    assert generate() == 0
    text = student(project).read_text()
    assert "whole-line comment" not in text
    assert "instructor note" not in text
    assert 'title: "Homework 1"' in text


def test_generator_drops_two_line_sol_opener(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + '\n::: {.sol\n  data-x="1"}\nsecret answer\n:::\n')
    assert generate() == 0
    assert "secret answer" not in student(project).read_text()


FIVE_SPELLINGS = (
    '\n::: {data-note="}" .sol}\nsecret one\n:::\n'
    "\n::: sol\nsecret two\n:::\n"
    '\n::: {.content-visible when-profile="solution"}\nsecret three\n:::\n'
    '\n::: {.content-hidden unless-profile="solution"}\nsecret four\n:::\n'
    '\n::: {.content-visible unless-profile="assign"}\nsecret five\n:::\n'
)


def test_generator_drops_quoted_brace_bare_and_profile_divs(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + FIVE_SPELLINGS)
    assert generate() == 0
    text = student(project).read_text()
    for word in ("one", "two", "three", "four", "five"):
        assert f"secret {word}" not in text


@needs_quarto
def test_checker_agrees_on_quoted_brace_bare_and_profile_divs(project):
    """The writer's line scan and the checker's Pandoc AST must agree that
    each of these spellings is an answer div, or the check would fail a
    correct file (or pass a wrong one) on exactly these."""
    write(project / "hw" / "hw1.qmd", HOMEWORK + FIVE_SPELLINGS)
    assert generate() == 0
    assert check() == 0


RAW_ANSWER_DIVS = {
    "hidden class": '<div class="sol">\nsecret raw\n</div>\n',
    "upper case": '<DIV CLASS="other sol">\nsecret raw\n</DIV>\n',
    "tag over two lines": '<div id="x"\n     class="sol">\nsecret raw\n</div>\n',
    "profile div": '<div class="content-visible" when-profile="solution">\nsecret raw\n</div>\n',
    "data- profile div": '<div class="content-hidden" data-unless-profile="solution">\nsecret raw\n</div>\n',
    "repeated class, first wins": '<div class="sol" class="note">\nsecret raw\n</div>\n',
    "repeated class, case differs": '<div CLASS="sol" class="note">\nsecret raw\n</div>\n',
}


@pytest.mark.parametrize("div", RAW_ANSWER_DIVS.values(), ids=RAW_ANSWER_DIVS.keys())
def test_generator_refuses_raw_html_answer_div(project, capsys, div):
    """Pandoc reads a raw <div class="sol"> as the same div as ::: {.sol},
    so the assign filter hides it, but the writer removes only ::: divs.
    Copied through, it would leak the answer with check: false."""
    source = HOMEWORK + "\n" + div
    write(project / "hw" / "hw1.qmd", source)
    assert generate() == 1
    assert not student(project).exists()
    out = capsys.readouterr().out
    line = source.splitlines().index(div.splitlines()[0]) + 1
    assert f"hw1.qmd:{line}: an answer in a raw HTML <div>" in out
    assert "::: div" in out


def test_generator_names_the_included_file_holding_a_raw_div(project, capsys):
    fragment = project / "exercises" / "topic" / "_exr-a.qmd"
    write(fragment, FRAGMENT + '\n<div class="sol">\nsecret raw\n</div>\n')
    assert generate() == 1
    line = len(FRAGMENT.splitlines()) + 2
    assert f"_exr-a.qmd:{line}: an answer in a raw HTML <div>" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text",
    [
        '<div class="note">\nA hint for students.\n</div>\n',
        '```html\n<div class="sol">shown as code</div>\n```\n',
        'Write `<div class="sol">` in HTML, or better, `::: {.sol}`.\n',
        '<!-- <div class="sol"> -->\n',
        '<div class="note" class="sol">\nPandoc keeps the first class.\n</div>\n',
    ],
    ids=["benign class", "code block", "code span", "comment", "repeated class, benign first"],
)
def test_generator_allows_other_raw_divs(project, text):
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\n" + text)
    assert generate() == 0


@needs_quarto
def test_benign_raw_div_passes_the_check(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + '\n<div class="note">\nA hint for students.\n</div>\n')
    assert generate() == 0
    assert "A hint for students." in student(project).read_text()
    assert check() == 0


@needs_quarto
def test_checker_refuses_raw_html_answer_div_in_source(project, capsys):
    """The check refuses a source carrying a raw answer div even when the
    student file predates it (a stale output directory, say), so the
    refusal comes from scanning the source, not from the AST comparison."""
    assert generate() == 0
    write(project / "hw" / "hw1.qmd", HOMEWORK + '\n<div class="sol">\nsecret raw\n</div>\n')
    assert check() == 1
    assert "an answer in a raw HTML <div>" in capsys.readouterr().out


def test_generator_keeps_student_profile_div(project):
    write(
        project / "hw" / "hw1.qmd",
        HOMEWORK + '\n::: {.content-visible when-profile="assign"}\n\\vspace{2in}\n:::\n',
    )
    assert generate() == 0
    assert "vspace" in student(project).read_text()


def test_nested_include_resolves_against_the_top_document(tmp_path):
    """Quarto resolves a nested include against the rendered document's
    directory, not the including file's; the two rules pick different files
    here."""
    write(tmp_path / "doc.qmd", "{{< include sub/outer.qmd >}}\n")
    write(tmp_path / "sub" / "outer.qmd", "{{< include inner.qmd >}}\n")
    write(tmp_path / "inner.qmd", "top-level inner\n")
    write(tmp_path / "sub" / "inner.qmd", "sibling inner\n")
    assert expand_includes(tmp_path / "doc.qmd") == ["top-level inner"]


def test_leading_slash_include_needs_a_project(tmp_path):
    with pytest.raises(StudentQmdError, match="no _quarto.yml"):
        resolve_include("/x.qmd", tmp_path / "doc.qmd")


def test_include_cycle_is_an_error(tmp_path):
    write(tmp_path / "a.qmd", "{{< include b.qmd >}}\n")
    write(tmp_path / "b.qmd", "{{< include a.qmd >}}\n")
    with pytest.raises(StudentQmdError, match="cycle"):
        expand_includes(tmp_path / "a.qmd")


def test_missing_include_fails_generation(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\n{{< include nope.qmd >}}\n")
    assert generate() == 1


def test_comment_spanning_a_div_line_fails_generation(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\n<!--\n:::\n-->\n")
    assert generate() == 1


def test_mid_paragraph_comment_line_does_not_split_the_paragraph(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\nline one\n<!-- note -->\nline two\n")
    assert generate() == 0
    assert "line one\nline two" in student(project).read_text()


def test_render_chunks_dropped_but_refs_div_kept(project):
    extra = "\n::: hidden\n```sh\nquarto render hw1.qmd\n```\n:::\n\n::: {#refs}\n:::\n"
    write(project / "hw" / "hw1.qmd", HOMEWORK + extra)
    assert generate("--drop-render-chunks", "true") == 0
    text = student(project).read_text()
    assert "quarto render" not in text
    assert "::: hidden" not in text
    assert "{#refs}" in text


def test_render_chunks_kept_by_default(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\n```sh\nquarto render hw1.qmd\n```\n")
    assert generate() == 0
    assert "quarto render" in student(project).read_text()


def test_list_file_holds_absolute_paths(project):
    assert generate("--list-file", "list.txt") == 0
    lines = (project / "list.txt").read_text().splitlines()
    assert lines == [str((project / "out" / "hw1.qmd").resolve())]


def test_pattern_matching_nothing_warns(project, capsys):
    assert generate(sources=("hw/*.qmd", "exams/*.qmd")) == 0
    assert "matched no file" in capsys.readouterr().out


def test_no_source_at_all_is_an_error(project):
    with pytest.raises(StudentQmdError, match="no source matched"):
        find_sources(["exams/*.qmd"])


def test_two_sources_with_one_name_are_refused(project):
    write(project / "other" / "hw1.qmd", HOMEWORK)
    assert generate(sources=("hw/*.qmd", "other/*.qmd")) == 1


def test_empty_hidden_classes_are_refused():
    with pytest.raises(StudentQmdError, match="hidden-classes"):
        Config(hidden_classes=frozenset())


def test_hidden_class_is_not_misnamed():
    cfg = Config(hidden_classes=frozenset({"solution"}))
    assert "solution" not in cfg.misnamed
    assert "answer" in cfg.misnamed


# --- the check, which reads documents with Quarto's Pandoc -----------------


@needs_quarto
def test_check_passes_on_generated_file(project, capsys):
    assert generate() == 0
    assert check() == 0
    assert "2 answer(s) removed" in capsys.readouterr().out


# Each negative control: (id, how to damage the student file, expected message).
def _append(extra):
    return lambda text: text + extra


def _drop_exercise_b(text):
    start = text.index("::: {#exr-b}")
    end = text.index(":::", start + 3) + 3
    return text[:start] + text[end:]


def _add_metadata(text):
    return text.replace('title: "Homework 1"', 'title: "Homework 1"\nauthor: Someone', 1)


def _eol_yaml_comment(text):
    return text.replace('title: "Homework 1"', 'title: "Homework 1" # note', 1)


NEGATIVE_CONTROLS = [
    ("quoted-brace-sol", _append('\n::: {data-note="}" .sol}\nhidden\n:::\n'), "answer-key-only"),
    ("bare-sol", _append("\n::: sol\nhidden\n:::\n"), "answer-key-only"),
    (
        "solution-profile-div",
        _append('\n::: {.content-visible when-profile="solution"}\nhidden\n:::\n'),
        "answer-key-only",
    ),
    ("two-character-answer", _append(f"\n{ANSWER_B}\n"), "does not match"),
    ("leaked-paragraph", _append(f"\n{ANSWER_A}\n"), "contains solution text"),
    ("html-comment", _append("\n<!-- a note -->\n"), "HTML comment"),
    ("dropped-exercise", _drop_exercise_b, "does not match"),
    ("include", _append("\n{{< include /exercises/topic/_exr-a.qmd >}}\n"), "include shortcode"),
    ("added-metadata", _add_metadata, "metadata differs"),
    ("eol-yaml-comment", _eol_yaml_comment, "YAML comment"),
    ("render-chunk", _append("\n```sh\nquarto render hw1.qmd\n```\n"), "quarto render"),
]


@needs_quarto
@pytest.mark.parametrize(
    "damage,expected", [c[1:] for c in NEGATIVE_CONTROLS], ids=[c[0] for c in NEGATIVE_CONTROLS]
)
def test_check_fails_on_damaged_student_file(project, capsys, damage, expected):
    assert generate("--drop-render-chunks", "true") == 0
    path = student(project)
    path.write_text(damage(path.read_text()))
    assert check("--drop-render-chunks", "true") == 1
    assert expected in capsys.readouterr().out


@needs_quarto
def test_check_fails_on_missing_student_file(project, capsys):
    assert check() == 1
    assert "missing" in capsys.readouterr().out


@needs_quarto
@pytest.mark.parametrize("opener", ["::: {.solution}", "::: solution", "::: {.answer}"])
def test_check_refuses_misnamed_answer_div_in_source(project, capsys, opener):
    write(project / "hw" / "hw1.qmd", HOMEWORK + f"\n{opener}\nan answer\n:::\n")
    assert generate() == 0
    assert check() == 1
    assert "does not hide" in capsys.readouterr().out


@needs_quarto
def test_check_accepts_a_caller_hidden_class(project):
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\n::: {.solution}\nan answer\n:::\n")
    assert generate("--hidden-classes", "sol solution") == 0
    assert check("--hidden-classes", "sol solution") == 0


@needs_quarto
def test_check_passes_after_two_line_opener_and_mid_paragraph_comment(project):
    extra = '\n::: {.sol\n  data-x="1"}\nsecret\n:::\n\nline one\n<!-- note -->\nline two\n'
    write(project / "hw" / "hw1.qmd", HOMEWORK + extra)
    assert generate() == 0
    assert check() == 0


@needs_quarto
def test_check_parses_executable_cells(project):
    """Plain Pandoc misreads ```{r} as inline code, which would swallow the
    rest of the document; the check reads the cell as a code block."""
    extra = "\n```{r}\n#| echo: false\nx <- 1 + 1\n```\n\nAfter the cell.\n"
    write(project / "hw" / "hw1.qmd", HOMEWORK + extra)
    assert generate() == 0
    assert check() == 0
    path = student(project)
    path.write_text(path.read_text().replace("After the cell.", "After the cell, changed."))
    assert check() == 1


@needs_quarto
def test_check_ignores_citation_renumbering(project):
    """A citation inside a removed answer shifts every later citation's note
    number, which is not a change to the question."""
    write(
        project / "hw" / "hw1.qmd",
        HOMEWORK.replace(ANSWER_B, f"{ANSWER_B} [@knuth]") + "\nSee [@lamport].\n",
    )
    assert generate() == 0
    assert check() == 0


@needs_quarto
def test_check_passes_with_render_chunks_dropped(project):
    extra = "\n::: hidden\n```sh\nquarto render hw1.qmd\n```\n:::\n\n::: {#refs}\n:::\n"
    write(project / "hw" / "hw1.qmd", HOMEWORK + extra)
    assert generate("--drop-render-chunks", "true") == 0
    assert check("--drop-render-chunks", "true") == 0


NO_ANSWERS = """---
title: "Reading"
---

::: {#exr-c}
Read chapter 1.
:::
"""


@needs_quarto
def test_source_without_answers_fails_by_default(project, capsys):
    write(project / "hw" / "hw2.qmd", NO_ANSWERS)
    assert generate() == 0
    assert check() == 1
    assert "no answer-key-only divs" in capsys.readouterr().out


@needs_quarto
def test_source_without_answers_warns_when_not_required(project, capsys):
    write(project / "hw" / "hw2.qmd", NO_ANSWERS)
    assert generate() == 0
    assert check("--require-answers", "false") == 0
    assert "::warning::" in capsys.readouterr().out


@needs_quarto
def test_no_answers_anywhere_fails_even_when_not_required(project, capsys):
    write(project / "hw" / "hw1.qmd", NO_ANSWERS)
    assert generate() == 0
    assert check("--require-answers", "false") == 1
    assert "nothing was tested" in capsys.readouterr().out


def test_bad_boolean_is_refused(project):
    assert check("--require-answers", "maybe") == 1


# --- prune-macros (gha#927) --------------------------------------------------

MACROS = r"""\providecommand{\vecf}[1]{\tilde{#1}}
\def\vx{\vecf{x}}
\def\unused{u}
\def\vxy{\vecf{xy}}
\providecommand{\two}[2]{
  #1 + #2
}
\def\vx{\vecf{z}}
\def\~{\sim}
"""

MACRO_HOMEWORK = r"""---
title: "Homework 2"
---

{{< include /macros.qmd >}}

::: {#exr-m}
Find $\vx$ and $\two{a}{b}$, where $X \~ N$.
:::

::: {.sol}
It is $\vx$.
:::

```tex
\def\incode{c}
```
"""


@pytest.fixture
def macro_project(project):
    write(project / "macros.qmd", MACROS)
    write(project / "hw" / "hw1.qmd", MACRO_HOMEWORK)
    return project


def test_macro_def_name_forms():
    from student_qmd_macros import macro_def_name

    assert macro_def_name(r"\def\vx{x}") == "vx"
    assert macro_def_name(r"\let\foo\bar") == "foo"
    assert macro_def_name(r"\def\~{\sim}") == "~"
    assert macro_def_name(r"\newcommand*{\cmd}[1]{#1}") == "cmd"
    assert macro_def_name(r"\renewcommand{\cmd}{x}") == "cmd"
    assert macro_def_name(r"  \def\vx{x}") is None
    assert macro_def_name(r"Text \def\vx{x}") is None


def test_prune_keeps_used_and_transitive_macros_only(macro_project):
    assert generate("--prune-macros", "true") == 0
    text = student(macro_project).read_text()
    assert r"\providecommand{\vecf}" in text  # used only through \vx
    assert r"\def\vx{\vecf{x}}" in text
    assert r"\def\vx{\vecf{z}}" in text  # a redefinition stays: it wins
    assert r"\unused" not in text
    assert r"\vxy" not in text  # \vx does not reference \vxy
    assert "  #1 + #2\n}" in text  # a multi-line definition is kept whole
    assert r"\def\~{\sim}" in text
    assert r"\def\incode{c}" in text  # code is left alone


def test_prune_is_off_by_default(macro_project):
    assert generate() == 0
    assert r"\unused" in student(macro_project).read_text()


def test_prune_refuses_a_definition_that_never_closes(macro_project, capsys):
    write(macro_project / "macros.qmd", "\\def\\open{{x}\n\\def\\gone{g}\n")
    assert generate("--prune-macros", "true") == 1
    assert "definition of \\open do not close" in capsys.readouterr().out
    assert generate() == 0


def test_a_definition_stops_at_a_fence_rather_than_taking_text_in():
    # `:::}` would balance the braces, taking the callout and its text into
    # an unused definition that pruning then drops.
    lines = ["\\def\\weird{", "::: {.callout-note}", "Real text.", ":::}", "$\\vx$", "\\def\\vx{v}"]
    with pytest.raises(MacroError, match="weird"):
        prune_macros(lines)


def test_a_definition_stops_at_a_blank_line():
    with pytest.raises(MacroError, match="open"):
        macro_groups(["\\def\\open{", "", "Real text.}"])


def test_a_brace_in_a_tex_comment_is_not_counted():
    lines = ["\\newcommand{\\foo}{", "% a stray brace {", "  bar", "}", "\\def\\baz{used}"]
    assert macro_groups(lines) == [MacroDef("foo", 0, 4), MacroDef("baz", 4, 5)]


def test_escaped_characters_are_not_braces_or_comments():
    assert brace_depth("\\{ \\} \\% {") == 1
    assert brace_depth("a \\\\% {") == 0
    lines = ["\\def\\\\{", "  \\relax", "}", "\\def\\after{a}"]
    assert macro_groups(lines) == [MacroDef("\\", 0, 3), MacroDef("after", 3, 4)]


def test_prune_refuses_a_definition_inside_an_answer(macro_project, capsys):
    hw = MACRO_HOMEWORK.replace("It is $\\vx$.", "\\def\\key{42}\nIt is $\\vx$.")
    write(macro_project / "hw" / "hw1.qmd", hw)
    assert generate("--prune-macros", "true") == 1
    assert "macro definition inside an answer-key-only div" in capsys.readouterr().out
    assert generate() == 0


@needs_quarto
def test_check_passes_with_macros_pruned(macro_project, capsys):
    assert generate("--prune-macros", "true") == 0
    assert check("--prune-macros", "true") == 0
    assert "1 answer(s) removed" in capsys.readouterr().out


@needs_quarto
def test_check_fails_when_a_needed_macro_is_dropped(macro_project, capsys):
    assert generate("--prune-macros", "true") == 0
    path = student(macro_project)
    path.write_text(path.read_text().replace("\\providecommand{\\vecf}[1]{\\tilde{#1}}\n", ""))
    assert check("--prune-macros", "true") == 1
    assert "does not match" in capsys.readouterr().out


@needs_quarto
def test_check_fails_on_a_macro_the_source_lacks(macro_project, capsys):
    assert generate("--prune-macros", "true") == 0
    path = student(macro_project)
    path.write_text(path.read_text().replace("\\def\\~{\\sim}", "\\def\\~{\\sim}\n\\def\\key{42}"))
    assert check("--prune-macros", "true") == 1
    assert "macro definition its source does not have" in capsys.readouterr().out


@needs_quarto
def test_check_refuses_a_macro_inside_an_answer_in_source(macro_project, capsys):
    assert generate("--prune-macros", "true") == 0
    hw = MACRO_HOMEWORK.replace("It is $\\vx$.", "\\def\\key{42}\n\nIt is $\\vx$.")
    write(macro_project / "hw" / "hw1.qmd", hw)
    assert check("--prune-macros", "true") == 1
    assert "macro definition inside an answer-key-only div" in capsys.readouterr().out


@needs_quarto
def test_check_names_a_dropped_empty_block(project, capsys):
    # The empty refs div renders as no text at all, so the message has to
    # name it rather than print '' against '(nothing)'.
    write(project / "hw" / "hw1.qmd", HOMEWORK + "\n::: {#refs}\n:::\n")
    assert generate() == 0
    path = student(project)
    path.write_text(path.read_text().replace("::: {#refs}\n:::\n", ""))
    assert check() == 1
    assert "expected '(an empty Div #refs)', found '(nothing)'" in capsys.readouterr().out



def test_checker_keeps_and_flags_a_raw_block_whose_definition_never_closes():
    # Pandoc parses an unclosed definition as text, so no real source makes
    # this block; the checker still must not strip a guess out of one.
    block = {"t": "RawBlock", "c": ["tex", "\\def\\open{{x}\n\\def\\gone{g}"]}
    found: list[str] = []
    assert check_student_qmd.without_macro_defs(block, found) == block
    assert found and found[0].startswith("!") and "open" in found[0]
