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


def failing_inspect(monkeypatch):
    failed = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
    monkeypatch.setattr(rs.subprocess, "run", lambda *a, **k: failed)


def test_failed_inspect_appends_exclusions_to_render_list(tmp_path, monkeypatch, capsys):
    # quarto inspect fails on mds and pds (gha#1214); the render must go on.
    pytest.importorskip("yaml")
    write(tmp_path, "_quarto.yml", 'project:\n  render:\n    - "*.qmd"\n')
    write(tmp_path, "a.qmd", REAL_PAGE)
    write(tmp_path, "s.qmd", STUB_PAGE)
    failing_inspect(monkeypatch)
    assert rs.main(["x", str(tmp_path), "skip"]) == 0
    assert capsys.readouterr().out == "1\n"
    text = (tmp_path / "_quarto-skip.yml").read_text()
    assert text == 'project:\n  render:\n    - "!s.qmd"\n'


def test_failed_inspect_without_render_list_skips_nothing(tmp_path, monkeypatch, capsys):
    # The pages Quarto would render (.md, nested pages) are then not known,
    # so neither a narrowed list nor an empty one may be written.
    pytest.importorskip("yaml")
    write(tmp_path, "_quarto.yml", "project:\n  type: default\n")
    write(tmp_path, "s.qmd", STUB_PAGE)
    write(tmp_path, "sub/a.qmd", REAL_PAGE)
    failing_inspect(monkeypatch)
    monkeypatch.delenv("QUARTO_PROFILE", raising=False)
    assert rs.main(["x", str(tmp_path), "skip", "website"]) == 0
    assert capsys.readouterr().out == "0\n"
    assert not (tmp_path / "_quarto-skip.yml").exists()
    assert "QUARTO_PROFILE" not in os.environ
    monkeypatch.setenv("QUARTO_PROFILE", "caller")
    rs.main(["x", str(tmp_path), "skip", "website"])
    assert os.environ["QUARTO_PROFILE"] == "caller"


def test_failed_inspect_without_pyyaml_skips_nothing(tmp_path):
    # A runner image may lack PyYAML; the publish must go on.
    write(tmp_path, "proj/_quarto.yml", 'project:\n  render:\n    - "*.qmd"\n')
    write(tmp_path, "proj/s.qmd", STUB_PAGE)
    write(tmp_path, "block/yaml.py", "raise ImportError('no yaml')\n")
    write(tmp_path, "bin/quarto", "#!/bin/sh\nexit 1\n")
    (tmp_path / "bin/quarto").chmod(0o755)
    env = dict(os.environ, PYTHONPATH=str(tmp_path / "block"),
               PATH="%s%s%s" % (tmp_path / "bin", os.pathsep, os.environ["PATH"]))
    result = subprocess.run(["python3", SCRIPT, str(tmp_path / "proj"), "skip"],
                            env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "0\n"
    assert not (tmp_path / "proj/_quarto-skip.yml").exists()
