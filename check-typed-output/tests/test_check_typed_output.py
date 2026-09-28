"""Unit tests for check-typed-output.

Covers the fence parser and both detectors directly, then the two scopes
(whole tree, and diff-scoped against a base ref) via small throwaway git
repos generated at test time -- nothing committed, so this repo's own tree
never carries a fixture another selftest job would scan.

check-typed-output.py isn't an importable module name (the hyphen), so load
it by path -- the same pattern as check-new-line-breaks' suite.
"""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_MOD_PATH = _DIR / "check-typed-output.py"
_spec = importlib.util.spec_from_file_location("check_typed_output", _MOD_PATH)
assert _spec is not None and _spec.loader is not None, f"Could not load {_MOD_PATH}"
typed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(typed)

FENCE = "```"
DEFAULTS = typed.compile_patterns(typed.DEFAULT_PATTERNS)


def scan(text, patterns=None):
    return typed.scan_text(text, DEFAULTS if patterns is None else patterns)


def lines_of(findings, kind=None):
    return [f.line for f in findings if kind is None or f.kind == kind]


# ── parse_info_string ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "info, expected",
    [
        ("python", ("python", False)),
        (" r", ("r", False)),
        ("julia extra", ("julia", False)),
        ("{r}", ("r", True)),
        ("{python echo=FALSE}", ("python", True)),
        ("{r label, eval=TRUE}", ("r", True)),
        ("{.python}", ("python", False)),
        ('{#lst-x .python lst-cap="A listing"}', ("python", False)),
        ("{.numberLines .python}", ("python", False)),
        ("{.python .numberLines}", ("python", False)),
        ("{.numberLines}", ("numberlines", False)),
        ("{=html}", ("{=raw}", False)),
        ("", ("", False)),
        ("text", ("text", False)),
        ("{ojs}", ("ojs", True)),
    ],
)
def test_parse_info_string(info, expected):
    assert tuple(typed.parse_info_string(info)) == expected


# ── (a) output comments ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "comment",
    ["# -> True", "#-> True", "# => True", "#> [1] 2", "# Output: 3", "# output: 3"],
)
@pytest.mark.parametrize("lang", ["python", "r", "julia", "{r}", "{python}", "{.python}"])
def test_output_comment_flagged_in_code_fences(comment, lang):
    text = f"{FENCE}{lang}\nx = 1\nprint(x)   {comment}\n{FENCE}\n"
    found = scan(text)
    assert lines_of(found, "comment") == [3]


def test_attribute_form_listing_is_scanned():
    # mln's model-selection chapter writes a listing this way; the first
    # parser draft read only a leading class and missed both comments.
    text = f'{FENCE}{{#lst-a .python lst-cap="x"}}\nprint(1)\n# -> 1\n{FENCE}\n'
    assert lines_of(scan(text), "comment") == [3]


@pytest.mark.parametrize(
    "line",
    [
        "#| output: false",       # a Quarto chunk option, not typed output
        "#| echo: false",
        "# maps a -> b, then b => c",  # an arrow later in a comment
        "x <- 1  # set x",
        "y = x >= 2",
    ],
)
def test_ordinary_comments_not_flagged(line):
    text = f"{FENCE}{{r}}\n{line}\n{FENCE}\n"
    assert scan(text) == []


def test_comment_outside_any_fence_not_flagged():
    assert scan("Prose mentioning `# ->` and\n# -> a heading-ish line\n") == []


@pytest.mark.parametrize("lang", ["bash", "sh", "yaml", "{ojs}", "text", ""])
def test_other_languages_not_scanned_for_comments(lang):
    text = f"{FENCE}{lang}\necho hi   # -> hi\n{FENCE}\n"
    assert lines_of(scan(text), "comment") == []


def test_longer_fence_contents_are_not_parsed_as_fences():
    # A four-backtick fence quoting a three-backtick example is one block:
    # its inner "```python" line opens nothing.
    text = "````markdown\n```python\nprint(1)  # -> 1\n```\n````\n"
    assert scan(text) == []


def test_shorter_run_does_not_close_a_longer_fence():
    # A three-backtick line inside a four-backtick fence is content, so the
    # comment after it is still inside the python fence.
    text = "````python\nprint(1)\n```\nprint(2)  # -> 2\n````\n"
    assert lines_of(scan(text), "comment") == [4]


def test_unclosed_output_block_covers_only_real_lines():
    text = f"{FENCE}r\nx\n{FENCE}\n{FENCE}text\n1\n"
    found = scan(text)
    assert [(f.kind, f.lines) for f in found] == [("block", (4, 5))]


def test_fence_inside_list_item_is_scanned():
    text = f"1.  Run it:\n\n    {FENCE}python\n    print(1)  # -> 1\n    {FENCE}\n"
    assert lines_of(scan(text), "comment") == [4]


