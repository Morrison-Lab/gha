"""Unit tests for check-quarto-links.

The fixtures are throwaway git repositories built in ``tmp_path`` per case,
never committed, so no other selftest job's repo-wide scan sweeps up a dead
link on purpose.

The cases worth keeping if this is ever trimmed are the NEGATIVE ones,
because each pins a decision that is silent when reversed:

  * a link inside a fenced code block, a code span or an HTML comment is not
    a link
  * a subfile's link is resolved from the page that includes it, and a
    `_`-prefixed file nothing includes is skipped rather than resolved from
    its own directory
  * an escaped include (``{{</* include */>}}``) includes nothing
  * `fail: yes` still blocks (fail-closed)

check-quarto-links.py is not an importable module name (the hyphen), so it
is loaded by path, the same pattern check-new-line-breaks/tests uses.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MOD_PATH = _HERE.parent / "check-quarto-links.py"
_ACTION_YML = _HERE.parent / "action.yml"
_WORKFLOW_YML = _HERE.parent.parent / ".github" / "workflows" / "check-quarto-links.yml"
_spec = importlib.util.spec_from_file_location("check_quarto_links", _MOD_PATH)
assert _spec is not None and _spec.loader is not None
ql = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ql)


def _repo(tmp_path: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def _findings(tmp_path, monkeypatch, files, exts=".qmd, .md, .Rmd, .ipynb"):
    _repo(tmp_path, files)
    monkeypatch.chdir(tmp_path)
    tracked = ql.tracked_files(ql.DEFAULT_GLOBS.split(), [])
    return [
        (f.path, f.line, f.target)
        for f in ql.find_dead_links(Path("."), tracked, ql.parse_extensions(exts))
    ]


def test_dead_link_is_flagged_with_its_line(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": "# A\n\nSee [B](b.qmd) and [gone](old-name.qmd).\n",
        "b.qmd": "# B\n",
    })
    assert got == [("a.qmd", 3, "old-name.qmd")]


def test_link_split_across_lines_reports_the_target_line(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": "# A\n\nSee [the old\nname](old.qmd#sec) here.\n",
    })
    assert got == [("a.qmd", 4, "old.qmd#sec")]


def test_code_and_comments_are_not_links(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": (
            "# A\n\n"
            "```markdown\n[x](gone1.qmd)\n```\n\n"
            "~~~~\n[x](gone2.qmd)\n~~~~\n\n"
            "Inline `[x](gone3.qmd)` span.\n\n"
            "<!-- [x](gone4.qmd) -->\n"
            "<!--\n[x](gone5.qmd)\n-->\n"
            "Real [x](gone6.qmd).\n"
        ),
    })
    assert got == [("a.qmd", 17, "gone6.qmd")]


def test_a_shorter_fence_does_not_close_a_longer_one(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": "````\n```\n[x](inside.qmd)\n```\n````\n[x](outside.qmd)\n",
    })
    assert got == [("a.qmd", 6, "outside.qmd")]


def test_urls_anchors_and_other_file_types_are_not_checked(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": (
            "[u](https://example.org/x.qmd) [m](mailto:a@example.org) "  # phi-allow
            "[h](#sec) [p](//cdn.example.org/x.md) ![i](missing.png) "
            "[s]({{< meta page >}}.qmd) [d](folder/)\n"
        ),
    })
    assert got == []


def test_reference_definitions_html_and_percent_encoding(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": (
            "[ref]: gone-ref.qmd\n"
            "[^1]: A footnote, not a link to.qmd\n"
            '<a href="gone-html.qmd">x</a>\n'
            "[ok](my%20page.qmd) [angle](<my page.qmd>)\n"
        ),
        "my page.qmd": "# p\n",
    })
    assert got == [("a.qmd", 1, "gone-ref.qmd"), ("a.qmd", 3, "gone-html.qmd")]


def test_subfile_links_resolve_from_the_including_page(tmp_path, monkeypatch):
    # The layout Morrison-Lab/mln uses: chapters include
    # _subfiles/<chapter>/_x.qmd, whose links are written relative to the
    # chapter, not to the subfile.
    got = _findings(tmp_path, monkeypatch, {
        "chapters/a.qmd": "{{< include _subfiles/a/_x.qmd >}}\n",
        "chapters/b.qmd": "# B\n",
        "chapters/_subfiles/a/_x.qmd": "See [B](b.qmd) and [gone](gone.qmd).\n",
    })
    assert got == [("chapters/_subfiles/a/_x.qmd", 1, "gone.qmd")]


def test_nested_includes_resolve_from_every_ancestor(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "chapters/a.qmd": "{{< include _sub/_outer.qmd >}}\n",
        "chapters/_sub/_outer.qmd": "{{< include _inner.qmd >}}\n",
        "chapters/_sub/_inner.qmd": "[B](b.qmd)\n",
        "chapters/b.qmd": "# B\n",
    })
    assert got == []


def test_nested_include_links_resolve_from_the_top_level_page_only(tmp_path, monkeypatch):
    # Quarto resolves everything an included file contains from the
    # top-level page's directory, so a target that exists only beside the
    # intermediate subfile is still dead.
    got = _findings(tmp_path, monkeypatch, {
        "chapters/a.qmd": "{{< include _sub/_outer.qmd >}}\n",
        "chapters/_sub/_outer.qmd": "{{< include _sub/_inner.qmd >}}\n",
        "chapters/_sub/_inner.qmd": "[B](b.qmd)\n",
        "chapters/_sub/b.qmd": "# only beside the subfiles\n",
    })
    assert got == [("chapters/_sub/_inner.qmd", 1, "b.qmd")]


def test_a_subfile_must_resolve_from_every_page_that_includes_it(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a/page.qmd": "{{< include ../_shared/_x.qmd >}}\n",
        "b/page.qmd": "{{< include ../_shared/_x.qmd >}}\n",
        "_shared/_x.qmd": "[sibling](sibling.qmd)\n",
        "a/sibling.qmd": "# only under a/\n",
    })
    assert got == [("_shared/_x.qmd", 1, "sibling.qmd")]


def test_quoted_include_path_with_a_space(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "chapters/a.qmd": '{{< include "_sub/my part.qmd" >}}\n',
        "chapters/_sub/my part.qmd": "[gone](gone.qmd)\n",
    })
    assert got == [("chapters/_sub/my part.qmd", 1, "gone.qmd")]


def test_indented_code_block_is_not_prose_but_a_list_continuation_is(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": (
            "Some text.\n"
            "\n"
            "    Example: [x](in-code.qmd)\n"
            "\n"
            "    still code [y](in-code-too.qmd)\n"
            "More text.\n"
            "\n"
            "- A list item.\n"
            "\n"
            "    A continuation paragraph [z](in-list.qmd).\n"
        ),
    })
    assert got == [("a.qmd", 10, "in-list.qmd")]


def test_escaped_brackets_and_blockquoted_code_are_not_links(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "a.qmd": (
            "\\[not a link\\](gone1.qmd)\n"
            "> Example:\n"
            "> ```markdown\n"
            "> [x](gone2.qmd)\n"
            "> ```\n"
            "[a link ending in an escaped backslash\\\\](gone3.qmd)\n"
            "> A quoted [real link](gone4.qmd).\n"
        ),
    })
    assert got == [("a.qmd", 6, "gone3.qmd"), ("a.qmd", 7, "gone4.qmd")]


def test_unincluded_partial_is_skipped_and_escaped_include_includes_nothing(tmp_path, monkeypatch):
    # An outtake kept for reuse: its include is escaped and commented out,
    # so Quarto never renders it and its links resolve from nowhere.
    got = _findings(tmp_path, monkeypatch, {
        "chapters/a.qmd": "<!-- {{</* include outtakes/_old.qmd */>}} -->\n",
        "chapters/outtakes/_old.qmd": "[B](b.qmd)\n",
        "chapters/b.qmd": "# B\n",
    })
    assert got == []


def test_root_relative_links_resolve_from_the_quarto_project(tmp_path, monkeypatch):
    got = _findings(tmp_path, monkeypatch, {
        "site/_quarto.yml": "project:\n  type: website\n",
        "site/about.qmd": "# About\n",
        "site/docs/page.qmd": "[a](/about.qmd) [b](/gone.qmd)\n",
    })
    assert got == [("site/docs/page.qmd", 1, "/gone.qmd")]


def test_target_extensions_limit_what_is_checked(tmp_path, monkeypatch):
    files = {"a.qmd": "[x](gone.md) [y](gone.qmd)\n"}
    got = _findings(tmp_path, monkeypatch, files, exts=".qmd")
    assert got == [("a.qmd", 1, "gone.qmd")]


def test_long_line_is_linear(tmp_path, monkeypatch):
    blob = "![](data:image/png;base64," + "A" * 2_000_000 + ")\n"
    start = time.monotonic()
    got = _findings(tmp_path, monkeypatch, {"a.qmd": blob + "[x](gone.qmd)\n"})
    assert got == [("a.qmd", 2, "gone.qmd")]
    assert time.monotonic() - start < 20


# -- the env var -> main() -> exit code path --------------------------------

def _main(tmp_path, monkeypatch, files, **env) -> int:
    _repo(tmp_path, files)
    monkeypatch.chdir(tmp_path)
    for key in ("QL_GLOBS", "QL_TARGET_EXTENSIONS", "QL_PATHS_IGNORE", "QL_FAIL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return ql.main()


_DEAD = {"a.qmd": "[x](gone.qmd)\n", "vendor/b.md": "[y](gone.md)\n"}


def test_main_fails_on_a_finding_by_default(tmp_path, monkeypatch, capsys):
    assert _main(tmp_path, monkeypatch, _DEAD) == 1
    out = capsys.readouterr().out
    assert "::error file=a.qmd,line=1," in out
    assert "Examined 2 file(s)" in out


@pytest.mark.parametrize("value,expected", [("false", 0), (" FALSE ", 0), ("yes", 1), ("true", 1)])
def test_fail_is_read_fail_closed(tmp_path, monkeypatch, value, expected):
    assert _main(tmp_path, monkeypatch, _DEAD, QL_FAIL=value) == expected


def test_paths_ignore_skips_source_files(tmp_path, monkeypatch, capsys):
    assert _main(tmp_path, monkeypatch, _DEAD, QL_PATHS_IGNORE="a.qmd, vendor") == 0
    assert "Examined 0 file(s)" in capsys.readouterr().out


def test_clean_tree_passes(tmp_path, monkeypatch):
    assert _main(tmp_path, monkeypatch, {"a.qmd": "[b](b.qmd)\n", "b.qmd": "# b\n"}) == 0


# -- defaults declared in three places must agree ---------------------------

# Parsed with a regex rather than a YAML library on purpose: the selftest job
# installs only pytest.

def _declared_default(path: Path, name: str) -> str:
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f"{name}:":
            indent = len(line) - len(line.lstrip())
            for body in lines[i + 1:]:
                if body.strip() and len(body) - len(body.lstrip()) <= indent:
                    break
                if body.strip().startswith("default:"):
                    return body.split("default:", 1)[1].strip().strip("'")
    raise AssertionError(f"no default for {name} in {path}")


@pytest.mark.parametrize("path", [_ACTION_YML, _WORKFLOW_YML])
@pytest.mark.parametrize("name,script_default", [
    ("globs", ql.DEFAULT_GLOBS),
    ("target-extensions", ql.DEFAULT_TARGET_EXTENSIONS),
])
def test_declared_defaults_match_the_script(path, name, script_default):
    assert _declared_default(path, name) == script_default


@pytest.mark.parametrize("path", [_ACTION_YML, _WORKFLOW_YML])
def test_declared_fail_default_is_blocking(path):
    assert _declared_default(path, "fail") == "true"
