r"""Unit tests for check-result-definition-links.

Fixtures: a result div with a cross-reference, with a link to a #def- anchor, and
with no definition link (flagged); the opt-out comment; other div kinds; and
diff scoping.
"""

import importlib.util
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_result_definition_links", _DIR / "check-result-definition-links.py")
assert _spec is not None and _spec.loader is not None
crdl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crdl)


def div(kind="thm", body="Every @def-variance is nonnegative."):
    return f"::: {{#{kind}-a}}\n{body}\n:::\n"


def run(text: str, touched=None):
    return crdl.check_file("a.qmd", text.split("\n"), touched)


def test_cross_reference_counts():
    assert run(div()) == []


def test_bracketed_cross_reference_counts():
    assert run(div(body="See [@def-variance].")) == []


@pytest.mark.parametrize("target", [
    "#def-variance",
    "variance.qmd#def-variance",
    "https://morrison-lab.github.io/pds/variance-covariance.html#def-variance",
])
def test_link_to_a_definition_anchor_counts(target):
    assert run(div(body=f"The [variance]({target}) is nonnegative.")) == []


def test_result_with_no_definition_link_is_flagged():
    findings = run(div(body="The variance is nonnegative."))
    assert len(findings) == 1
    assert "#thm-a" in findings[0].message
    assert findings[0].line == 1


def test_link_to_a_non_definition_is_flagged():
    assert len(run(div(body="By [Jensen](#thm-jensen) and @thm-jensen."))) == 1


def test_handle_or_path_with_at_sign_is_not_a_reference():
    assert len(run(div(body="Handle name@def-x or see a/@def-x."))) == 1


@pytest.mark.parametrize("kind", ["thm", "lem", "cor", "prp"])
def test_each_result_kind_is_checked(kind):
    assert len(run(div(kind=kind, body="Nothing linked."))) == 1


@pytest.mark.parametrize("kind", ["def", "rem", "exm", "exr"])
def test_other_div_kinds_are_not_checked(kind):
    assert run(div(kind=kind, body="Nothing linked.")) == []


def test_opt_out_comment_exempts_the_div():
    body = "<!-- check-result-definition-links: allow: a numeric identity -->\n1 + 1 = 2."
    assert run(div(body=body)) == []


def test_a_link_inside_a_comment_or_fence_does_not_count():
    body = "<!-- @def-x -->\n```\n@def-y\n```\nNothing linked."
    assert len(run(div(body=body))) == 1


def test_a_link_in_a_nested_proof_counts():
    text = "::: {#thm-a}\nClaim.\n\n::: proof\nBy @def-variance.\n:::\n:::\n"
    assert run(text) == []


def test_only_touched_divs_are_checked():
    text = div(body="One.") + "\n" + div(kind="lem", body="Two.")
    findings = run(text, touched={6})
    assert [f.message.split(":")[0] for f in findings] == ["#lem-a"]
    assert run(text, touched={99}) == []


def test_main_exit_codes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    import subprocess
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "p.qmd").write_text(div(body="Nothing linked."))
    subprocess.run(["git", "add", "p.qmd"], check=True)
    monkeypatch.setenv("CRDL_WHOLE_TREE", "true")
    assert crdl.main() == 0
    monkeypatch.setenv("CRDL_FAIL", "true")
    assert crdl.main() == 1
    monkeypatch.delenv("CRDL_WHOLE_TREE")
    assert crdl.main() == 0