def test_tilde_fence_needs_tilde_close():
    text = "~~~python\nprint(1)\n```\n# -> 1\n~~~\n"
    assert lines_of(scan(text), "comment") == [4]


def test_custom_patterns_replace_defaults():
    pats = typed.compile_patterns([r"#\s*returns"])
    text = f"{FENCE}python\nf()  # returns 3\ng()  # -> 4\n{FENCE}\n"
    assert lines_of(scan(text, pats), "comment") == [2]


def test_invalid_pattern_is_dropped_with_warning(capsys):
    pats = typed.compile_patterns(["(unclosed", r"#>"])
    assert len(pats) == 1
    assert "Ignoring invalid pattern" in capsys.readouterr().out


# ── (b) hand-written output blocks ───────────────────────────────────────────

@pytest.mark.parametrize("out_info", ["", "text", "output", " text", "{.text}"])
@pytest.mark.parametrize("code", ["python", "r", "julia", "{r}"])
def test_output_block_after_code_flagged(code, out_info):
    text = f"{FENCE}{code}\nprint(1)\n{FENCE}\n\n\n{FENCE}{out_info}\n1\n{FENCE}\n"
    found = scan(text)
    assert lines_of(found, "block") == [6]
    assert found[0].lines == (6, 7, 8)


def test_output_block_directly_adjacent_flagged():
    text = f"{FENCE}r\nx\n{FENCE}\n{FENCE}\n[1] 1\n{FENCE}\n"
    assert lines_of(scan(text), "block") == [4]


def test_prose_between_breaks_the_shape():
    text = f"{FENCE}python\nprint(1)\n{FENCE}\n\nIt prints:\n\n{FENCE}text\n1\n{FENCE}\n"
    assert lines_of(scan(text), "block") == []


@pytest.mark.parametrize("prev", ["bash", "yaml", "text", "", "{ojs}"])
def test_text_block_after_non_code_fence_not_flagged(prev):
    text = f"{FENCE}{prev}\nls\n{FENCE}\n\n{FENCE}text\nout\n{FENCE}\n"
    assert lines_of(scan(text), "block") == []


def test_code_after_code_not_flagged():
    # A second language's version of the same code is not an output block.
    text = f"{FENCE}python\nprint(1)\n{FENCE}\n\n{FENCE}r\nprint(1)\n{FENCE}\n"
    assert scan(text) == []


def test_output_block_body_not_scanned_for_comments():
    text = f"{FENCE}r\nx\n{FENCE}\n{FENCE}text\n#> [1] 1\n{FENCE}\n"
    found = scan(text)
    assert [f.kind for f in found] == ["block"]


# ── defaults agree across the script, action.yml and the workflow ────────────

def _yaml_default(path: Path, name: str) -> str:
    """Read one input's `default:` with a line scan (the tests job installs
    only pytest, not a YAML library)."""
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^\s+{re.escape(name)}:\s*$", line):
            for follow in lines[i + 1:]:
                m = re.match(r"^\s+default:\s*(.*)$", follow)
                if m:
                    return m.group(1).strip().strip("'\"")
                if re.match(r"^\s{0,6}[a-z-]+:\s*$", follow):
                    break
    raise AssertionError(f"{path.name} declares no default for {name}")


_ACTION = _DIR / "action.yml"
_WORKFLOW = _DIR.parent / ".github" / "workflows" / "check-typed-output.yml"


@pytest.mark.parametrize("path", [_ACTION, _WORKFLOW], ids=["action", "workflow"])
def test_defaults_agree_with_script(path):
    assert _yaml_default(path, "globs") == typed._DEFAULT_GLOBS
    assert _yaml_default(path, "fail") == str(typed._DEFAULT_FAIL).lower()
    assert _yaml_default(path, "diff-scoped") == "false"
    assert _yaml_default(path, "patterns") == ""


# ── Scopes, against throwaway git repos ──────────────────────────────────────

def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.invalid")  # phi-allow
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    monkeypatch.chdir(tmp_path)
    return tmp_path


LEGACY = f"# Page\n\n{FENCE}python\nprint(1)  # -> 1\n{FENCE}\n"


def _commit(repo, name, text, msg="c"):
    (repo / name).write_text(text)
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", msg)


def _run(**kw):
    kw.setdefault("patterns", DEFAULTS)
    return typed.run(["*.qmd"], typed.compile_ignores(kw.pop("ignore", [])), **kw)


def test_whole_tree_reports_legacy(repo):
    _commit(repo, "a.qmd", LEGACY)
    _commit(repo, "notes.md", LEGACY)  # outside the default glob
    res = _run()
    assert not res.skipped
    assert [(p, f.line) for p, f in res.findings] == [("a.qmd", 4)]


