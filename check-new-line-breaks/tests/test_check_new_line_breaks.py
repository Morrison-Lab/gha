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


# ── Sentence boundaries at a Markdown emphasis close (gha#397) ───────────────
#
# A sentence ending in emphasis puts the closing `**` between the period and
# the whitespace, so a closing-char class that omits `*`/`_` never sees the
# boundary, and a `**Claim.** Explanation.` line reads as one sentence.
# Measured 2026-08-03: adding the two characters raises the multi-sentence
# lines detected across Morrison-Lab/ai-config's Markdown from 2837 to 3398,
# so 561 lines -- about one in six of what the fixed check finds -- were
# invisible to it. Ported from ai-config's own test_slb.py (Bug 7/7b/7c/7d),
# whose sibling regex had the same defect.

def test_bold_close_is_a_sentence_boundary():
    result = nlb.split_sentences(
        "**Ending the head poll does not end the PR watch.** "
        "The two run at different frequencies."
    )
    assert result == [
        "**Ending the head poll does not end the PR watch.**",
        "The two run at different frequencies.",
    ]


def test_italic_close_is_a_sentence_boundary():
    result = nlb.split_sentences("See the note.* Then continue with the next point.")
    assert result == ["See the note.*", "Then continue with the next point."]


def test_underscore_emphasis_close_is_a_sentence_boundary():
    result = nlb.split_sentences(
        "__Ending the head poll does not end the PR watch.__ "
        "The two run at different rates."
    )
    assert result == [
        "__Ending the head poll does not end the PR watch.__",
        "The two run at different rates.",
    ]


def test_emphasis_close_before_lowercase_does_not_split():
    """Adding `*`/`_` to the closing class must not over-split.

    A bold close followed by a lowercase word is a continuing clause, not a
    sentence boundary; the uppercase-or-markup lookahead keeps it on one line.
    """
    text = "It is **critical.** yet often skipped on the first pass."
    assert nlb.split_sentences(text) == [text]


def test_bold_close_line_is_flagged_end_to_end():
    """The detector, not just the splitter: this line must be reported."""
    flagged = nlb.classify_line(
        "**Ending the head poll does not end the PR watch.** "
        "The two run at different frequencies."
    )
    assert flagged == "sentence"


# ── lowercase-opening second sentence (#389) ─────────────────────────────────

def test_lowercase_sentence_start_is_split():
    """A sentence opening with a bare lowercase identifier is a boundary.

    Our prose routinely starts a sentence with a package or repo name
    (`renv`, `serodynamics`); the check was silent on exactly those lines.
    """
    assert nlb.split_sentences(
        "agent disabled in both. serodynamics needed the /review path built."
    ) == [
        "agent disabled in both.",
        "serodynamics needed the /review path built.",
    ]
    assert nlb.split_sentences("it went red. renv restored the lockfile.") == [
        "it went red.",
        "renv restored the lockfile.",
    ]


def test_lowercase_start_line_is_flagged_end_to_end():
    """The detector, not just the splitter: a lowercase-continuation line reports."""
    flagged = nlb.classify_line("it went red. renv restored the lockfile.")
    assert flagged == "sentence"


# These first two pin the pre-existing `\s+`-after-terminator requirement (a
# decimal's `.` sits between digits with no following space), NOT the new
# lowercase-branch lookbehind -- deleting the lookbehind leaves both passing.
# `test_digit_ending_token_...` below is the one that exercises the lookbehind
# for a numeric-looking token.
def test_decimal_between_digits_does_not_split():
    text = "The lockfile drifted to 0.9012 in the diff."
    assert nlb.split_sentences(text) == [text]


def test_version_between_digits_does_not_split():
    text = "We pinned it to v2.1 for the release."
    assert nlb.split_sentences(text) == [text]


def test_version_at_clause_end_does_not_split():
    """`v2.1. renv`: unlike the internal-dot cases above, the trailing `.` here
    IS followed by whitespace, so `\\s+` matches -- the lookbehind is the sole
    guard (the char before the `.` is a digit). Mutation-verified: removing the
    lookbehind turns this into a false split."""
    text = "We shipped v2.1. renv restored it after."
    assert nlb.split_sentences(text) == [text]


