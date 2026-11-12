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
    ignores = css.diffscope.compile_ignores(["_extensions/**"])
    assert css.diffscope.ignored("_extensions/a/_quarto.yml", ignores)
    assert not css.diffscope.ignored("_quarto.yml", ignores)


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


def test_default_globs_reach_a_nested_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "_quarto.yml").write_text("website:\n  title: x\n")
    subprocess.run(["git", "add", "docs/_quarto.yml"], check=True)
    assert len(css.run(css.DEFAULT_GLOBS.split(), [])) == 1


def test_directory_name_with_a_quote_is_listed(tmp_path, monkeypatch):
    # git quotes such a name in a plain ls-files listing (gha#1923).
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    sub = tmp_path / 'say"hi'
    sub.mkdir()
    (sub / "_quarto.yml").write_text("website:\n  title: x\n")
    subprocess.run(["git", "add", "--", 'say"hi/_quarto.yml'], check=True)
    found = css.run(css.DEFAULT_GLOBS.split(), [])
    assert [f.directory for f in found] == ['say"hi']


def test_bare_directory_ignore_skips_its_contents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "_quarto.yml").write_text("website:\n  title: x\n")
    subprocess.run(["git", "add", "docs/_quarto.yml"], check=True)
    assert css.run(css.DEFAULT_GLOBS.split(), ["docs"]) == []


def test_outside_a_git_checkout_exits_with_an_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    try:
        css.run(css.DEFAULT_GLOBS.split(), [])
    except SystemExit as exc:
        assert "git ls-files failed" in str(exc)
    else:
        raise AssertionError("run() returned outside a git checkout")