def test_paths_ignore(repo):
    (repo / "out").mkdir()
    _commit(repo, "out/a.qmd", LEGACY)
    assert _run(ignore=["out"]).findings == []
    assert len(_run().findings) == 1


def test_diff_scoped_ignores_legacy_and_flags_new(repo):
    _commit(repo, "a.qmd", LEGACY)
    _git(repo, "checkout", "-qb", "feature")
    _commit(repo, "a.qmd", LEGACY + f"\n{FENCE}r\nx  #> [1] 2\n{FENCE}\n")
    res = _run(diff_scoped=True, base_ref="main")
    assert [(p, f.line) for p, f in res.findings] == [("a.qmd", 8)]


def test_diff_scoped_flags_block_when_only_its_body_is_added(repo):
    base = f"{FENCE}python\nprint(1)\n{FENCE}\n\n{FENCE}text\n1\n{FENCE}\n"
    _commit(repo, "a.qmd", base)
    _git(repo, "checkout", "-qb", "feature")
    _commit(repo, "a.qmd", base.replace("text\n1\n", "text\n1\n2\n"))
    res = _run(diff_scoped=True, base_ref="main")
    assert [(f.kind, f.line) for _, f in res.findings] == [("block", 5)]


def test_diff_scoped_moved_lines_are_exempt(repo):
    _commit(repo, "a.qmd", LEGACY)
    _git(repo, "checkout", "-qb", "feature")
    (repo / "a.qmd").write_text("# Page\n")
    _commit(repo, "b.qmd", LEGACY)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "split")
    assert _run(diff_scoped=True, base_ref="main").findings == []


def test_diff_scoped_moved_block_is_exempt(repo):
    block = f"{FENCE}python\nprint(1)\n{FENCE}\n\n{FENCE}text\n1\n{FENCE}\n"
    _commit(repo, "a.qmd", block)
    _git(repo, "checkout", "-qb", "feature")
    (repo / "a.qmd").write_text("# Page\n")
    _commit(repo, "b.qmd", block)
    assert _run(diff_scoped=True, base_ref="main").findings == []


def test_line_added_inside_block_not_excused_by_unrelated_deletion(repo):
    # The new `1` inside an untouched output block must not be exempted by a
    # deletion of the same short text in some other file.
    block = f"{FENCE}python\nprint(1)\n{FENCE}\n\n{FENCE}text\nold\n{FENCE}\n"
    _commit(repo, "a.qmd", block)
    _commit(repo, "other.qmd", "x\n1\ny\n")
    _git(repo, "checkout", "-qb", "feature")
    (repo / "other.qmd").write_text("x\ny\n")
    _commit(repo, "a.qmd", block.replace("old\n", "old\n1\n"))
    found = _run(diff_scoped=True, base_ref="main").findings
    assert [(p, f.kind, f.line) for p, f in found] == [("a.qmd", "block", 5)]