def test_ellipsis_before_lowercase_does_not_split():
    """`wait... foo`: the only dot with a following space is the third, and the
    two characters immediately before it are both dots, so the `(?<=[a-z][a-z])`
    lookbehind fails there. The lookbehind -- not the immediate-whitespace guard
    -- is what blocks this one (mutation-verified: removing the lookbehind lets
    `wait...` split off)."""
    text = "wait... foo comes next here now."
    assert nlb.split_sentences(text) == [text]


def test_digit_ending_token_before_lowercase_does_not_split():
    """`plan9. really`: a token ending in a digit IS followed by whitespace and a
    lowercase word, so `\\s+` matches; the two-lowercase-letter lookbehind
    (`n9` is not two letters) is what refuses this split. Deleting the lookbehind
    turns this into a false split."""
    text = "It ships as plan9. really soon now here."
    assert nlb.split_sentences(text) == [text]


def test_single_letter_initial_before_lowercase_does_not_split():
    """`U.S. economy`: the terminal period follows a single uppercase letter,
    so the two-lowercase-letter lookbehind refuses the split."""
    text = "It is used across the U.S. economy at large."
    assert nlb.split_sentences(text) == [text]


def test_dotted_abbreviation_before_lowercase_does_not_split():
    """`a.m.`: the terminal period follows `.m`, not two lowercase letters."""
    text = "The build starts at 9 a.m. sharp every day."
    assert nlb.split_sentences(text) == [text]


def test_single_letter_word_before_lowercase_does_not_split():
    """A one-letter token like `a.` is not a genuine word ending."""
    text = "Option a. really works well in practice here."
    assert nlb.split_sentences(text) == [text]


def test_quoted_fragment_before_lowercase_does_not_split():
    """A mid-sentence quoted or parenthesized fragment ending in `.` followed by
    a lowercase word must NOT split: the lowercase branch has no closing-char
    class, so the `"` between the `.` and the space blocks `\\s+`. (The uppercase
    branch safely carries closers -- #397 added `*`/`_` to catch `**bold.**` --
    because its uppercase-follower lookahead refuses this mid-construct case; a
    lowercase follower does not, so a closer here would over-split.)"""
    text = 'He said "stop that." and then walked away.'
    assert nlb.split_sentences(text) == [text]


def test_lowercase_abbreviation_before_lowercase_does_not_split():
    """A lowercase `sec.` before a lowercase word is mid-sentence, so it must not
    split. Its lowercase form is protected only on the lowercase branch (via
    `_ABBREV_LOWER_RE`, applied after the uppercase branch runs)."""
    text = "Set the timeout to 3 sec. then wait a while."
    assert nlb.split_sentences(text) == [text]


def test_lowercase_abbreviation_before_uppercase_does_split():
    """The mirror of the previous test: the same lowercase unit abbreviation
    before an UPPERCASE follower IS a genuine sentence boundary and must split.
    This is why the lowercase-form protection is scoped to the lowercase branch
    only -- registering it on both branches (an earlier attempt) silently
    un-split `... ms. The next ...`. Regression guard for round-3 finding."""
    assert nlb.split_sentences(
        "It took 300 ms. The next run was faster."
    ) == ["It took 300 ms.", "The next run was faster."]
    assert nlb.split_sentences(
        "Refer to sec. The details are listed there."
    ) == ["Refer to sec.", "The details are listed there."]


def test_added_time_unit_before_lowercase_does_not_split():
    """`min` is added to the lowercase-only list because bare time units are
    common in this repo's timeout/duration prose; it must not false-split
    before a lowercase word."""
    text = "Set the retry backoff to 5 min. and then give up."
    assert nlb.split_sentences(text) == [text]


def test_incidental_lowercase_abbrev_before_lowercase_does_not_split():
    """`ms.` lands in the lowercase-only list incidentally -- as the lowercased
    form of the `Ms` title abbreviation, not a deliberate unit addition like
    `min` -- but it falls in the same duration prose, so pin its
    lowercase-follower behavior. (Its uppercase-follower case, which must still
    split, is covered by test_lowercase_abbreviation_before_uppercase_does_split
    above.)"""
    text = "It took 300 ms. then it retried the request."
    assert nlb.split_sentences(text) == [text]


