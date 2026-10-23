"""Tests for preview/skip-formats.py, which leaves slow formats out of a PR preview.

Every case runs the script's `main()` on a project written under `tmp_path`,
so the file layouts below are the contract: a `format:` mapping in
`_quarto*.yml` and in a page's front matter.
"""

import json
import os

import pytest

from conftest import write

PROJECT = """\
project:
  type: website

format:
  html:
    theme: cosmo
  revealjs:
    slide-level: 2
  pdf:
    toc: true
    # kept with its entry
    documentclass: article

  docx: default
execute:
  freeze: auto
"""

PAGE = """\
---
title: A page
format:
  html: default
  pdf:
    keep-tex: true
bibliography: !expr here("refs.bib")
---

format:
  pdf: this is body text, not front matter
"""


@pytest.fixture
def run(format_skipper, tmp_path, monkeypatch):
    def _run(skip="pdf docx", keep="", labels=()):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SKIP_FORMATS", skip)
        monkeypatch.setenv("KEEP_FORMATS", keep)
        monkeypatch.setenv("PR_LABELS", json.dumps(list(labels)))
        assert format_skipper.main() == 0

    return _run


def read(tmp_path, name):
    return (tmp_path / name).read_text(encoding="utf-8")


def test_removes_named_formats_and_keeps_the_rest(run, tmp_path):
    write(tmp_path, "_quarto.yml", PROJECT)
    run()
    text = read(tmp_path, "_quarto.yml")
    assert "pdf:" not in text and "docx:" not in text
    assert "documentclass" not in text and "# kept with its entry" not in text
    assert "html:\n    theme: cosmo" in text
    assert "revealjs:\n    slide-level: 2" in text
    assert "execute:\n  freeze: auto" in text


def test_pdf_label_keeps_pdf(run, tmp_path):
    write(tmp_path, "_quarto.yml", PROJECT)
    run(labels=["preview:pdf", "other"])
    text = read(tmp_path, "_quarto.yml")
    assert "pdf:\n    toc: true" in text
    assert "docx:" not in text


def test_keep_formats_keeps_docx_for_tracked_changes(run, tmp_path):
    write(tmp_path, "_quarto.yml", PROJECT)
    run(keep="docx")
    text = read(tmp_path, "_quarto.yml")
    assert "docx: default" in text
    assert "pdf:" not in text


def test_a_format_key_left_empty_is_removed(run, tmp_path):
    write(tmp_path, "_quarto.yml", "project:\n  type: book\nformat:\n  pdf:\n    toc: true\nlang: en\n")
    run()
    assert read(tmp_path, "_quarto.yml") == "project:\n  type: book\nlang: en\n"


def test_edits_front_matter_only(run, tmp_path):
    write(tmp_path, "page.qmd", PAGE)
    run()
    text = read(tmp_path, "page.qmd")
    head, _, body = text.partition("\n---\n\n")
    assert "pdf:" not in head and "keep-tex" not in head
    assert "html: default" in head
    assert "!expr here" in head
    assert "pdf: this is body text, not front matter" in body


def test_profile_files_and_nested_pages_are_edited(run, tmp_path):
    write(tmp_path, "_quarto-website.yml", PROJECT)
    write(tmp_path, "chapters/ch1.qmd", PAGE)
    run()
    assert "pdf:" not in read(tmp_path, "_quarto-website.yml")
    assert "pdf:" not in read(tmp_path, "chapters/ch1.qmd").split("\n---\n")[0]


def test_ignored_directories_are_left_alone(run, tmp_path):
    write(tmp_path, "_site/page.qmd", PAGE)
    write(tmp_path, "_freeze/x/_quarto.yml", PROJECT)
    run()
    assert read(tmp_path, "_site/page.qmd") == PAGE
    assert read(tmp_path, "_freeze/x/_quarto.yml") == PROJECT


def test_nothing_to_skip_changes_nothing(run, tmp_path):
    write(tmp_path, "_quarto.yml", PROJECT)
    run(skip="")
    assert read(tmp_path, "_quarto.yml") == PROJECT
    run(skip="pdf", labels=["preview:pdf"])
    assert read(tmp_path, "_quarto.yml") == PROJECT


def test_running_twice_is_a_no_op(run, tmp_path):
    write(tmp_path, "_quarto.yml", PROJECT)
    run()
    once = read(tmp_path, "_quarto.yml")
    run()
    assert read(tmp_path, "_quarto.yml") == once


def test_mtime_is_preserved(run, tmp_path):
    write(tmp_path, "_quarto.yml", PROJECT)
    os.utime(tmp_path / "_quarto.yml", (1_000_000_000, 1_000_000_000))
    run()
    assert int((tmp_path / "_quarto.yml").stat().st_mtime) == 1_000_000_000


def test_an_inline_format_entry_is_reported_not_silently_kept(run, tmp_path, capsys):
    write(tmp_path, "_quarto.yml", PROJECT)
    write(tmp_path, "page.qmd", "---\ntitle: T\nformat: pdf\n---\nBody\n")
    run()
    assert "format: pdf" in capsys.readouterr().err


def test_inline_entry_is_reported_even_when_nothing_else_changes(run, tmp_path, capsys):
    write(tmp_path, "page.qmd", "---\ntitle: T\nformat: pdf\n---\nBody\n")
    run()
    assert "format: pdf" in capsys.readouterr().err


def test_a_list_form_format_block_is_kept_beside_a_mapping_block(run, tmp_path):
    write(tmp_path, "_quarto.yml", "format:\n  - html\n  - pdf\n")
    write(tmp_path, "_quarto-website.yml", PROJECT)
    run()
    assert read(tmp_path, "_quarto.yml") == "format:\n  - html\n  - pdf\n"
    assert "pdf:" not in read(tmp_path, "_quarto-website.yml")
