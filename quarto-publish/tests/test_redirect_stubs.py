"""Tests for redirect-stubs.py."""

import importlib.util
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "redirect-stubs.py")
spec = importlib.util.spec_from_file_location("redirect_stubs", SCRIPT)
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

STUB_PAGE = "---\ntitle: S\nredirect-stub: true\nformat:\n  html: default\n---\nmoved\n"
REAL_PAGE = (
    "---\ntitle: A\nformat:\n  html: default\n  revealjs:\n"
    "    output-file: a-slides.html\n---\n# H\nhi\n"
)


def write(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def fake_inspect(render, inputs):
    def inspect(project, active):
        config = {"project": {"render": render}} if render else {}
        return {"config": config,
                "files": {"input": [os.path.join(project, p) for p in inputs]}}
    return inspect


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


def test_no_file_without_stubs(tmp_path, monkeypatch):
    write(tmp_path, "a.qmd", "---\ntitle: A\n---\n")
    monkeypatch.setattr(rs, "inspect_project", fake_inspect(None, ["a.qmd"]))
    assert rs.main(["x", str(tmp_path), "skip"]) == 0
    assert not (tmp_path / "_quarto-skip.yml").exists()


def test_exclusions_only_when_project_lists_pages(tmp_path, monkeypatch):
    write(tmp_path, "s.qmd", STUB_PAGE)
    monkeypatch.setattr(rs, "inspect_project", fake_inspect(["*.qmd"], ["s.qmd"]))
    rs.main(["x", str(tmp_path), "skip"])
    text = (tmp_path / "_quarto-skip.yml").read_text()
    assert text == 'project:\n  render:\n    - "!s.qmd"\n'


def test_inputs_minus_stubs_when_project_lists_no_pages(tmp_path, monkeypatch):
    write(tmp_path, "s.qmd", STUB_PAGE)
    monkeypatch.setattr(rs, "inspect_project",
                        fake_inspect(None, ["s.qmd", "a.qmd", "sub/b.qmd"]))
    rs.main(["x", str(tmp_path), "skip"])
    text = (tmp_path / "_quarto-skip.yml").read_text()
    assert text == 'project:\n  render:\n    - "a.qmd"\n    - "sub/b.qmd"\n'


@pytest.mark.skipif(shutil.which("quarto") is None, reason="quarto is not installed")
@pytest.mark.parametrize("with_list", [False, True])
def test_real_render_builds_no_stub_deck(tmp_path, with_list):
    config = "project:\n  type: default\n"
    if with_list:
        config += '  render:\n    - "*.qmd"\n'
    write(tmp_path, "_quarto.yml", config)
    write(tmp_path, "a.qmd", REAL_PAGE)
    write(tmp_path, "s.qmd", STUB_PAGE)
    write(tmp_path, "_sub.qmd", "---\ntitle: sub\n---\nsub\n")
    assert rs.main(["x", str(tmp_path), "gha-skip-stubs"]) == 0
    subprocess.run(
        ["quarto", "render", str(tmp_path), "--profile", "gha-skip-stubs",
         "--to", "revealjs", "--output-dir", "out"],
        check=True, capture_output=True)
    built = sorted(os.listdir(tmp_path / "out"))
    assert "a-slides.html" in built
    assert "s.html" not in built
    assert "_sub.html" not in built


def test_empty_render_list_is_an_empty_list_not_null(tmp_path, monkeypatch):
    write(tmp_path, "s.qmd", STUB_PAGE)
    monkeypatch.setattr(rs, "inspect_project", fake_inspect(None, ["s.qmd"]))
    rs.main(["x", str(tmp_path), "skip"])
    text = (tmp_path / "_quarto-skip.yml").read_text()
    assert text == "project:\n  render: []\n"


def test_is_stub_mode_exit_status(tmp_path):
    write(tmp_path, "s.qmd", STUB_PAGE)
    write(tmp_path, "a.qmd", REAL_PAGE)
    assert rs.main(["x", "--is-stub", str(tmp_path / "s.qmd")]) == 0
    assert rs.main(["x", "--is-stub", str(tmp_path / "a.qmd")]) == 1