def test_no_as_a_word_before_lowercase_does_split():
    """A lowercase `no.` is the English word ending a sentence, so it should
    split: `No` is protected only in its listed (title) case, not lowercase."""
    assert nlb.split_sentences("The answer is no. renv handles it fine.") == [
        "The answer is no.",
        "renv handles it fine.",
    ]


def test_number_abbreviation_before_uppercase_does_not_split():
    """`Item No. Three`: `No.` (the "number" abbreviation) must stay protected on
    the pre-existing uppercase branch. `_ABBREV_RE` runs before both branches, so
    the abbreviation list has to keep `No` for this case even though a lowercase
    `no.` splits (previous test). Regression guard for round-2 finding."""
    text = "Item No. Three is the failing one here."
    assert nlb.split_sentences(text) == [text]


def test_all_caps_abbreviation_lookalike_still_splits():
    """An ALL-CAPS abbreviation-lookalike (`SEC.`) is deliberately not protected,
    so a genuine sentence boundary after it still splits -- a blanket IGNORECASE
    would have added a false negative here."""
    assert nlb.split_sentences(
        "It was filed with the SEC. The case dragged on for years."
    ) == [
        "It was filed with the SEC.",
        "The case dragged on for years.",
    ]


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


def _find(tmp_path: Path, base_ref: str = "", globs=("*.md",), scope_mode: str = "auto"):
    import os
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        return nlb.find_violations(
            base_ref, list(globs), [],
            nlb._DEFAULT_CLAUSE_BREAKS, nlb._DEFAULT_CLAUSE_MIN_LENGTH,
            scope_mode,
        )
    finally:
        os.chdir(cwd)


def _checkout(tmp_path: Path, *args: str) -> None:
    subprocess.run(["git", "checkout", "-q", *args], cwd=tmp_path, check=True)


def _current_branch(tmp_path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=tmp_path, check=True, capture_output=True, encoding="utf-8",
    ).stdout.strip()


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


# -- gha#684: moved (relocated) content is not new content ------------------
#
# A PR that moves an existing block into a brand-new file shows every moved
# line as added -- there is no deletion of the source to pair against, since
# the source file still exists (modified, not deleted) -- so without the
# base-tree membership check, every previously-grandfathered line in the new
# file reflags. These four pin both directions: a verbatim move stays exempt,
# and anything actually new (a new line, or a line edited during the move)
# still flags.

