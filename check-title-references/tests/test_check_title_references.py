"""Unit tests for check-title-references.

Covers what is flagged (a link whose text is the title of the heading or page it
targets, with no content type beside it), what passes (a type word before or
after, a term link, an external link, a different text), the skips (code,
comments, front matter, the allow marker), diff scoping, the skip-not-fallback
guard, and the defaults the action and script must agree on.
"""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_title_references", _DIR / "check-title-references.py"
)
assert _spec is not None and _spec.loader is not None
ctr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ctr)

PAGE = """---
title: "Regularization"
---

# Overview

## Practical considerations

## Choosing λ {#sec-choosing}

Body line.
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctr.reset_index()
    subprocess.run(["git", "init", "-q", "."], check=True)
    (tmp_path / "reg.qmd").write_text(PAGE)
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "-c", "user.email=t@example.org", "-c", "user.name=t",  # phi-allow
                    "commit", "-qm", "init"], check=True)
    yield tmp_path
    ctr.reset_index()


def flagged(line):
    findings, _ = ctr.scan_file([line])
    return [f.phrase for f in findings]


@pytest.mark.parametrize("line", [
    "See [Practical considerations](#practical-considerations) for more.",
    "See [Practical considerations](reg.qmd#practical-considerations).",
    "See [practical considerations](reg.html#practical-considerations).",
    "See [Choosing λ](#sec-choosing).",
    "Read [Regularization](reg.qmd) first.",
    "See [**Practical considerations**](#practical-considerations).",
])
def test_bare_title_link_is_flagged(repo, line):
    assert len(flagged(line)) == 1


@pytest.mark.parametrize("line", [
    "See the [Practical considerations](#practical-considerations) section.",
    "See the section [Practical considerations](#practical-considerations).",
    "See Section [Practical considerations](#practical-considerations).",
    "See the section titled \"[Practical considerations](#practical-considerations)\".",
    "Read the [Regularization](reg.qmd) chapter.",
    "Read the [Regularization](reg.qmd) page.",
    "See the [Overview](#overview) subsection.",
])
def test_type_word_beside_the_link_passes(repo, line):
    assert flagged(line) == []


@pytest.mark.parametrize("line", [
    "A [ridge penalty](#practical-considerations) matters.",
    "A [regularization](#def-regularization) term.",
    "See [Practical considerations](https://example.org/#practical-considerations).",
    "See [Practical considerations](#no-such-anchor).",
    "See [Practical considerations](reg.qmd#overview).",
    "![Practical considerations](#practical-considerations)",
    "See @sec-choosing.",
])
def test_other_links_pass(repo, line):
    assert flagged(line) == []


def test_skips_code_comments_and_allow_marker(repo):
    link = "[Practical considerations](#practical-considerations)"
    lines = [
        f"`{link}`",
        f"<!-- {link} -->",
        f"See {link}. <!-- check-title-references: allow -->",
        "```",
        link,
        "```",
    ]
    findings, _ = ctr.scan_file(lines)
    assert findings == []


def test_front_matter_is_skipped(repo):
    lines = ["---", "x: [Practical considerations](#practical-considerations)", "---"]
    assert ctr.scan_file(lines)[0] == []


def test_slug_matches_pandoc():
    assert ctr.slugify("Practical considerations") == "practical-considerations"
    assert ctr.slugify("1. Why it *works*") == "why-it-works"


def run_main(monkeypatch, tmp_path, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return ctr.main()


def commit_page(repo, text):
    (repo / "new.qmd").write_text(f'---\ntitle: "N"\n---\n\n{text}\n')
    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "-c", "user.email=t@example.org", "-c", "user.name=t",  # phi-allow
                    "commit", "-qm", "add"], check=True)


def test_added_line_fails_and_untouched_line_does_not(repo, monkeypatch):
    commit_page(repo, "See [Overview](#overview).")
    code = run_main(monkeypatch, repo, CTR_BASE_REF="HEAD^", CTR_GLOBS="*.qmd")
    assert code == 1
    ctr.reset_index()
    assert run_main(monkeypatch, repo, CTR_BASE_REF="HEAD", CTR_GLOBS="*.qmd") == 0


def test_fail_false_warns_only(repo, monkeypatch):
    commit_page(repo, "See [Overview](#overview).")
    code = run_main(monkeypatch, repo, CTR_BASE_REF="HEAD^", CTR_GLOBS="*.qmd",
                    CTR_FAIL="false")
    assert code == 0


def test_no_base_skips_instead_of_scanning_whole_tree(repo, monkeypatch, capsys):
    commit_page(repo, "See [Overview](#overview).")
    monkeypatch.delenv("CTR_BASE_REF", raising=False)
    assert run_main(monkeypatch, repo, CTR_GLOBS="*.qmd") == 0
    assert "Skipping" in capsys.readouterr().out


def input_default(text, name):
    """The ``default:`` of the input ``name`` in an action or workflow file."""
    match = re.search(
        rf"^( +){name}:\n(?:\1 +.*\n)*?\1 +default: *'?([^'\n]*)'?$",
        text, re.MULTILINE)
    assert match, f"no default for input {name}"
    return match.group(2)


def test_defaults_agree_across_script_action_and_workflow():
    action = (_DIR / "action.yml").read_text()
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-title-references.yml").read_text()
    assert "CTR_FAIL: ${{ inputs.fail }}" in action
    assert "CTR_GLOBS: ${{ inputs.globs }}" in action
    assert ctr._DEFAULT_FAIL is True
    for text in (action, workflow):
        assert input_default(text, "fail") == "true"
        assert input_default(text, "globs") == ctr.DEFAULT_GLOBS
        assert input_default(text, "whole-tree") == "false"