def test_new_block_not_excused_by_unrelated_identical_block(repo):
    # An unrelated deleted block with the same short body (`2`) is not a
    # move of the new one: the code fence the new block follows differs.
    _commit(repo, "old.qmd", f"{FENCE}r\nx + 1\n{FENCE}\n\n{FENCE}\n2\n{FENCE}\n")
    _git(repo, "checkout", "-qb", "feature")
    (repo / "old.qmd").write_text("# Gone\n")
    _commit(repo, "b.qmd", f"{FENCE}python\nprint(2)\n{FENCE}\n\n{FENCE}\n2\n{FENCE}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    found = _run(diff_scoped=True, base_ref="main").findings
    assert [(p, f.kind) for p, f in found] == [("b.qmd", "block")]


def test_block_added_under_untouched_code_is_new(repo):
    # Only a span that was itself added can have moved: typing an output
    # block under code that was already there is new, even when the same
    # code and output are deleted from another file in the same diff.
    code = f"{FENCE}r\nx\n{FENCE}\n"
    block = f"\n{FENCE}text\n[1] 1\n{FENCE}\n"
    _commit(repo, "a.qmd", code)
    _commit(repo, "c.qmd", code + block)
    _git(repo, "checkout", "-qb", "feature")
    (repo / "c.qmd").write_text("# Gone\n")
    _commit(repo, "a.qmd", code + block)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    found = _run(diff_scoped=True, base_ref="main").findings
    assert [(p, f.kind) for p, f in found] == [("a.qmd", "block")]


def test_pure_rename_is_a_move(repo):
    _commit(repo, "a.qmd", LEGACY)
    _git(repo, "checkout", "-qb", "feature")
    _git(repo, "mv", "a.qmd", "b.qmd")
    _git(repo, "commit", "-qm", "rename")
    assert _run(diff_scoped=True, base_ref="main").findings == []


def test_deletion_from_ignored_path_is_not_a_move(repo):
    # Content deleted from a path outside the checked population cannot have
    # moved from it, so promoting an outtake reports its typed output.
    (repo / "outtakes").mkdir()
    _commit(repo, "outtakes/old.qmd", LEGACY)
    _git(repo, "checkout", "-qb", "feature")
    _git(repo, "rm", "-q", "outtakes/old.qmd")
    _commit(repo, "new.qmd", LEGACY)
    found = _run(diff_scoped=True, base_ref="main", ignore=["outtakes"]).findings
    assert [p for p, _ in found] == ["new.qmd"]


def test_diff_scoped_copy_is_not_exempt(repo):
    # Only a deletion in the same diff exempts a line: duplicating untouched
    # base content is new writing.
    _commit(repo, "a.qmd", LEGACY)
    _git(repo, "checkout", "-qb", "feature")
    _commit(repo, "b.qmd", LEGACY)
    assert [p for p, _ in _run(diff_scoped=True, base_ref="main").findings] == ["b.qmd"]


def test_diff_scoped_sees_uncommitted_change(repo):
    _commit(repo, "a.qmd", "# Page\n")
    _git(repo, "checkout", "-qb", "feature")
    (repo / "a.qmd").write_text(LEGACY)
    assert len(_run(diff_scoped=True, base_ref="main").findings) == 1


def test_diff_scoped_anchors_on_merge_base(repo):
    # The base branch drops the legacy line after the feature branch forked.
    # Diffing against the base tip would show that line as added on the
    # feature branch; the merge base shows the feature added nothing.
    _commit(repo, "a.qmd", LEGACY)
    _git(repo, "checkout", "-qb", "feature")
    _commit(repo, "b.qmd", "# Other\n")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, "a.qmd", "# Page\n")
    _git(repo, "checkout", "-q", "feature")
    assert _run(diff_scoped=True, base_ref="main").findings == []


def test_diff_scoped_without_base_skips(repo):
    _commit(repo, "a.qmd", LEGACY)
    assert _run(diff_scoped=True, base_ref="").skipped


def test_diff_scoped_unresolvable_base_skips_not_whole_tree(repo):
    _commit(repo, "a.qmd", LEGACY)
    res = _run(diff_scoped=True, base_ref="no-such-ref")
    assert res.skipped and res.findings == []


def test_base_ref_ignored_when_not_diff_scoped(repo):
    _commit(repo, "a.qmd", LEGACY)
    assert len(_run(diff_scoped=False, base_ref="HEAD").findings) == 1


# ── main(): env plumbing and exit codes ──────────────────────────────────────

@pytest.fixture
def env(monkeypatch):
    for name in ("TYPED_OUTPUT_PATTERNS", "TYPED_OUTPUT_GLOBS", "TYPED_OUTPUT_PATHS_IGNORE", "TYPED_OUTPUT_FAIL",
                 "TYPED_OUTPUT_DIFF_SCOPED", "TYPED_OUTPUT_BASE_REF"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_main_warns_by_default(repo, env, capsys):
    _commit(repo, "a.qmd", LEGACY)
    assert typed.main() == 0
    out = capsys.readouterr().out
    assert "::warning file=a.qmd,line=4::" in out
    assert "`# ->`" in out


def test_main_fail_true_exits_1_with_errors(repo, env, capsys):
    _commit(repo, "a.qmd", LEGACY)
    env.setenv("TYPED_OUTPUT_FAIL", "true")
    assert typed.main() == 1
    assert "::error file=a.qmd,line=4::" in capsys.readouterr().out


def test_main_patterns_env_replaces_defaults(repo, env):
    _commit(repo, "a.qmd", LEGACY)
    env.setenv("TYPED_OUTPUT_FAIL", "true")
    env.setenv("TYPED_OUTPUT_PATTERNS", "#\\s*returns\n")
    assert typed.main() == 0


def test_main_diff_scoped_env_reaches_run(repo, env, capsys):
    _commit(repo, "a.qmd", LEGACY)
    env.setenv("TYPED_OUTPUT_FAIL", "true")
    env.setenv("TYPED_OUTPUT_DIFF_SCOPED", "true")
    env.setenv("TYPED_OUTPUT_BASE_REF", "HEAD")
    assert typed.main() == 0
    assert "No typed output found." in capsys.readouterr().out


def test_main_clean_tree_reports_examined_count(repo, env, capsys):
    _commit(repo, "a.qmd", "# Page\n")
    assert typed.main() == 0
    out = capsys.readouterr().out
    assert "Examined 1 file(s)." in out
    assert "No typed output found." in out