def test_moved_block_to_new_file_is_not_flagged(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with pre-existing drift")
    (tmp_path / "notes.md").write_text("# Notes\n")
    (tmp_path / "moved.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "split the drift into a new file")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert violations == []


def test_new_violation_in_new_file_is_still_flagged(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    (tmp_path / "fresh.md").write_text("- Genuinely new. Two sentences.\n")
    _commit(tmp_path, "new file with a new violation")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("fresh.md", 1)]


def test_mixed_moved_and_new_lines_flags_only_the_new_one(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with pre-existing drift")
    (tmp_path / "notes.md").write_text("# Notes\n")
    (tmp_path / "moved.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
        "- Genuinely new. Two sentences.\n"
    )
    _commit(tmp_path, "split plus a new violation")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("moved.md", 2)]


def test_line_edited_during_move_is_flagged(tmp_path):
    # The exemption is verbatim-only: editing the line while relocating it is
    # new writing, so it must flag even though most of the text pre-exists.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with pre-existing drift")
    (tmp_path / "notes.md").write_text("# Notes\n")
    (tmp_path / "moved.md").write_text(
        "- Grandfathered drift, reworded in transit. Two sentences on one line.\n"
    )
    _commit(tmp_path, "move with an edit")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("moved.md", 1)]


def test_duplicate_of_untouched_base_line_is_still_flagged(tmp_path):
    # The exemption is keyed on the diff's own deleted lines, never on mere
    # membership in the base tree: a genuinely new line that happens to
    # duplicate a pre-existing line in a file this PR never touched is new
    # writing, and exempting it would hand authors a silent bypass (write any
    # known-grandfathered line verbatim and the check waves it through).
    _init_repo(tmp_path)
    (tmp_path / "untouched.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with pre-existing drift elsewhere")
    (tmp_path / "fresh.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "new file duplicating an untouched line")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("fresh.md", 1)]


def test_one_deletion_exempts_at_most_one_addition(tmp_path):
    # The deleted-lines record is a multiset: deleting a violating line once
    # while adding its exact text three times exempts only one of the three,
    # so a single legitimate deletion cannot launder unlimited duplicates.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with pre-existing drift")
    (tmp_path / "notes.md").write_text("# Notes\n")
    (tmp_path / "a.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    (tmp_path / "b.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    (tmp_path / "c.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "one deletion, three identical additions")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert len(violations) == 2


def test_two_deletions_exempt_two_additions(tmp_path):
    # The legitimate mirror of the case above: a base file carrying two
    # identical grandfathered lines that both move keeps both exemptions.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- Grandfathered drift. Two sentences on one line.\n"
        "\n## Later\n\n- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with the same drift twice")
    (tmp_path / "notes.md").write_text("# Notes\n\n## Later\n")
    (tmp_path / "a.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    (tmp_path / "b.md").write_text(
        "- Grandfathered drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "two deletions, two identical additions")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert violations == []


def test_moved_line_starting_with_two_dashes_is_exempt(tmp_path):
    # In the raw diff a deleted line whose content starts with "--" renders
    # as "---<content>", which prefix-sniffing mistook for a file header and
    # dropped from the deleted set, denying a real move its exemption. The
    # parser now decides header-vs-body by hunk position instead.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n-- Dashed drift, yes. Two sentences on one line.\n"
    )
    _commit(tmp_path, "base with dashed drift")
    (tmp_path / "notes.md").write_text("# Notes\n")
    (tmp_path / "moved.md").write_text(
        "-- Dashed drift, yes. Two sentences on one line.\n"
    )
    _commit(tmp_path, "move the dashed line")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert violations == []


def test_added_line_starting_with_two_pluses_is_still_flagged(tmp_path):
    # The added-line mirror: "++<content>" renders as "+++<content>", which
    # prefix-sniffing mistook for a file header -- skipping the line AND
    # desynchronizing the line counter for everything after it. Both the
    # dashed line and the ordinary one after it must be flagged, at the
    # right line numbers.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n++ Plussed drift, yes. Two sentences on one line.\n"
        "- Ordinary new drift. Two sentences on one line.\n"
    )
    _commit(tmp_path, "add a plussed line and an ordinary one")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [
        ("notes.md", 3), ("notes.md", 4)]


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


# -- working-tree-aware scope (gha#825) --------------------------------------
#
# `_added_line_numbers` used to diff `<base>...HEAD` -- committed only -- then
# read line *content* from the working tree, so a local run before committing
# reported "No lines missing semantic breaks" about lines it never examined.
# These pin the fix: "auto" scope widens to the working tree when it carries
# a change to a matched file, a committed run is unaffected (the control),
# a clean run of either scope reports how many lines it actually examined,
# and the merge-base anchor a stale base once relied on is unchanged.

def test_uncommitted_violation_is_flagged_in_auto_scope(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    # Add a violating line WITHOUT committing it.
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short bullet.\n- Two sentences. On one line.\n"
    )

    violations, skipped = _find(tmp_path, base_ref="HEAD")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("notes.md", 4)]
    assert [v.reason for v in violations] == ["sentence"]


def test_same_violation_committed_is_the_control(tmp_path):
    # Same bytes as the case above, committed instead of left uncommitted --
    # this is what already worked before gha#825, and must keep working.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short bullet.\n- Two sentences. On one line.\n"
    )
    _commit(tmp_path, "commit the violation")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("notes.md", 4)]
    assert [v.reason for v in violations] == ["sentence"]


