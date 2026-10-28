"""Tests for check-search-shortcut."""

import importlib.util
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "check-search-shortcut.py")
spec = importlib.util.spec_from_file_location("check_search_shortcut", SCRIPT)
css = importlib.util.module_from_spec(spec)
spec.loader.exec_module(css)


def check(**files):
    return css.check_project(".", {k: v.splitlines() for k, v in files.items()})


GOOD = 'website:\n  search:\n    keyboard-shortcut: ["/"]\n'


def test_slash_only_inline_passes():
    assert check(a=GOOD) == []


def test_slash_only_block_list_passes():
    text = "website:\n  search:\n    keyboard-shortcut:\n      - /\n"
    assert check(a=text) == []


def test_default_shortcut_missing_fails():
    findings = check(a="website:\n  title: x\n")
    assert len(findings) == 1 and findings[0].path is None


def test_f_in_list_fails():
    text = 'website:\n  search:\n    keyboard-shortcut: ["f", "/"]\n'
    findings = check(a=text)
    assert len(findings) == 1 and findings[0].line == 3


def test_s_in_block_list_fails():
    text = "website:\n  search:\n    keyboard-shortcut:\n      - /\n      - s\n"
    assert len(check(a=text)) == 1


def test_empty_shortcut_fails():
    text = "website:\n  search:\n    keyboard-shortcut: []\n"
    assert len(check(a=text)) == 1


def test_book_without_shortcut_fails():
    assert len(check(a="book:\n  title: x\n")) == 1


def test_book_with_shortcut_passes():
    assert check(a='book:\n  search:\n    keyboard-shortcut: ["/"]\n') == []


def test_search_off_passes():
    assert check(a="website:\n  search: false\n") == []


def test_project_without_site_passes():
    assert check(a="project:\n  type: default\n") == []


def test_shortcut_in_sibling_profile_file_passes():
    assert check(a="website:\n  title: x\n", b=GOOD) == []


def test_comment_after_value_ignored():
    text = 'website:\n  search:\n    keyboard-shortcut: ["/"]  # f is out\n'
    assert check(a=text) == []


def test_ignore_pattern_matches_extensions():
    assert css._ignored("_extensions/a/_quarto.yml", ["_extensions/**"])
    assert not css._ignored("_quarto.yml", ["_extensions/**"])


def test_nested_search_false_does_not_turn_search_off():
    text = "website:\n  sidebar:\n    style: docked\n    search: false\n"
    assert len(check(a=text)) == 1


def test_search_false_at_child_level_after_nested_block_counts():
    text = "website:\n  title: x\n  sidebar:\n    search: false\n  search: false\n"
    assert check(a=text) == []


def test_search_false_under_another_top_key_ignored():
    text = "format:\n  html:\n    search: false\nwebsite:\n  title: x\n"
    assert len(check(a=text)) == 1


def test_run_over_git_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "_quarto.yml").write_text("website:\n  title: x\n")
    subprocess.run(["git", "add", "_quarto.yml"], check=True)
    assert len(css.run(["_quarto*.yml"], [])) == 1
    (tmp_path / "_quarto.yml").write_text(GOOD)
    assert css.run(["_quarto*.yml"], []) == []
