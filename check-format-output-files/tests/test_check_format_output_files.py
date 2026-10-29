"""Tests for check-format-output-files."""

import importlib.util
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "check-format-output-files.py")
spec = importlib.util.spec_from_file_location("check_format_output_files", SCRIPT)
cfo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfo)

REQ = ["revealjs", "pdf", "docx"]

FULL = """---
title: "A"
format:
  html: default
  revealjs:
    output-file: a-slides.html
  pdf:
    output-file: a-handout.pdf
  docx:
    output-file: a.docx
---
body
"""

REVEAL = "  revealjs:\n    output-file: a-slides.html\n"


def check(text, required=REQ):
    return cfo.check_page("a.qmd", text.splitlines(), required)


def test_full_front_matter_passes():
    assert check(FULL) == []


def test_missing_revealjs_fails():
    # The mds linear-algebra.qmd case: --to revealjs wrote linear-algebra.html.
    findings = check(FULL.replace(REVEAL, ""))
    assert len(findings) == 1 and "omits revealjs" in findings[0].message


def test_inline_default_has_no_output_file():
    findings = check(FULL.replace(REVEAL, "  revealjs: default\n"))
    assert len(findings) == 1 and "no `output-file`" in findings[0].message
    assert findings[0].line == 5


def test_no_format_key_fails():
    assert len(check('---\ntitle: "A"\n---\nbody\n')) == 1


def test_no_front_matter_is_skipped():
    assert check("just text\n") == []


def test_required_formats_are_configurable():
    text = FULL.replace("  docx:\n    output-file: a.docx\n", "")
    assert check(text) and check(text, ["revealjs", "pdf"]) == []


def test_subfiles_are_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "_sub.qmd").write_text("---\ntitle: x\n---\n")
    (tmp_path / "page.qmd").write_text("---\ntitle: x\n---\n")
    subprocess.run(["git", "init", "-q", "."], check=True)
    subprocess.run(["git", "add", "."], check=True)
    findings = cfo.run(["*.qmd"], [], REQ)
    assert [f.path for f in findings] == ["page.qmd"]


def test_inline_flow_entry_with_output_file_passes():
    text = FULL.replace(REVEAL, "  revealjs: {output-file: a-slides.html}\n")
    assert check(text) == []


def test_flow_style_format_mapping_passes():
    text = ("---\nformat: {html: default, revealjs: {output-file: a.html}, "
            "pdf: {output-file: a.pdf}, docx: {output-file: a.docx}}\n---\n")
    assert check(text) == []


def test_flow_style_format_mapping_missing_output_file_fails():
    text = ("---\nformat: {revealjs: default, pdf: {output-file: a.pdf}, "
            "docx: {output-file: a.docx}}\n---\n")
    findings = check(text)
    assert len(findings) == 1 and "revealjs" in findings[0].message


def test_quoted_format_key_passes():
    text = FULL.replace("  revealjs:\n", '  "revealjs":\n')
    assert check(text) == []