def test_clean_dirty_tree_reports_examined_count(tmp_path, capsys):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    # Uncommitted, but clean: no violation, so the old code's silent "clean"
    # message would look identical to having examined nothing at all.
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short bullet.\n- A second, equally short bullet.\n"
    )

    violations, skipped = _find(tmp_path, base_ref="HEAD")
    assert not skipped
    assert violations == []
    out = capsys.readouterr().out
    assert "Examined 1 added line(s) across 1 file(s) (scope: working tree)." in out


def test_clean_committed_tree_reports_examined_count(tmp_path, capsys):
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short bullet.\n- A second, equally short bullet.\n"
    )
    _commit(tmp_path, "clean addition")

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert violations == []
    out = capsys.readouterr().out
    assert "Examined 1 added line(s) across 1 file(s) (scope: committed)." in out


def test_committed_scope_ignores_uncommitted_content(tmp_path, capsys):
    # Explicit override: even with a dirty tree, "committed" scope must not
    # widen -- this is CI's own behavior, made available on purpose. The
    # base is a prior commit that itself added one clean line, so the two
    # scopes actually disagree here: "committed" sees only that clean line
    # (1 examined, 0 violations), while "worktree"/"auto" would also pick up
    # the uncommitted violation below. Using base_ref=HEAD with nothing
    # committed would make every scope look identical and prove nothing.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short clean bullet.\n")
    _commit(tmp_path, "clean, committed addition")
    # Uncommitted on top: a real violation that "committed" scope must miss.
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short clean bullet.\n- Two sentences. On one line.\n"
    )

    violations, skipped = _find(tmp_path, base_ref="HEAD~1", scope_mode="committed")
    assert not skipped
    assert violations == []
    out = capsys.readouterr().out
    assert "Examined 1 added line(s) across 1 file(s) (scope: committed)." in out


def test_committed_scope_missing_violation_is_caught_by_auto(tmp_path):
    # The direct control for the test above: the same tree, same base,
    # under "auto" (which resolves to "worktree" since the tree is dirty)
    # DOES catch the uncommitted violation "committed" scope just missed.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short clean bullet.\n")
    _commit(tmp_path, "clean, committed addition")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short clean bullet.\n- Two sentences. On one line.\n"
    )

    violations, skipped = _find(tmp_path, base_ref="HEAD~1")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("notes.md", 4)]


def test_staged_but_uncommitted_violation_is_flagged(tmp_path):
    # `git add` without a commit: content lives in the index, not just the
    # working tree. A plain `git diff <merge_base>` (no `--cached`) folds
    # both staged and unstaged changes into one diff against the working
    # tree, so this must be caught exactly like the fully-unstaged case.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n\n- A short bullet.\n")
    _commit(tmp_path, "base")
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A short bullet.\n- Two sentences. On one line.\n"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    violations, skipped = _find(tmp_path, base_ref="HEAD")
    assert not skipped
    assert [(v.path, v.line) for v in violations] == [("notes.md", 4)]


def test_untracked_file_does_not_widen_scope_and_warns(tmp_path, capsys):
    # A brand-new untracked file must NOT flip "auto" to "worktree" on its
    # own -- plain `git diff` cannot show it either way, so widening would
    # promise an examination that never happens. It should instead be named
    # in an explicit warning, and the tracked tree stays clean/committed.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    (tmp_path / "untracked.md").write_text("- A violation. Right here.\n")

    violations, skipped = _find(tmp_path, base_ref="HEAD")
    assert not skipped
    assert violations == []
    out = capsys.readouterr().out
    assert "Examined 0 added line(s) across 0 file(s) (scope: committed)." in out
    assert "untracked.md" in out
    assert "not examined" in out


def test_base_branch_advancing_is_not_flagged_via_merge_base_worktree_scope(tmp_path):
    # The dirty-tree companion to the test above: an uncommitted (not just
    # committed) addition on the diverged feature branch must also stay
    # unaffected by the base branch's own later violation, exercising
    # "worktree" scope (via "auto") rather than "committed". All branch
    # switching happens on a CLEAN tree; the uncommitted edit is made last,
    # since git refuses to switch branches out from under a dirty file.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    trunk = _current_branch(tmp_path)

    _checkout(tmp_path, "-b", "feature2")
    (tmp_path / "feature.md").write_text("- A clean addition here.\n")
    _commit(tmp_path, "feature work")

    _checkout(tmp_path, trunk)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A base-branch violation. Two sentences.\n"
    )
    _commit(tmp_path, "base branch advances with its own violation")

    _checkout(tmp_path, "feature2")
    # Leave an UNCOMMITTED clean addition, so "auto" resolves to "worktree".
    (tmp_path / "feature.md").write_text(
        "- A clean addition here.\n- Another clean one.\n"
    )
    violations, skipped = _find(tmp_path, base_ref=trunk)
    assert not skipped
    assert violations == []


