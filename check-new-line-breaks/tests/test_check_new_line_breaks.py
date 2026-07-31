"""Unit tests for check-new-line-breaks.

Covers the pure sentence-splitting/block-detection logic directly, plus the
diff-scoping behavior (the check's core differentiator: it must flag lines a
diff adds, and must NOT reflag pre-existing drift in an untouched line) via
small throwaway git repos.

check-new-line-breaks.py isn't an importable module name (the hyphen), so
load it by path -- same pattern as check-phi/tests/test_detectors.py.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_MOD_PATH = Path(__file__).resolve().parent.parent / "check-new-line-breaks.py"
_spec = importlib.util.spec_from_file_location("check_new_line_breaks", _MOD_PATH)
assert _spec is not None and _spec.loader is not None, f"Could not load {_MOD_PATH}"
nlb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nlb)


# ── split_sentences ──────────────────────────────────────────────────────────

def test_splits_two_plain_sentences():
    assert nlb.split_sentences("First one. Second one.") == ["First one.", "Second one."]


def test_single_sentence_is_not_split():
    assert nlb.split_sentences("Just one sentence here.") == ["Just one sentence here."]


def test_abbreviation_period_does_not_split():
    result = nlb.split_sentences("See e.g. the manual for details.")
    assert len(result) == 1


def test_period_inside_inline_code_does_not_split():
    result = nlb.split_sentences("Run `python3 -m pytest .` to test it.")
    assert len(result) == 1


# ── prose_line_numbers ───────────────────────────────────────────────────────

def test_frontmatter_and_heading_excluded():
    text = "---\ntitle: x\n---\n# Heading\nPara line.\n"
    assert nlb.prose_line_numbers(text) == {5}


def test_fenced_code_excluded():
    text = "Intro line.\n```\ncode with a period. not prose.\n```\nOutro line.\n"
    assert nlb.prose_line_numbers(text) == {1, 5}


def test_table_and_hr_excluded():
    text = "| a | b. two sentences. |\n| - | - |\n---\nParagraph text.\n"
    assert nlb.prose_line_numbers(text) == {4}


def test_multiline_html_comment_excluded():
    text = (
        "<!--\n"
        "Interior comment line. Two sentences here.\n"
        "-->\n"
        "Real prose line.\n"
    )
    assert nlb.prose_line_numbers(text) == {4}


def test_single_line_html_comment_excluded():
    text = "<!-- one-line comment -->\nReal prose line.\n"
    assert nlb.prose_line_numbers(text) == {2}


def test_blockquote_prose_is_checked():
    text = "> First sentence. Second sentence.\n"
    assert nlb.prose_line_numbers(text) == {1}


def test_blockquote_bullet_and_blank_excluded():
    text = "> - a bullet\n>\n> prose line\n"
    assert nlb.prose_line_numbers(text) == {3}


def test_blockquote_nested_fence_excluded():
    text = "> ```\n> code with a period. not prose.\n> ```\n> prose line\n"
    assert nlb.prose_line_numbers(text) == {4}


# ── line_content ─────────────────────────────────────────────────────────────

def test_bullet_marker_is_stripped():
    assert nlb.line_content("- some text here") == "some text here"


def test_blockquote_prefix_is_stripped():
    assert nlb.line_content("> some text here") == "some text here"


def test_plain_line_is_returned_stripped():
    assert nlb.line_content("  plain text  ") == "plain text"


# ── diff-scoping (find_violations), against small throwaway git repos ───────

def _init_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(tmp_path: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=tmp_path, check=True)


def _find(tmp_path: Path, base_ref: str = "", globs=("*.md",)):
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return nlb.find_violations(base_ref, list(globs), [])
    finally:
        os.chdir(cwd)


def test_diff_scope_flags_newly_added_violation(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short bullet.\n- Two sentences. On one line.\n"
    )
    _commit(tmp_path, "add violation")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("notes.md", 4)]
    assert [v.reason for v in violations] == ["sentence"]


def test_diff_scope_does_not_reflag_pre_existing_drift(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("- Fine as-is. Two sentences here.\n")
    _commit(tmp_path, "base with pre-existing drift")
    (tmp_path / "notes.md").write_text(
        "- Fine as-is. Two sentences here.\n- A brand-new short bullet.\n"
    )
    _commit(tmp_path, "unrelated addition")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert violations == []


def test_unresolvable_base_ref_skips_rather_than_scanning_whole_tree(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("- Long-standing violation. Two sentences.\n")
    _commit(tmp_path, "only commit")

    violations, skipped = _find(tmp_path, base_ref="deadbeefdeadbeef")
    assert skipped
    assert violations == []


def test_empty_base_ref_skips_rather_than_scanning_whole_tree(tmp_path):
    # No base to diff against (e.g. a push run) must never fall back to a
    # whole-tree scan -- that would defeat the entire point of diff-scoping,
    # reflagging every pre-existing long line the corpus already carries.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("- A violation. Right here.\n")
    _commit(tmp_path, "only commit")

    violations, skipped = _find(tmp_path, base_ref="")
    assert skipped
    assert violations == []


# ── clause breaks (SemBr rule 5) ─────────────────────────────────────────────

# Long enough to clear the 80-char gate, with the semicolon mid-line.
_LONG_SEMICOLON = (
    "The first clause carries the main point of the sentence; "
    "the second one stands entirely on its own."
)


def test_strip_inline_markup_drops_code_spans_and_link_targets():
    assert nlb.strip_inline_markup("run `a; b` now") == "run  now"
    assert nlb.strip_inline_markup("see [docs](http://x.com/a;b)") == "see [docs]"


def test_long_line_with_midline_semicolon_is_a_clause_break():
    assert len(_LONG_SEMICOLON) > 80
    assert nlb.has_late_semicolon(_LONG_SEMICOLON)


def test_short_line_with_semicolon_is_not_flagged():
    # Same construction, under the length gate: a semicolon alone is not
    # enough, which is the whole point of gating on length.
    assert not nlb.has_late_semicolon("Do this; then that.")


def test_trailing_semicolon_is_not_a_clause_break():
    text = "A clause that is quite long indeed and already ends where it should;"
    assert not nlb.has_late_semicolon(text, min_length=10)


def test_semicolon_only_inside_code_span_is_not_a_clause_break():
    text = "Invoke the helper with `for x in xs; do thing; done` and read its output."
    assert not nlb.has_late_semicolon(text, min_length=10)


def test_semicolon_inside_a_multi_backtick_code_span_is_not_a_clause_break():
    # #337 review round 3: `[^`]*` matched the empty span formed by the two
    # opening backticks of a ``...``, so an N-backtick span -- CommonMark's
    # form for a span containing a backtick -- kept its contents, semicolons
    # and all. That is the exact construct the stripping exists to remove.
    text = (
        "Invoke the helper with ``for x in xs; do thing; done`` "
        "and then read all of its output carefully."
    )
    assert len(text) > 80
    assert ";" not in nlb.strip_inline_markup(text)
    assert not nlb.has_late_semicolon(text)


def test_a_backtick_inside_a_multi_backtick_span_does_not_end_it():
    assert nlb.strip_inline_markup("use ``a `b` c`` here") == "use  here"


@pytest.mark.parametrize(
    "label,text",
    [
        # #337 round 5: stripping deletes the construct but not the space
        # beside it, so a leading semicolon can land at index 1 and slip past
        # the find(";", 1) guard. Both shapes strip to a leading " ; ".
        ("space before the semicolon",
         "`configure` ; the remaining prose runs on for quite a while here and "
         "says rather a lot more besides, well past the gate"),
        ("two adjacent constructs",
         "`npm` `install`; the remaining prose runs on for quite a while here and "
         "says rather a lot more besides, well past the gate"),
    ],
)
def test_leading_semicolon_survives_whitespace_left_by_stripping(label, text):
    stripped = nlb.strip_inline_markup(text).strip()
    assert len(stripped) >= 80, (
        f"{label}: fixture must clear the length gate, else this passes "
        f"without ever reaching the leading-semicolon guard"
    )
    assert not nlb.has_late_semicolon(text), label


@pytest.mark.parametrize("raw", ["eighty", "8o", "80.5"])
def test_env_int_warns_on_a_non_numeric_value(raw, monkeypatch, capsys):
    # #337 round 5: only the negative branch warned, so a caller's typo fell
    # back silently -- the exact case this section's rationale names.
    monkeypatch.setenv("NLB_CLAUSE_MIN_LENGTH", raw)
    assert nlb._env_int("NLB_CLAUSE_MIN_LENGTH", 80) == 80
    assert "::warning" in capsys.readouterr().out


def test_env_int_stays_silent_when_unset(monkeypatch, capsys):
    monkeypatch.delenv("NLB_CLAUSE_MIN_LENGTH", raising=False)
    assert nlb._env_int("NLB_CLAUSE_MIN_LENGTH", 80) == 80
    assert capsys.readouterr().out == ""


def test_a_leading_semicolon_does_not_mask_a_later_interior_one():
    # Self-caught while reviewing the fix above: rejecting index 0 after a
    # plain find(';') threw away the whole line, so a leading semicolon hid a
    # genuine boundary further along. The search skips position 0 instead.
    text = (
        "`cfg`; a first clause that runs on for quite a while here; "
        "and a second one after it."
    )
    assert nlb.strip_inline_markup(text).lstrip().startswith(";")
    assert nlb.has_late_semicolon(text, min_length=10)


def test_leading_semicolon_is_not_a_clause_break():
    # A semicolon in the first position ends nothing, so there is no clause to
    # break after. Reachable once stripping removes what preceded it.
    text = "`configure`; " + "the remaining prose runs on for a while and is long indeed."
    assert nlb.strip_inline_markup(text).lstrip().startswith(";")
    assert not nlb.has_late_semicolon(text, min_length=10)


def test_long_line_without_semicolon_is_not_flagged():
    text = "A single long clause that simply runs on for a good while without any break."
    assert not nlb.has_late_semicolon(text, min_length=10)


def test_clause_min_length_is_configurable():
    text = "Short; line."
    assert not nlb.has_late_semicolon(text)
    assert nlb.has_late_semicolon(text, min_length=5)


def test_length_gate_measures_visible_prose_not_raw_markdown():
    # Regression (#337 review): the gate used to read len(text) while the
    # semicolon search read the stripped text, so a short line inflated past
    # the gate by a long link target was flagged. That also contradicts the
    # URL-inflation exception in ai-config's semantic-line-breaks guidance.
    text = "See [x](https://example.com/" + "a" * 90 + "); ok now."
    assert len(text) > 80, "raw line must clear the gate for this to test anything"
    assert len(nlb.strip_inline_markup(text)) < 80
    assert not nlb.has_late_semicolon(text)


def test_a_long_code_span_does_not_inflate_a_short_line_past_the_gate():
    text = "Run `" + "x" * 90 + "` first; then stop."
    assert len(text) > 80
    assert not nlb.has_late_semicolon(text)


@pytest.mark.parametrize(
    "label,text",
    [
        # #337 round 2: a bare URL has no `](` to anchor on, so it used to
        # bypass stripping entirely -- reintroducing the round-1 bug for
        # unbracketed links, and treating a `;` in a query string as a clause.
        ("bare URL with a semicolon in its query string",
         "Open https://example.com/search?a=1;b=2 in a browser for details, please, and read on"),
        ("bare URL inflating an otherwise short line",
         "See https://example.com/docs/some/quite/long/path/page.html; it explains the rest."),
        ("autolink",
         "See <https://example.com/docs/some/quite/long/path/page.html>; it explains the rest."),
        # An HTML entity also ends in `;`, and renders as a single glyph.
        ("HTML entity",
         "This sentence uses fish &amp; chips as an example of a common food pairing today"),
    ],
)
def test_markup_carrying_a_semicolon_is_not_a_clause_break(label, text):
    assert not nlb.has_late_semicolon(text), label


def test_clause_boundary_after_a_bare_url_survives_stripping():
    # #337 review round 3: `https?://\S+` ran to the next whitespace, so a `;`
    # sitting immediately after a URL was eaten along with it and a genuine
    # rule 5 break went unreported. Stripping must remove the URL and keep the
    # punctuation next to it.
    text = (
        "The full derivation is written up at https://example.com/paper.pdf; "
        "the second clause stands entirely on its own."
    )
    assert nlb.strip_inline_markup(text).rstrip() == (
        "The full derivation is written up at ; "
        "the second clause stands entirely on its own."
    )
    assert nlb.has_late_semicolon(text)


def test_identical_prose_does_not_flip_verdict_on_link_syntax():
    # The sharpest form of the round-2 finding: the same sentence, written two
    # ways, must get the same answer.
    bare = "Open https://example.com/search?a=1;b=2 in a browser for details, please, and read on"
    bracketed = (
        "Open [the search page](https://example.com/search?a=1;b=2) in a browser "
        "for details, please, and read on"
    )
    assert nlb.has_late_semicolon(bare) == nlb.has_late_semicolon(bracketed)


def test_min_length_is_inclusive():
    # #337 review, third finding: the input is named a *minimum*, so a line of
    # exactly that many visible characters is checked rather than skipped.
    text = "a" * 68 + "; " + "b" * 10
    assert len(text) == 80
    assert nlb.has_late_semicolon(text, min_length=80)
    assert not nlb.has_late_semicolon(text, min_length=81)


def test_sentence_reason_wins_over_clause_reason():
    # A line that breaks both rules is reported once, against rule 4.
    text = _LONG_SEMICOLON + " And a second sentence follows it."
    assert nlb.classify_line(text) == "sentence"


def test_clause_check_can_be_disabled():
    assert nlb.classify_line(_LONG_SEMICOLON) == "clause"
    assert nlb.classify_line(_LONG_SEMICOLON, clause_breaks=False) is None


def test_clause_break_is_on_by_default_in_diff_scope(tmp_path):
    # The opt-out half of #336: a newly-added clause-joined long line is
    # flagged without any caller opting in.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        f"# Notes\n\n- A short bullet.\n- {_LONG_SEMICOLON}\n"
    )
    _commit(tmp_path, "add clause-joined line")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line, v.reason) for v in violations] == [
        ("notes.md", 4, "clause")
    ]


# ── defaults declared in two places must agree ───────────────────────────────

# The script's fallbacks and action.yml's declared defaults are independent
# copies of the same two values, so a test pins them together rather than a
# comment asking the next editor to remember (the gha#303 precedent).

# Parsed with a regex rather than a YAML library on purpose: the selftest job
# installs only pytest, so importing yaml here would fail in CI.
_ACTION_YML = _MOD_PATH.parent / "action.yml"
_WORKFLOW_YML = (
    _MOD_PATH.parent.parent / ".github" / "workflows" / "check-new-line-breaks.yml"
)


def _declared_default(path: Path, input_name: str) -> str:
    """Read an input's declared `default:` out of a YAML file, textually.

    Scans forward from the input's own key to the first `default:` line,
    which is how both files are laid out.
    """
    lines = path.read_text().split("\n")
    starts = [i for i, line in enumerate(lines) if line.strip() == f"{input_name}:"]
    assert starts, f"input {input_name!r} not found in {path.name}"
    for line in lines[starts[0] + 1:]:
        stripped = line.strip()
        if stripped.startswith("default:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    raise AssertionError(f"no default declared for {input_name!r} in {path.name}")


@pytest.mark.parametrize("path", [_ACTION_YML, _WORKFLOW_YML])
def test_declared_clause_breaks_default_matches_script_default(path):
    assert (_declared_default(path, "clause-breaks") == "true") is (
        nlb._DEFAULT_CLAUSE_BREAKS
    )


@pytest.mark.parametrize("path", [_ACTION_YML, _WORKFLOW_YML])
def test_declared_clause_min_length_default_matches_script_default(path):
    assert int(_declared_default(path, "clause-min-length")) == (
        nlb._DEFAULT_CLAUSE_MIN_LENGTH
    )


# ── the env var -> main() -> exit code path ──────────────────────────────────

# #337 round 2: `_selftest.yml` calls the composite with `clause-breaks:
# 'false'`, but that step sets no `fail:`, and main() returns 0 on every path
# unless NLB_FAIL is true -- so it stays green whether the input reaches the
# script, is dropped, or was never declared. These two cases are what actually
# prove the plumbing, by making the exit code depend on it.

def _main_exit_code(tmp_path, monkeypatch, **env) -> int:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NLB_BASE_REF", "HEAD~1")
    monkeypatch.setenv("NLB_FAIL", "true")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return nlb.main()


def _repo_with_added_clause_line(tmp_path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        f"# Notes\n\n- A short bullet.\n- {_LONG_SEMICOLON}\n"
    )
    _commit(tmp_path, "add clause-joined line")


def test_clause_check_on_by_default_reaches_main_and_fails(tmp_path, monkeypatch):
    _repo_with_added_clause_line(tmp_path)
    assert _main_exit_code(tmp_path, monkeypatch) == 1


def test_clause_breaks_false_reaches_main_and_passes(tmp_path, monkeypatch):
    _repo_with_added_clause_line(tmp_path)
    assert _main_exit_code(tmp_path, monkeypatch, NLB_CLAUSE_BREAKS="false") == 0


def test_clause_min_length_env_var_reaches_main(tmp_path, monkeypatch):
    _repo_with_added_clause_line(tmp_path)
    # Raising the gate above the line's length silences it, which proves the
    # second env var is read too, not just the boolean.
    assert _main_exit_code(tmp_path, monkeypatch, NLB_CLAUSE_MIN_LENGTH="500") == 0


# ── malformed env values ─────────────────────────────────────────────────────

# #337 review round 3: both readers fell back silently. Falling back is right;
# doing it without a word is what hides a caller's typo.

def test_unrecognized_flag_value_reads_as_false_and_warns(monkeypatch, capsys):
    monkeypatch.setenv("NLB_CLAUSE_BREAKS", "yes")
    assert nlb._env_flag("NLB_CLAUSE_BREAKS", True) is False
    assert "::warning::" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["true", "TRUE", "false", ""])
def test_recognized_flag_values_do_not_warn(monkeypatch, capsys, value):
    monkeypatch.setenv("NLB_CLAUSE_BREAKS", value)
    nlb._env_flag("NLB_CLAUSE_BREAKS", True)
    assert capsys.readouterr().out == ""


def test_non_numeric_min_length_falls_back_to_the_default_and_warns(monkeypatch, capsys):
    """Round 3 fixed the negative branch but not this one.

    The section comment above says "both readers fell back silently", which
    was only made true for `_env_flag` and for `_env_int`'s *negative* input.
    An unparseable value -- the likelier typo, since `8o` and `80` differ by
    one keystroke -- still took the silent path (#337 review round 5).
    """
    monkeypatch.setenv("NLB_CLAUSE_MIN_LENGTH", "8o")
    assert nlb._env_int("NLB_CLAUSE_MIN_LENGTH", 80) == 80
    assert "::warning::" in capsys.readouterr().out


def test_unset_min_length_falls_back_silently(monkeypatch, capsys):
    """The warning must not fire when the caller simply did not set it.

    Guards the fix above from over-correcting: an unset variable is the
    normal case, and warning on it would make every default run noisy.
    """
    monkeypatch.delenv("NLB_CLAUSE_MIN_LENGTH", raising=False)
    assert nlb._env_int("NLB_CLAUSE_MIN_LENGTH", 80) == 80
    assert capsys.readouterr().out == ""


def test_negative_min_length_falls_back_to_the_default_and_warns(monkeypatch, capsys):
    # A negative gate admits every line, so it is invalid rather than merely
    # unusual -- and turning an advisory check into a firehose is exactly the
    # failure a silent fallback would hide.
    monkeypatch.setenv("NLB_CLAUSE_MIN_LENGTH", "-5")
    assert nlb._env_int("NLB_CLAUSE_MIN_LENGTH", 80) == 80
    assert "::warning::" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "80", "500"])
def test_non_negative_min_lengths_are_taken_as_given(monkeypatch, capsys, value):
    monkeypatch.setenv("NLB_CLAUSE_MIN_LENGTH", value)
    assert nlb._env_int("NLB_CLAUSE_MIN_LENGTH", 80) == int(value)
    assert capsys.readouterr().out == ""


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── stripping must not manufacture an interior semicolon ─────────────────────

# #337 review round 5: `strip_inline_markup(...).rstrip()` never left-trimmed,
# so whitespace left behind by a stripped construct could sit between the line
# start and a semicolon -- turning a semicolon that ends nothing into an
# "interior" one. The two cases below differ only by that space, so they are
# asserted together: either both are clause breaks or neither is, and the
# no-space form was already correctly ignored.

_PADDING = "word " * 20


def test_leading_semicolon_after_a_stripped_span_is_not_a_clause_break():
    text = "`code` ; " + _PADDING
    assert nlb.has_late_semicolon(text) is False


def test_leading_semicolon_with_and_without_a_space_agree():
    spaced = "`code` ; " + _PADDING
    tight = "`code`; " + _PADDING
    assert nlb.has_late_semicolon(spaced) == nlb.has_late_semicolon(tight)
