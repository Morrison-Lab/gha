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
    assert [(f, ln) for f, ln, _ in violations] == [("notes.md", 4)]


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
