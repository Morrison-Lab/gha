"""Tests for redirect-stubs.py."""

import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "redirect_stubs", os.path.join(HERE, os.pardir, "redirect-stubs.py"))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def write(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_finds_only_stubs(tmp_path):
    write(tmp_path, "a.qmd", "---\ntitle: A\nredirect-stub: true\n---\n")
    write(tmp_path, "b.qmd", "---\ntitle: B\n---\n")
    write(tmp_path, "c.qmd", "---\ntitle: C\nredirect-stub: false\n---\n")
    write(tmp_path, "sub/d.qmd", "---\nredirect-stub: true\n---\n")
    write(tmp_path, "_e.qmd", "---\nredirect-stub: true\n---\n")
    write(tmp_path, "_extensions/x/f.qmd", "---\nredirect-stub: true\n---\n")
    assert rs.find_stubs(str(tmp_path)) == ["a.qmd", "sub/d.qmd"]


def test_key_after_front_matter_is_ignored(tmp_path):
    write(tmp_path, "a.qmd", "---\ntitle: A\n---\nredirect-stub: true\n")
    assert rs.find_stubs(str(tmp_path)) == []


def test_writes_profile_only_with_stubs(tmp_path):
    write(tmp_path, "a.qmd", "---\ntitle: A\n---\n")
    assert rs.main(["x", str(tmp_path), "skip"]) == 0
    assert not (tmp_path / "_quarto-skip.yml").exists()
    write(tmp_path, "_quarto.yml", "project:\n  type: default\n")
    write(tmp_path, "s.qmd", "---\nredirect-stub: true\n---\n")
    rs.main(["x", str(tmp_path), "skip"])
    text = (tmp_path / "_quarto-skip.yml").read_text()
    assert text.startswith('project:\n  render:\n    - "**/*.qmd"\n')
    assert text.endswith('    - "!s.qmd"\n')


def test_exclusion_only_when_project_lists_pages(tmp_path):
    write(tmp_path, "_quarto.yml", 'project:\n  render:\n    - "*.qmd"\n')
    write(tmp_path, "s.qmd", "---\nredirect-stub: true\n---\n")
    rs.main(["x", str(tmp_path), "skip"])
    text = (tmp_path / "_quarto-skip.yml").read_text()
    assert text == 'project:\n  render:\n    - "!s.qmd"\n'
