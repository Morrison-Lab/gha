"""Unit tests for check-informal-definitions.

Tests cover:
- Detection of bolded terms followed by defining language outside def divs
- Detection of \\eqdef and \\triangleq outside def divs
- Detection of naming sentences before display math
- Detection of prose paragraphs under '### Definitions' headings
- Exemption of concepts defined inside formal ::: {#def-...} divs
- Exemption of notation sections (### Notation, ### Typographic Conventions)
- Exemption of labels and metadata (**Note:**, **Figure 1:**)
- Line-level and file-level opt-out directives
- Exclusion of code blocks, HTML comments, tables, and frontmatter
- Diff-scoping behavior and report outputs
"""

import importlib.util
import json
from pathlib import Path
import pytest

_DIR = Path(__file__).resolve().parent.parent
_MOD_PATH = _DIR / "check-informal-definitions.py"
_spec = importlib.util.spec_from_file_location("check_informal_definitions", _MOD_PATH)
assert _spec is not None and _spec.loader is not None, f"Could not load {_MOD_PATH}"
check_defs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_defs)

Finding = check_defs.Finding
scan_file_lines = check_defs.scan_file_lines


def test_bold_prose_definition_flagged():
    content = [
        "## Introduction",
        "",
        "**Random** is a property of a variable whose value is uncertain.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 1
    assert findings[0].rule == "bold-prose-definition"
    assert findings[0].term == "Random"
    assert findings[0].line == 3


def test_article_prefixed_bold_prose_definition_flagged():
    content = [
        "## Stochastic Processes",
        "",
        "A **stochastic process** is a collection of random variables indexed by time.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 1
    assert findings[0].rule == "bold-prose-definition"
    assert findings[0].term == "stochastic process"
    assert findings[0].line == 3


def test_probabilistic_refers_to_flagged():
    content = [
        "## Models",
        "",
        "**Probabilistic** refers to models based on axiomatic probability theory.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 1
    assert findings[0].rule == "bold-prose-definition"
    assert findings[0].term == "Probabilistic"


def test_bold_colon_definition_flagged():
    content = [
        "## Variables",
        "",
        "We call it a **Random variable**: a measurable function from sample space to real numbers.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 1
    assert findings[0].rule == "bold-colon-definition"
    assert findings[0].term == "Random variable"


def test_eqdef_outside_div_flagged():
    content = [
        "## Derivation",
        "",
        "Here we define $X_t \\eqdef f(X_{t-1}, \\epsilon_t)$ directly in text.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 1
    assert findings[0].rule == "eqdef-outside-div"
    assert findings[0].line == 3


def test_definitions_section_prose_flagged():
    content = [
        "### Definitions",
        "",
        "**State space** denotes the set of all possible values.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) >= 1
    assert any(f.rule == "definitions-section-prose" or f.rule == "bold-prose-definition" for f in findings)


def test_naming_sentence_before_display_math_flagged():
    content = [
        "## Variance",
        "",
        "The **variance** of a discrete random variable is:",
        "$$",
        "\\mathrm{Var}(X) = \\sum (x - \\mu)^2 p(x)",
        "$$",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 1
    assert findings[0].rule == "naming-sentence-display-math"
    assert findings[0].line == 3


def test_concept_inside_formal_def_div_is_clean():
    content = [
        "## Chapter 1",
        "",
        "::: {#def-random-variable}",
        "A **random variable** is a measurable function from sample space to real numbers.",
        "$$",
        "X: \\Omega \\to \\mathbb{R}",
        "$$",
        "where $X \\eqdef \\omega \\mapsto x$.",
        ":::",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_concept_inside_theorem_div_is_clean():
    content = [
        "::: {#thm-central-limit}",
        "The **sample mean** is asymptotically normally distributed.",
        ":::",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_notation_section_is_exempt():
    content = [
        "### Notation",
        "",
        "**Bold letters** denote vectors, while **italic letters** denote scalars.",
        "**$X$** is a matrix.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_common_labels_are_not_flagged():
    content = [
        "**Note:** This is an important distinction to keep in mind.",
        "**Warning:** Do not run this command as root.",
        "**Tip:** You can use shortcut keys for navigation.",
        "**Figure 1:** This is the architecture diagram.",
        "**Table 2:** Parameter values used in the simulation.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_line_level_opt_out():
    content = [
        "**Random** is used here colloquially. <!-- check-informal-definitions: allow -->",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_file_level_opt_out():
    content = [
        "<!-- check-informal-definitions: ignore-file -->",
        "",
        "**Random** is undefined formally in this scratchpad.",
        "**Stochastic** refers to randomness.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_code_fences_and_comments_ignored():
    content = [
        "```python",
        "# **Random** is a python comment",
        "x = '\\eqdef'",
        "```",
        "",
        "<!--",
        "**Stochastic** is an HTML comment",
        "-->",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_frontmatter_ignored():
    content = [
        "---",
        "title: \"**Random** is in title\"",
        "---",
        "",
        "Normal body text.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert len(findings) == 0


def test_diff_scoping_selects_only_added_lines():
    content = [
        "Line 1",
        "**Random** is defined on pre-existing line 2.",
        "Line 3",
        "**Stochastic process** is added on line 4.",
    ]
    # Only line 4 is in the diff
    findings = scan_file_lines(Path("test.qmd"), content, added_lines={4})
    assert len(findings) == 1
    assert findings[0].line == 4
    assert findings[0].term == "Stochastic process"


def test_cli_clean_file_exits_zero(tmp_path, monkeypatch):
    clean_file = tmp_path / "clean.qmd"
    clean_file.write_text(
        "::: {#def-variance}\nThe **variance** is a [measure](m.qmd#def-measure) of dispersion.\n:::\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["check-informal-definitions.py", "--path", str(clean_file), "--fail=true"],
    )
    assert check_defs.main() == 0


def test_cli_failing_file_exits_one_and_writes_reports(tmp_path, monkeypatch):
    dirty_file = tmp_path / "dirty.qmd"
    dirty_file.write_text(
        "## Section\n**Random** is undefined formally.\n",
        encoding="utf-8",
    )
    md_out = tmp_path / "report.md"
    json_out = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "check-informal-definitions.py",
            "--path",
            str(dirty_file),
            "--fail=true",
            "--output-markdown",
            str(md_out),
            "--output-json",
            str(json_out),
        ],
    )
    assert check_defs.main() == 1
    assert md_out.exists()
    assert "**Random**" in md_out.read_text(encoding="utf-8")
    assert json_out.exists()
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["total_findings"] == 1
    assert len(data["findings"]) == 1
    assert data["findings"][0]["term"] == "Random"


def test_cli_clean_file_writes_reports(tmp_path, monkeypatch):
    clean_file = tmp_path / "clean.qmd"
    clean_file.write_text(
        "::: {#def-random}\n## Random\nDefinition [content](c.qmd#def-content)\n:::\n",
        encoding="utf-8",
    )
    md_out = tmp_path / "report.md"
    json_out = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "check-informal-definitions.py",
            "--path",
            str(clean_file),
            "--fail=true",
            "--output-markdown",
            str(md_out),
            "--output-json",
            str(json_out),
        ],
    )
    assert check_defs.main() == 0
    assert md_out.exists()
    assert "Clean. No informal definitions found." in md_out.read_text(encoding="utf-8")
    assert json_out.exists()
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["total_findings"] == 0
    assert len(data["findings"]) == 0


def test_cli_failing_file_with_fail_false_exits_zero(tmp_path, monkeypatch):
    dirty_file = tmp_path / "dirty.qmd"
    dirty_file.write_text(
        "## Section\n**Random** is undefined formally.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["check-informal-definitions.py", "--path", str(dirty_file), "--fail=false"],
    )
    assert check_defs.main() == 0


def test_four_colon_fence_and_nesting_is_clean():
    content = """
:::: {#def-outer}
A formal outer definition.

::: {#thm-inner}
An inner theorem.
:::

The **estimator** is a formal statistic.
::::
"""
    findings = scan_file_lines(Path("test.qmd"), content.splitlines())
    assert len(findings) == 0


def test_bold_term_with_intervening_math_symbol_is_flagged():
    content = """
# Probability Theory

A **random variable** $X$ is a measurable function from sample space to reals.

The **estimator** $\\hat{\\theta}$ is defined as the sample mean.

**Confidence interval** (\\alpha, \\beta): a random interval containing the parameter.
"""
    findings = scan_file_lines(Path("test.qmd"), content.splitlines())
    terms = [f.term for f in findings]
    assert "random variable" in terms
    assert "estimator" in terms
    assert "Confidence interval" in terms


def test_inline_code_spans_with_eqdef_or_defining_language_not_flagged():
    # Finding 2 reproduction: documentation referencing `\eqdef` or `is defined as` in backticks
    content = """
# Reference Doc

The check flags:
- `\\eqdef` or `\\triangleq` used in inline or display math outside a def div.
- A bold term followed by `is defined as` outside a def div.
"""
    findings = scan_file_lines(Path("ref.qmd"), content.splitlines())
    assert len(findings) == 0


def test_unequal_backtick_runs_open_no_code_span():
    # A run closes a span only on a run of the same length (gha#1856), so
    # this line holds no span and its definition is prose.
    content = """
# Methods

A ` **widget** is defined as a small gadget ``.
"""
    findings = scan_file_lines(Path("ref.qmd"), content.splitlines())
    assert len(findings) == 1


def test_nested_subsection_under_notation_remains_exempt():
    # Finding 6 reproduction: subsection under Notation remains exempt
    content = """
### Notation

#### Vectors and Matrices

We let **v** denote a column vector.
**M** is a symmetric matrix.

### Methods

A **stochastic process** is a collection of random variables.
"""
    findings = scan_file_lines(Path("test.qmd"), content.splitlines())
    assert len(findings) == 1
    assert findings[0].term == "stochastic process"


def test_nested_subsection_under_definitions_remains_in_definitions_scope():
    content = """
### Definitions

#### Basic Terms

**State space** of the Markov chain.

### Next Section

**State space** of the Markov chain.
"""
    findings = scan_file_lines(Path("test.qmd"), content.splitlines())
    # The one under Definitions/Basic Terms is flagged by definitions-section-prose;
    # the one under Next Section is not under definitions section and has no defining verb
    assert len(findings) == 1
    assert findings[0].rule == "definitions-section-prose"


def test_non_definition_question_with_is_this_not_flagged():
    content = """
- **Strategic correctness.** Is this the right algorithm or design for the problem?
- **Performance.** Is there any memory leak?
"""
    findings = scan_file_lines(Path("test.qmd"), content.splitlines())
    assert len(findings) == 0


def test_compile_ignores_and_matching():
    # Finding 7 reproduction: anchored ignore matching
    ignores = check_defs.diffscope.compile_ignores(["tests", "vendor/**", "_site"])
    assert check_defs.diffscope.ignored("tests/foo.qmd", ignores)
    assert check_defs.diffscope.ignored("vendor/lib/doc.qmd", ignores)
    assert check_defs.diffscope.ignored("_site/index.qmd", ignores)
    assert not check_defs.diffscope.ignored("content/test-page.qmd", ignores)
    assert not check_defs.diffscope.ignored("scratch-notes.qmd", ignores)


# gha#1482: shapes that are not informal definitions.
@pytest.mark.parametrize("content", [
    # A bold label opening a line or list item.
    ["**Improvement**: The citation is to a current survey."],
    ["- **A shared axis**: the panels must line up on one scale."],
    # A local abbreviation inside an argument.
    ["Let $S_n \\eqdef \\sum_i X_i$ be the partial sum."],
    # Notation, not a definition.
    ["**Expectation** is denoted $\\E{X}$ here."],
    # "X is:" before display math with no naming cue computes a value.
    ["The inner derivative is:", "$$", "f'(x) = 2x", "$$"],
])
def test_gha1482_non_definitions_pass(content):
    assert scan_file_lines(Path("test.qmd"), ["## S", ""] + content) == []


def test_eqdef_inside_proof_div_passes():
    content = ["::: {.proof}", "Then $m \\eqdef 2$ and so on.", ":::"]
    assert scan_file_lines(Path("test.qmd"), content) == []


def test_eqdef_outside_proof_still_flagged():
    content = ["## S", "", "The rate $m \\eqdef 2$ is fixed."]
    assert [f.rule for f in scan_file_lines(Path("test.qmd"), content)] == ["eqdef-outside-div"]


def test_bare_class_proof_div_is_tracked():
    # "::: proof" (no braces) nested in a theorem opens a div, so its closer
    # ends the proof and leaves the theorem open for the line after it.
    content = [
        "::: {#thm-a}", "Statement.", "",
        "::: proof", "Then $k \\eqdef 2$.", ":::", "",
        "Hence $j \\eqdef 3$ in the statement.", ":::", "",
        "## After", "", "The rate $m \\eqdef 2$ is fixed.",
    ]
    findings = scan_file_lines(Path("test.qmd"), content)
    assert [(f.rule, f.line) for f in findings] == [("eqdef-outside-div", 13)]


def test_leading_bold_label_is_not_a_naming_cue():
    content = ["**Note**: the inner derivative is:", "", "$$", "f'(x) = 2x", "$$"]
    assert scan_file_lines(Path("test.qmd"), content) == []


def test_bold_term_after_a_leading_label_is_still_a_naming_cue():
    content = ["**Note**: the **variance** is:", "", "$$", "V = 1", "$$"]
    rules = [f.rule for f in scan_file_lines(Path("test.qmd"), content)]
    assert rules == ["naming-sentence-display-math"]