def test_empty_diff_reports_zero_and_passes(tmp_path, capsys):
    # No changes at all, committed or otherwise: the reported count must
    # read zero rather than being silently indistinguishable from a pass
    # over real content.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")

    violations, skipped = _find(tmp_path, base_ref="HEAD")
    assert not skipped
    assert violations == []
    out = capsys.readouterr().out
    assert "Examined 0 added line(s) across 0 file(s) (scope: committed)." in out


def test_base_branch_advancing_is_not_flagged_via_merge_base(tmp_path):
    # The merge-base anchor `<base>...HEAD` already had must be unchanged by
    # the fix: a violation the base branch picks up *after* the feature
    # branch diverged must still not be flagged, in either scope.
    _init_repo(tmp_path)
    (tmp_path / "notes.md").write_text("# Notes\n")
    _commit(tmp_path, "base")
    trunk = _current_branch(tmp_path)

    _checkout(tmp_path, "-b", "feature")
    (tmp_path / "feature.md").write_text("- A clean addition here.\n")
    _commit(tmp_path, "feature work")

    _checkout(tmp_path, trunk)
    (tmp_path / "notes.md").write_text(
        "# Notes\n\n- A base-branch violation. Two sentences.\n"
    )
    _commit(tmp_path, "base branch advances with its own violation")

    _checkout(tmp_path, "feature")
    violations, skipped = _find(tmp_path, base_ref=trunk)
    assert not skipped
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
# 'false'`, which proves `action.yml` parses and the opt-out path runs. These
# cases are what actually prove the plumbing, by making the exit code depend on it.

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


@pytest.mark.parametrize("path", [_ACTION_YML, _WORKFLOW_YML])
def test_declared_fail_default_matches_script_default(path):
    assert (_declared_default(path, "fail") == "true") is nlb._DEFAULT_FAIL


def test_violations_emit_error_annotations_when_fail_false(tmp_path, monkeypatch, capsys):
    _repo_with_added_clause_line(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NLB_BASE_REF", "HEAD~1")
    monkeypatch.setenv("NLB_FAIL", "false")
    exit_code = nlb.main()
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "::error file=notes.md,line=4::" in out
    assert "::warning file=" not in out


def test_violations_emit_error_annotations_when_fail_unset(tmp_path, monkeypatch, capsys):
    _repo_with_added_clause_line(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NLB_BASE_REF", "HEAD~1")
    monkeypatch.delenv("NLB_FAIL", raising=False)
    exit_code = nlb.main()
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "::error file=notes.md,line=4::" in out
    assert "::warning file=" not in out


def test_violations_emit_error_annotations_when_fail_true(tmp_path, monkeypatch, capsys):
    _repo_with_added_clause_line(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NLB_BASE_REF", "HEAD~1")
    monkeypatch.setenv("NLB_FAIL", "true")
    exit_code = nlb.main()
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "::error file=notes.md,line=4::" in out
    assert "::warning file=" not in out


# ── malformed env values ─────────────────────────────────────────────────────

# #337 review round 3: both readers fell back silently. Falling back is right;
# doing it without a word is what hides a caller's typo.

def test_unrecognized_flag_value_falls_back_to_default_and_warns(monkeypatch, capsys):
    monkeypatch.setenv("NLB_CLAUSE_BREAKS", "yes")
    assert nlb._env_flag("NLB_CLAUSE_BREAKS", True) is True
    assert nlb._env_flag("NLB_CLAUSE_BREAKS", False) is False
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
    # unusual -- and turning the check into a firehose is exactly the
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
