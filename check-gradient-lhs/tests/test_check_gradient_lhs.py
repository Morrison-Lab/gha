"""Unit tests for check-gradient-lhs (gha#1538).

Covers the stated-gradient forms that are flagged, the ones that pass (the
symbol on the left, no equation, code, comments), the display-equation
lookahead, diff scoping, the allow comment, and the defaults the script,
action and reusable workflow must agree on.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_gradient_lhs", _DIR / "check-gradient-lhs.py")
assert _spec is not None and _spec.loader is not None
cgl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cgl)


def flagged(text: str):
    findings, _ = cgl.scan_file(text.split("\n"), None)
    return [f.line for f in findings]


def test_inline_gradient_without_symbol_is_flagged():
    assert flagged("Its gradient is $2 \\vx$.") == [1]


def test_gradient_equals_inline_math_is_flagged():
    assert flagged("The gradient equals $\\vzero$ at the minimum.") == [1]


def test_symbol_on_the_left_inline_passes():
    assert flagged("The gradient is $\\gradf{f}(\\vx) = 2 \\vx$.") == []


def test_nabla_on_the_left_passes():
    assert flagged("The gradient is $\\nabla f(x) = 2x$.") == []


def test_display_equation_without_symbol_is_flagged():
    text = "The gradient is:\n\n$$\n2 \\vx = \\vy\n$$\n"
    assert flagged(text) == [1]


def test_display_equation_with_symbol_passes():
    text = "The gradient is:\n\n$$\n\\gradf{f}(\\vx) = 2 \\vx\n$$\n"
    assert flagged(text) == []


def test_display_with_a_blank_line_before_it_is_followed():
    text = "The gradient is\n\n$$\\gradwrt{\\vx}{f} = 2\\vx$$\n"
    assert flagged(text) == []


def test_no_equation_following_passes():
    assert flagged("The gradient is zero at the minimum.\n") == []
    assert flagged("The gradient is\n\nMore prose follows.\n") == []


def test_gradient_without_is_passes():
    assert flagged("The gradient points uphill.") == []


def test_code_and_comments_are_not_read():
    assert flagged("```\nThe gradient is $x$\n```\n") == []
    assert flagged("<!-- The gradient is $x$ -->") == []


def test_allow_comment_on_the_line_or_before():
    assert flagged("Its gradient is $2 \\vx$. <!-- check-gradient-lhs: allow -->") == []
    assert flagged("<!-- check-gradient-lhs: allow -->\nIts gradient is $2 \\vx$.") == []


def test_keep_restricts_to_added_lines():
    lines = ["Its gradient is $2 \\vx$.", "Other."]
    assert cgl.scan_file(lines, {2})[0] == []
    assert len(cgl.scan_file(lines, {1})[0]) == 1


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")  # phi-allow: synthetic test address
    _git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit(repo, name, text):
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", "c")


def test_main_warns_by_default_and_fails_when_asked(repo, monkeypatch, capsys):
    _commit(repo, "a.qmd", "Intro.\n")
    _commit(repo, "a.qmd", "Intro.\nIts gradient is $2 \\vx$.\n")
    monkeypatch.setenv("CGL_BASE_REF", "HEAD~1")
    assert cgl.main() == 0
    assert "::warning" in capsys.readouterr().out
    monkeypatch.setenv("CGL_FAIL", "true")
    assert cgl.main() == 1


def test_no_base_ref_skips(repo, monkeypatch, capsys):
    _commit(repo, "a.qmd", "Its gradient is $2 \\vx$.\n")
    monkeypatch.delenv("CGL_BASE_REF", raising=False)
    assert cgl.main() == 0
    assert "Skipping" in capsys.readouterr().out


def test_defaults_agree_across_script_action_and_workflow():
    root = _DIR.parent
    assert cgl._DEFAULT_FAIL is False
    for path in (_DIR / "action.yml", root / ".github" / "workflows" / "check-gradient-lhs.yml"):
        text = path.read_text(encoding="utf-8")
        fail = re.search(r"\n\s+fail:\n(?:.*\n)*?\s+default:\s*'?(\w+)'?", text)
        assert fail and fail.group(1) == "false", path
        globs = re.search(r"\n\s+globs:\n(?:.*\n)*?\s+default:\s*'([^']*)'", text)
        assert globs and globs.group(1) == cgl.DEFAULT_GLOBS, path
