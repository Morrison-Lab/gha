r"""Unit tests for check-literal-math-letters.

Covers the math tokenizer, the file parser (what is skipped and why), the
diff scoping (the check's core differentiator: flag what a diff adds, never
what was already there), the skip-not-fallback guard, and the defaults the
action, the reusable workflow and the script must agree on.

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_literal_math_letters", _DIR / "check-literal-math-letters.py"
)
assert _spec is not None and _spec.loader is not None
lml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lml)


def flagged(text: str):
    """{line number: tokens} for a document given as one string."""
    findings, _ = lml.scan_file(text.split("\n"))
    return {f.line: list(f.tokens) for f in findings}


# -- scan_math ---------------------------------------------------------------

def test_single_latin_letters_are_flagged():
    assert lml.scan_math("y_i = x_i + 2") == ["y", "i", "x", "i"]


def test_greek_commands_are_flagged():
    assert lml.scan_math(r"\theta + \varepsilon - \Gamma") == [
        r"\theta", r"\varepsilon", r"\Gamma"]


def test_literal_greek_character_is_flagged_as_its_command():
    assert lml.scan_math("\u03b8 + \u03a3") == [r"\theta", r"\Sigma"]


def test_command_names_are_not_letters():
    assert lml.scan_math(r"\frac{1}{2} \sum \left( \right)") == []


def test_text_like_arguments_are_skipped():
    assert lml.scan_math(r"\text{obs} + \mathrm{d} + \operatorname{Var}") == []


def test_operatorname_star_and_nested_braces_are_skipped():
    assert lml.scan_math(r"\operatorname*{argmax}_{} \text{a {b} c}") == []


def test_mathbb_argument_is_skipped():
    assert lml.scan_math(r"\mathbb{R}^2") == []


def test_mathcal_argument_is_a_letter():
    assert lml.scan_math(r"\mathcal{L}") == ["L"]


def test_run_of_two_letters_is_not_a_single_letter():
    assert lml.scan_math("df") == []


def test_labels_and_environments_are_skipped():
    assert lml.scan_math(r"\begin{aligned} \label{eq-a} \end{aligned}") == []


def test_array_column_spec_is_skipped():
    assert lml.scan_math(r"\begin{array}{cc} 1 & 2 \end{array}") == []


def test_escaped_symbols_and_spacing_commands_are_skipped():
    assert lml.scan_math(r"a \, b \\ c \{ \}") == ["a", "b", "c"]


def test_definition_span_is_skipped():
    assert lml.scan_math(r"\newcommand{\foo}[1]{x_#1}") == []
    assert lml.scan_math(r"\def\foo{y}") == []


# -- scan_file: what is skipped ----------------------------------------------

def test_inline_and_display_math_are_scanned():
    doc = "Let $y$ be.\n\n$$\nx = 1\n$$\n"
    assert flagged(doc) == {1: ["y"], 4: ["x"]}


def test_single_line_display_math():
    assert flagged("$$z = 1$$") == {1: ["z"]}


def test_code_fence_is_skipped():
    doc = "```r\nx <- $y$\n```\n$z$\n"
    assert flagged(doc) == {4: ["z"]}


def test_tilde_fence_and_longer_fence_are_skipped():
    doc = "~~~\n$a$\n~~~\n````\n```\n$b$\n```\n$c$\n````\n$d$\n"
    assert flagged(doc) == {10: ["d"]}


def test_inline_code_span_is_skipped():
    assert flagged("Write `$y$` and `` $x$ `` here, then $z$.") == {1: ["z"]}


def test_text_command_is_skipped_in_a_document():
    assert flagged(r"$\text{y}$ and $\operatorname{x}$") == {}


def test_notation_div_is_skipped():
    doc = "::: {.notation}\n$y$ is the outcome.\n:::\n$x$\n"
    assert flagged(doc) == {4: ["x"]}


def test_notation_div_bare_class_form_is_skipped():
    doc = "::: notation\n$y$\n:::\n$x$\n"
    assert flagged(doc) == {4: ["x"]}


def test_nested_div_inside_notation_is_still_skipped():
    doc = "::::: {.notation}\n::: {.callout-note}\n$y$\n:::\n$w$\n:::::\n$x$\n"
    assert flagged(doc) == {7: ["x"]}


def test_notation_nested_in_other_div_ends_with_it():
    doc = "::: {.callout-note}\n::: {.notation}\n$y$\n:::\n$w$\n:::\n$x$\n"
    assert flagged(doc) == {5: ["w"], 7: ["x"]}


def test_any_fence_line_closes_only_the_innermost_div():
    # Pandoc closes the innermost div on any fence line, whatever its length,
    # so the notation div stays open after the first closer.
    doc = ":::: {.notation}\n::: {.callout-note}\n$y$\n::::\n$w$\n::::\n$x$\n"
    assert flagged(doc) == {7: ["x"]}


def test_other_div_is_scanned():
    assert flagged("::: {.callout-note}\n$y$\n:::\n") == {2: ["y"]}


def test_html_comment_is_skipped_single_and_multi_line():
    doc = "<!-- $y$ -->\n<!--\n$x$\n-->\n$z$\n"
    assert flagged(doc) == {5: ["z"]}


def test_front_matter_is_skipped():
    doc = "---\ntitle: $y$\n---\n$z$\n"
    assert flagged(doc) == {4: ["z"]}


def test_currency_is_not_math():
    assert flagged("It costs $5 and then $10 more.") == {}
    # A closing dollar sign followed by a digit closes nothing.
    assert flagged("Pay $5k-$10k per seat.") == {}


def test_escaped_dollar_is_not_math():
    assert flagged(r"Pay \$a and \$b today.") == {}


def test_math_in_a_blockquote_and_list_is_scanned():
    assert flagged("> see $y$\n- item $x$\n") == {1: ["y"], 2: ["x"]}


def test_align_environment_is_scanned_across_lines():
    doc = "\\begin{align}\ny &= 1 \\\\\nz &= 2\n\\end{align}\n$w$\n"
    assert flagged(doc) == {2: ["y"], 3: ["z"], 5: ["w"]}


def test_blank_line_ends_an_unclosed_display_block():
    doc = "$$\nx\n\nThen a $y$.\n"
    assert flagged(doc) == {2: ["x"], 4: ["y"]}


def test_multi_line_display_flags_the_line_with_the_letter():
    doc = "$$\n\\frac{1}{n}\n\\sum_i\n$$\n"
    assert flagged(doc) == {2: ["n"], 3: ["i"]}


def test_macro_definition_display_is_skipped():
    assert flagged("$$\\newcommand{\\foo}{y}$$") == {}


def test_allow_directive_covers_its_line_and_the_next():
    doc = "<!-- check-literal-math-letters: allow -->\n$y$\n$x$\n"
    assert flagged(doc) == {3: ["x"]}


def test_ignore_file_directive():
    doc = "<!-- check-literal-math-letters: ignore-file -->\n$y$\n"
    assert flagged(doc) == {}


def test_spans_scanned_are_counted():
    _, spans = lml.scan_file(["$a$ and $b$", "$$c$$"])
    assert spans == 3


# -- messages ------------------------------------------------------------------

def test_message_suggests_the_semantic_macro():
    message = lml.format_message(("y", r"\theta", "k"))
    assert r"y -> \outvar" in message
    assert r"\theta -> \param" in message
    assert "k" in message and "k ->" not in message
    assert ".notation" in message


def test_message_deduplicates_and_caps():
    message = lml.format_message(tuple("abcdefghijkl") + ("a",))
    assert message.count("a;") + message.count("a.") == 1
    assert "and 4 more" in message


# -- diff scoping, in throwaway git repos --------------------------------------

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")  # phi-allow
    _git(tmp_path, "config", "user.name", "Test")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _run(base_ref="main", globs=None, ignore=None, whole_tree=False):
    return lml.run_check(
        base_ref, globs or ["*.qmd"], lml.compile_ignores(ignore or []), whole_tree
    )


def _lines(report):
    return sorted((p, f.line) for p, f in report.findings)


def test_added_line_is_flagged_and_existing_line_is_not(repo):
    (repo / "a.qmd").write_text("Old line with $y$.\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "a.qmd").write_text("Old line with $y$.\nNew line with $x$.\n")
    _commit(repo, "topic")
    report = _run()
    assert _lines(report) == [("a.qmd", 2)]
    assert not report.skipped


def test_untouched_file_with_letters_is_not_flagged(repo):
    (repo / "old.qmd").write_text("$y$\n")
    (repo / "new.qmd").write_text("plain\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "new.qmd").write_text("plain\nmore plain\n")
    _commit(repo, "topic")
    report = _run()
    assert report.findings == []
    assert report.files == 1


def test_clean_added_line_is_examined_but_not_flagged(repo):
    (repo / "a.qmd").write_text("x\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "a.qmd").write_text("x\nUse $\\outvar$ here.\n")
    _commit(repo, "topic")
    report = _run()
    assert report.findings == []
    assert (report.files, report.lines, report.spans) == (1, 1, 1)


def test_letter_on_unchanged_display_line_with_changed_neighbour_is_not_flagged(repo):
    (repo / "a.qmd").write_text("$$\nx = 1\n$$\nprose\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "a.qmd").write_text("$$\nx = 1\n$$\nprose changed\n")
    _commit(repo, "topic")
    assert _run().findings == []


def test_display_block_opened_earlier_still_flags_an_added_line_inside_it(repo):
    (repo / "a.qmd").write_text("$$\n1 + 1\n$$\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "a.qmd").write_text("$$\n1 + 1\nz = 2\n$$\n")
    _commit(repo, "topic")
    assert _lines(_run()) == [("a.qmd", 3)]


def test_moved_line_is_not_flagged(repo):
    (repo / "a.qmd").write_text("a1\nMoved $y$ line.\nc3\nd4\ne5\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "a.qmd").write_text("a1\nc3\nd4\nMoved $y$ line.\ne5\n")
    _commit(repo, "topic")
    assert _run().findings == []


def test_uncommitted_edit_is_examined(repo):
    (repo / "a.qmd").write_text("plain\n")
    _commit(repo, "base")
    (repo / "a.qmd").write_text("plain\nstaged $y$\n")
    _git(repo, "add", "a.qmd")
    assert _lines(_run(base_ref="HEAD")) == [("a.qmd", 2)]


def test_added_line_starting_with_plus_signs_is_not_a_file_header(repo):
    (repo / "a.qmd").write_text("plain\n")
    _commit(repo, "base")
    _git(repo, "checkout", "-q", "-b", "topic")
    (repo / "a.qmd").write_text("plain\n++ $y$\n")
    _commit(repo, "topic")
    assert _lines(_run()) == [("a.qmd", 2)]


@pytest.mark.parametrize("base_ref", ["", "no-such-ref"])
def test_empty_or_unresolvable_base_ref_skips(repo, base_ref):
    (repo / "a.qmd").write_text("$y$\n")
    _commit(repo, "base")
    report = _run(base_ref=base_ref)
    assert report.skipped
    assert report.findings == []


def test_skip_without_base_prints_a_plain_line_and_exits_zero(repo, monkeypatch, capsys):
    (repo / "a.qmd").write_text("$y$\n")
    _commit(repo, "base")
    monkeypatch.setenv("LML_BASE_REF", "")
    monkeypatch.setenv("LML_FAIL", "true")
    assert lml.main() == 0
    out = capsys.readouterr().out
    assert "Skipping" in out
    assert "::warning::" not in out
    assert "No literal letters" not in out


def test_skip_on_unresolvable_base_prints_a_warning(repo, monkeypatch, capsys):
    (repo / "a.qmd").write_text("$y$\n")
    _commit(repo, "base")
    monkeypatch.setenv("LML_BASE_REF", "no-such-ref")
    assert lml.main() == 0
    assert "::warning::Skipping" in capsys.readouterr().out


def test_whole_tree_flags_existing_letters(repo):
    (repo / "a.qmd").write_text("$y$\n")
    (repo / "b.qmd").write_text("clean\n")
    _commit(repo, "base")
    report = _run(base_ref="", whole_tree=True)
    assert _lines(report) == [("a.qmd", 1)]
    assert not report.skipped
    assert report.files == 2


def test_paths_ignore_and_globs_narrow_the_scan(repo):
    (repo / "keep.qmd").write_text("$y$\n")
    (repo / "vendor").mkdir()
    (repo / "vendor" / "skip.qmd").write_text("$y$\n")
    (repo / "other.md").write_text("$y$\n")
    _commit(repo, "base")
    report = _run(base_ref="", whole_tree=True, ignore=["vendor"])
    assert _lines(report) == [("keep.qmd", 1)]


def test_main_warns_by_default_and_fails_on_request(repo, monkeypatch, capsys):
    (repo / "a.qmd").write_text("$y$\n")
    _commit(repo, "base")
    monkeypatch.setenv("LML_WHOLE_TREE", "true")
    monkeypatch.setenv("LML_GLOBS", "*.qmd")
    assert lml.main() == 0
    out = capsys.readouterr().out
    assert "::warning file=a.qmd,line=1::" in out
    assert r"y -> \outvar" in out
    assert "Examined 1 line(s) across 1 file(s), 1 math span(s)" in out
    monkeypatch.setenv("LML_FAIL", "true")
    assert lml.main() == 1
    assert "::error file=a.qmd,line=1::" in capsys.readouterr().out


# -- defaults declared in three places must agree --------------------------------

def _yaml_default(path: Path, key: str):
    """Value of the ``default:`` under input ``key``, by a line scan (no YAML lib)."""
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^\s+{re.escape(key)}:\s*$", line):
            indent = len(line) - len(line.lstrip())
            for follow in lines[i + 1:]:
                if follow.strip() and len(follow) - len(follow.lstrip()) <= indent:
                    break
                m = re.match(r"^\s+default:\s*(.+?)\s*$", follow)
                if m:
                    return m.group(1).strip("'\"")
    raise AssertionError(f"no default found for {key} in {path}")


_ACTION = _DIR / "action.yml"
_WORKFLOW = _DIR.parent / ".github" / "workflows" / "check-literal-math-letters.yml"


@pytest.mark.parametrize("path", [_ACTION, _WORKFLOW])
def test_globs_default_agrees_with_the_script(path):
    assert _yaml_default(path, "globs") == lml.DEFAULT_GLOBS


@pytest.mark.parametrize("path", [_ACTION, _WORKFLOW])
def test_fail_default_agrees_with_the_script(path):
    assert _yaml_default(path, "fail") == str(lml._DEFAULT_FAIL).lower()


def test_quoted_ignore_file_directive_exempts_nothing():
    doc = "Quote: `<!-- check-literal-math-letters: ignore-file -->`\n$y$\n"
    assert flagged(doc) != {}


def test_directive_inside_fence_is_not_obeyed():
    doc = "```\n<!-- check-literal-math-letters: ignore-file -->\n```\n$y$\n"
    assert flagged(doc) != {}


def test_notation_word_in_quoted_attribute_is_not_a_notation_div():
    doc = '::: {.remark title="the notation of regression"}\n$y$\n:::\n'
    assert flagged(doc) != {}


def test_fence_indented_in_list_and_blockquote_is_skipped():
    assert flagged("- item\n\n    ```r\n    a$b + c$d\n    ```\n") == {}
    assert flagged("> ```r\n> a$b + c$d\n> ```\n") == {}


def test_blank_line_ends_unclosed_environment():
    doc = "\\begin{align}\na\n\nProse with a b c.\n"
    assert 4 not in flagged(doc)


def test_environment_end_is_an_exact_match():
    doc = "\\begin{align} \\begin{aligned} 1 \\end{aligned} b \\end{align}\n"
    assert 1 in flagged(doc)


def test_variant_greek_characters_are_flagged():
    for ch in "\u03d5\u03f5\u03d1\u03c2":
        assert flagged("$" + ch + "$\n") != {}


# -- precise mode and deprecated aliases (gha#1159) --------------------------

@pytest.fixture
def known_mode(monkeypatch):
    monkeypatch.setattr(lml, "KNOWN_ONLY", True)


def test_precise_mode_flags_only_letters_that_have_a_macro(known_mode):
    assert lml.scan_math("y_i + k_j + x_p") == ["y", "x"]


def test_precise_mode_flags_the_named_greek_commands_only(known_mode):
    assert lml.scan_math(r"\theta + \alpha + \varepsilon + \Gamma") == [
        r"\theta", r"\varepsilon"]


def test_precise_mode_flags_a_literal_greek_character_with_a_macro(known_mode):
    assert lml.scan_math("\u03b8 + \u03b1") == [r"\theta"]


def test_default_mode_still_flags_every_letter():
    assert lml.scan_math("y_i + k_j") == ["y", "i", "k", "j"]


def test_raw_euler_number_is_flagged_with_the_macro_to_use(known_mode):
    assert lml.scan_math(r"e^{-x}") == ["e", "x"]
    assert r"\euler" in lml.format_message(("e",))


def test_deprecated_macro_is_flagged_in_either_mode(monkeypatch):
    monkeypatch.setitem(lml.DEPRECATED, "truemeanfn", r"\truemean")
    assert lml.scan_math(r"\truemeanfn + \truemean") == [r"\truemeanfn"]
    monkeypatch.setattr(lml, "KNOWN_ONLY", True)
    assert lml.scan_math(r"\truemeanfn + \truemean") == [r"\truemeanfn"]


def test_deprecated_macro_message_names_the_replacement(monkeypatch):
    monkeypatch.setitem(lml.DEPRECATED, "truemeanfn", r"\truemean")
    assert "deprecated -> \\truemean" in lml.format_message((r"\truemeanfn",))


def test_load_deprecated_reads_the_use_instruction(tmp_path):
    tsv = tmp_path / "interpretations.tsv"
    tsv.write_text(
        "\\truemeanfn\ttrue mean function; deprecated, use \\truemean\n"
        "\\truemean\ttrue mean function; replaces the deprecated \\truemeanfn\n"
        "\\other\tplain description\n"
    )
    assert lml.load_deprecated(str(tsv)) == {"truemeanfn": r"\truemean"}


def test_load_deprecated_missing_file_yields_no_rules(tmp_path, capsys):
    assert lml.load_deprecated(str(tmp_path / "absent.tsv")) == {}
    assert "Could not read" in capsys.readouterr().out


def test_cross_mark_counter_example_is_skipped_but_check_mark_line_is_flagged():
    doc = "> ❌ Let $x$ be the input.\n>\n> ✅ Let $x$ be the input.\n"
    assert flagged(doc) == {3: ["x"]}


def test_cross_mark_paragraph_continues_over_quote_lines_until_a_check_mark():
    doc = "> ❌ Let $x$ be\n> the input, $y$.\n> ✅ Let $w$ be it.\n"
    assert flagged(doc) == {3: ["w"]}


def test_cross_mark_skip_ends_at_a_blank_line_and_a_non_quote_line():
    doc = "> ❌ $x$\n\n$y$\n\n> ❌ $x$\nafter $z$\n"
    assert flagged(doc) == {3: ["y"], 6: ["z"]}


def test_quote_without_a_cross_mark_is_still_checked():
    assert flagged("> Let $x$ be the input.\n") == {1: ["x"]}


def test_empty_quote_line_ends_the_cross_mark_paragraph():
    # no check mark follows, so only the empty `>` can reset the skip
    assert flagged("> ❌ $x$\n>\n> $y$\n") == {3: ["y"]}


def test_nested_quote_cross_mark_is_skipped_and_nested_blank_ends_it():
    assert flagged("> > ❌ $x$\n> >\n> > $y$\n") == {3: ["y"]}


def test_cross_mark_in_the_middle_of_a_paragraph_does_not_start_a_skip():
    assert flagged("> Consider:\n> ❌ $x$\n") == {2: ["x"]}


def test_cross_mark_after_a_check_mark_line_starts_a_skip():
    assert flagged("> ✅ $x$\n> ❌ $y$\n") == {1: ["x"]}


# -- the log-odds symbol -----------------------------------------------------

def test_z_for_the_log_odds_is_flagged_in_precise_mode(known_mode):
    got = flagged("If the log-odds of an event are $z$, its probability is p.")
    assert got == {1: ["z[log-odds]"]}


def test_f_for_the_log_odds_is_flagged_in_precise_mode(known_mode):
    got = flagged("It passes through one half at $F = 0$ on the log-odds axis.")
    assert got == {1: ["F[log-odds]"]}


def test_z_without_log_odds_context_passes_in_precise_mode(known_mode):
    assert flagged("The Wald statistic is $z = b / s$.") == {}


def test_logodds_macro_is_not_flagged_in_precise_mode(known_mode):
    assert flagged(r"The log-odds are $\logodds = 0$.") == {}


def test_log_odds_message_names_the_macro(known_mode):
    msg = lml.format_message(("z[log-odds]",))
    assert r"\logodds" in msg


@pytest.mark.parametrize("text", [
    "The Wald $z$ for the logit slope.",
    "The logit is $F^{-1}(p)$ and the quantile is $z_{\\alpha/2}$.",
    "The log-odds $\\mathrm{F}$ and $\\text{F-test}$ differ.",
    "Let $a_z$ be the log-odds.",
    r"The score is $\logodds$ and the other value is $z_i$.",
    "The logits are $z_i$ and $z1$.",
    "The log-odds follow $F(t)$.",
    "The log odds are $\\zeta$.",
])
def test_log_odds_rule_leaves_correct_notation_alone(known_mode, text):
    assert flagged(text) == {}


def test_log_odds_rule_covers_logit_and_plurals(known_mode):
    assert flagged("The logits are $z$.") == {1: ["z[log-odds]"]}
    assert flagged("The log odds are $F$.") == {1: ["F[log-odds]"]}


def test_log_odds_macro_alone_is_not_context(known_mode):
    assert flagged(r"The score is $\logodds$ and $z = 2$.") == {}


def test_log_odds_rule_runs_in_default_mode_without_double_reporting():
    assert flagged("The log-odds are $z$.") == {1: ["z[log-odds]"]}


def test_log_odds_message_hides_the_internal_tag():
    assert "[log-odds]" not in lml.format_message(("F[log-odds]",))
