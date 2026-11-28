"""Tests for check-pr-size (gha#1188). Fixture repos are built in tmp_path."""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPT = ROOT / "check-pr-size.py"
spec = importlib.util.spec_from_file_location("check_pr_size", SCRIPT)
cps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cps)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",  # phi-allow
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})  # phi-allow


def make_repo(tmp_path, files):
    """Commit a base, then add `files` ({path: line count}) on top."""
    git(tmp_path, "init", "-q")
    (tmp_path / "base.txt").write_text("base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    for path, n in files.items():
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(f"line {i}\n" for i in range(n)))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "change")
    return tmp_path


def run(repo, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("PRS_")}
    # The fixtures are sized for caps of 10 files and 300 lines, so pin those
    # rather than track the default, which
    # test_defaults_agree_across_script_action_and_workflow pins.
    e.update({"PRS_BASE_REF": "HEAD^1", "PRS_MAX_FILES": "10", "PRS_MAX_LINES": "300"})
    e.update(env)
    p = subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, env=e,
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def test_small_pr_passes(tmp_path):
    repo = make_repo(tmp_path, {"a.qmd": 20, "b.qmd": 20})
    code, out = run(repo)
    assert code == 0
    assert "2 file(s), 40 changed line(s)" in out


def test_sweep_over_file_cap_fails(tmp_path):
    """Regression: a pds#244-style sweep touching many files, a few lines each."""
    repo = make_repo(tmp_path, {f"chapters/c{i}.qmd": 2 for i in range(25)})
    code, out = run(repo)
    assert code == 1
    assert "25 files changed (cap 10)" in out
    assert "minimal batches" in out


def test_over_line_cap_fails(tmp_path):
    repo = make_repo(tmp_path, {"big.qmd": 500})
    code, out = run(repo)
    assert code == 1
    assert "500 lines changed (cap 300)" in out


def test_exactly_at_cap_passes(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 30 for i in range(10)})
    code, _ = run(repo)
    assert code == 0


def test_one_over_cap_fails(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 1 for i in range(11)})
    code, _ = run(repo)
    assert code == 1


def test_builtin_ignores_are_not_counted(tmp_path):
    files = {f"_freeze/p{i}/x.json": 100 for i in range(30)}
    files["renv.lock"] = 900
    files["a.qmd"] = 5
    repo = make_repo(tmp_path, files)
    code, out = run(repo)
    assert code == 0
    assert "1 file(s), 5 changed line(s)" in out


def test_paths_ignore_exempts_a_directory(tmp_path):
    repo = make_repo(tmp_path, {f"gen/g{i}.qmd": 5 for i in range(20)})
    assert run(repo)[0] == 1
    assert run(repo, PRS_PATHS_IGNORE="gen/**")[0] == 0


BY_MODULE = {"c/_sub/definitions/_by-module.qmd": 270,
             "c/_sub/results/_by-module.qmd": 270, "c/x.qmd": 10}


@pytest.mark.parametrize("attr, counted", [
    ("linguist-generated", False),
    ("linguist-generated=true", False),
    ("linguist-generated=false", True),
    ("-linguist-generated", True),
    (None, True),
])
def test_linguist_generated_paths_are_not_counted(tmp_path, attr, counted):
    """lds#2355 shape: two committed generator outputs plus a small hand edit (gha#1959)."""
    if attr is not None:
        (tmp_path / ".gitattributes").write_text(f"**/_by-module.qmd {attr}\n")
    repo = make_repo(tmp_path, BY_MODULE)
    code, out = run(repo)
    if counted:
        assert code == 1
        assert "550 lines changed (cap 300)" in out
    else:
        assert code == 0
        assert "1 file(s), 10 changed line(s)" in out


def test_new_figure_subfile_lines_are_free_but_files_count(tmp_path):
    repo = make_repo(tmp_path, {"c/_fig-a-3d.qmd": 250, "c/_fig-b-3d.qmd": 250, "c/x.qmd": 10})
    code, out = run(repo)
    assert code == 0, out
    assert "3 file(s), 10 changed line(s)" in out


def test_new_figure_subfiles_still_count_toward_the_file_cap(tmp_path):
    repo = make_repo(tmp_path, {f"c/_fig-{i}.qmd": 5 for i in range(11)})
    code, _ = run(repo)
    assert code == 1


def test_edited_figure_subfile_lines_still_count(tmp_path):
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "_fig-a.qmd").write_text("old\n")
    repo = make_repo(tmp_path, {"c/_fig-a.qmd": 400})
    code, out = run(repo)
    assert code == 1, out


def test_exempt_label_lifts_the_cap(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_EXEMPT="true")
    assert code == 0
    assert "exemption label" in out


def test_fail_false_warns_without_blocking(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_FAIL="false")
    assert code == 0
    assert "::warning::This PR is too large" in out


def test_no_base_ref_skips(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_BASE_REF="")
    assert code == 0
    assert "skipping" in out


def test_unresolvable_base_ref_skips(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(40)})
    code, out = run(repo, PRS_BASE_REF="no-such-ref")
    assert code == 0
    assert "skipping" in out


def test_invalid_cap_is_an_error(tmp_path):
    repo = make_repo(tmp_path, {"a.qmd": 1})
    code, out = run(repo, PRS_MAX_FILES="ten")
    assert code == 2
    assert "PRS_MAX_FILES" in out


def test_custom_caps(tmp_path):
    repo = make_repo(tmp_path, {f"f{i}.qmd": 2 for i in range(5)})
    assert run(repo, PRS_MAX_FILES="4")[0] == 1
    assert run(repo, PRS_MAX_FILES="5")[0] == 0


def test_binary_file_counts_as_a_file_with_no_lines(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "base.txt").write_text("base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "bin")
    code, out = run(tmp_path)
    assert code == 0
    assert "1 file(s), 0 changed line(s)" in out


def _rename_repo(tmp_path, edit):
    git(tmp_path, "init", "-q")
    for i in range(12):
        (tmp_path / f"old{i}.qmd").write_text("".join(f"line {j} of {i}\n" for j in range(10)))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    for i in range(12):
        git(tmp_path, "mv", f"old{i}.qmd", f"new{i}.qmd")
        if edit:
            with open(tmp_path / f"new{i}.qmd", "a") as f:
                f.write("one more\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "rename")
    return tmp_path


def test_pure_renames_do_not_count_toward_the_file_cap(tmp_path):
    code, out = run(_rename_repo(tmp_path, edit=False))
    assert code == 0, out
    assert "0 file(s)" in out


def test_renames_with_edits_still_count(tmp_path):
    code, out = run(_rename_repo(tmp_path, edit=True))
    assert code == 1, out


def test_body_saying_mechanical_content_identical_exempts(tmp_path):
    repo = make_repo(tmp_path, {f"chapters/c{i}.qmd": 2 for i in range(25)})
    assert run(repo)[0] == 1
    code, out = run(repo, PRS_PR_BODY="Split the page.\n\nMechanical, content-identical.")
    assert code == 0, out
    assert run(repo, PRS_PR_BODY="mechanical but reworded")[0] == 1


def _split_repo(tmp_path, pages, extra=None, blanks=False):
    """`pages` pages of 40 distinct lines each, then every page split in two.

    The second half of each page moves unchanged into a new page. `extra`
    (a line of text) is appended to the first page's new half, as a reworded
    or new line would be. With `blanks`, every other line is a blank line or a
    `:::` fence, as in a real page.
    """
    git(tmp_path, "init", "-q")
    for i in range(pages):
        rows = [f"page {i} sentence {j}." if j % 2 or not blanks else ("" if j % 4 else ":::")
                for j in range(40)]
        (tmp_path / f"p{i}.qmd").write_text("".join(r + "\n" for r in rows))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    for i in range(pages):
        lines = (tmp_path / f"p{i}.qmd").read_text().splitlines(keepends=True)
        (tmp_path / f"p{i}.qmd").write_text("".join(lines[:20]))
        moved = "".join(lines[20:]) + (extra + "\n" if extra and i == 0 else "")
        (tmp_path / f"q{i}.qmd").write_text(moved)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "split")
    return tmp_path


def test_pure_movement_is_exempt_at_any_size(tmp_path):
    """Ezra, 2026-11-28: "pure movement prs are exempt from the cap"."""
    code, out = run(_split_repo(tmp_path, 20))
    assert code == 0, out
    assert "0 file(s), 0 changed line(s)" in out


def test_movement_plus_a_new_line_counts_only_the_new_line(tmp_path):
    code, out = run(_split_repo(tmp_path, 20, extra="A sentence nobody wrote before."))
    assert code == 0, out
    assert "1 file(s), 1 changed line(s)" in out


def test_pure_movement_with_blank_lines_and_fences_is_exempt(tmp_path):
    """The blank lines and fences of a moved block move with it."""
    code, out = run(_split_repo(tmp_path, 20, blanks=True))
    assert code == 0, out
    assert "0 file(s), 0 changed line(s)" in out


def test_short_lines_are_not_in_the_move_budget(tmp_path):
    texts = {"a.qmd": (["}", ""], ["}", ""])}
    assert not cps.move_budget(texts)


def test_short_lines_count_outside_a_moving_file():
    """A file with a new substantive line counts its short lines too, and a
    file of only short-line edits is not a moving file."""
    texts = {
        "src.qmd": ([], ["a moved sentence.", ""]),
        "dst.qmd": (["a moved sentence.", ""], []),
        "edit.qmd": (["a sentence nobody wrote.", ""], [""]),
        "blank.qmd": ([""], [""]),
    }
    assert cps.unmoved_counts(texts) == {"src.qmd": 0, "dst.qmd": 0, "edit.qmd": 3, "blank.qmd": 2}


def test_moved_lines_into_an_ignored_path_still_count(tmp_path):
    """An ignored path's lines cannot pay for a counted file's lines."""
    rows = [("a.qmd", 1), ("x.lock", 1)]
    texts = {"a.qmd": ([], ["long enough line"]), "x.lock": (["long enough line"], [])}
    regexes = cps.diffscope.compile_ignores(cps.BUILTIN_IGNORE)
    files, lines, _ = cps.measure(rows, regexes, texts=texts)
    assert (files, lines) == (1, 1)


def test_changed_texts_keys_a_deleted_file_on_its_old_path():
    diff = ("diff --git a/gone.qmd b/gone.qmd\ndeleted file mode 100644\n--- a/gone.qmd\n"
            "+++ /dev/null\n@@ -1,2 +0,0 @@\n-first line\n--- a dashed line\n")
    assert cps.changed_texts(diff) == {"gone.qmd": ([], ["first line", "-- a dashed line"])}


def test_parse_numstat_handles_renames():
    rows = cps.parse_numstat("3\t1\t\0dir/old.qmd\0dir/new.qmd\0-\t-\timg.bin\0")
    assert rows == [("dir/new.qmd", 4), ("img.bin", 0)]


def test_glob_to_regex_recursive():
    r = cps.diffscope.glob_to_regex("_freeze/**")
    assert r.match("_freeze/a/b/c.json")
    assert not r.match("src/_freeze/a")
    r2 = cps.diffscope.glob_to_regex("**/*.png")
    assert r2.match("a/b/c.png") and r2.match("c.png")


def test_paths_ignore_bare_directory_skips_its_contents(tmp_path):
    repo = make_repo(tmp_path, {f"gen/g{i}.qmd": 5 for i in range(20)})
    assert run(repo, PRS_PATHS_IGNORE="gen")[0] == 0


def test_name_with_a_quote_is_matched_unquoted(tmp_path):
    # git quotes such a name in a plain numstat listing (gha#1923), so the
    # built-in `**/*.png` ignore used to miss it and count the file.
    repo = make_repo(tmp_path, {'img/say"hi.png': 1, "a.qmd": 1})
    code, out = run(repo, PRS_MAX_FILES="1")
    assert code == 0, out
    assert "1 file(s)" in out


def test_quoted_rename_counts_as_a_pure_rename(tmp_path):
    repo = make_repo(tmp_path, {'d/say"hi.qmd': 3})
    (tmp_path / "e").mkdir()
    git(tmp_path, "mv", 'd/say"hi.qmd', 'e/say"hi.qmd')
    git(tmp_path, "commit", "-q", "-m", "rename")
    code, out = run(repo)
    assert code == 0, out
    assert "0 file(s)" in out


def _default(path, key):
    """First `default:` after the line `<key>:` (a line scan, no YAML library)."""
    lines = path.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == f"{key}:")
    for line in lines[start + 1:]:
        m = re.match(r"\s+default: '(\d+)'", line)
        if m:
            return m.group(1)
        assert not re.match(r"\s{0,6}[a-z-]+:\s*$", line) or line.strip().startswith(("description", "type")), \
            f"no default for {key} in {path}"
    raise AssertionError(f"{key} default not found in {path}")


@pytest.mark.parametrize("name,expected", [("max-files", cps.DEFAULT_MAX_FILES),
                                           ("max-lines", cps.DEFAULT_MAX_LINES)])
def test_defaults_agree_across_script_action_and_workflow(name, expected):
    """The gha#303 precedent: one default, declared three times, must agree."""
    action = ROOT / "action.yml"
    workflow = ROOT.parent / ".github" / "workflows" / "check-pr-size.yml"
    assert int(_default(action, name)) == expected
    assert int(_default(workflow, name)) == expected


# A pure token substitution is exempt (gha#2050).

def _substitution_repo(tmp_path, edit):
    """25 pages using `\\beta`, then `edit(i, text)` rewrites page i."""
    git(tmp_path, "init", "-q")
    for i in range(25):
        (tmp_path / f"p{i}.qmd").write_text(
            f"Page {i} on topic{i}.\n\nThe slope $\\beta_x$ is fixed.\nUnchanged line.\n"
            "Again $\\beta$.\nCheck x == y and flag = true and n = 3.\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    for i in range(25):
        p = tmp_path / f"p{i}.qmd"
        p.write_text(edit(i, p.read_text()))
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "substitute")
    return tmp_path


def test_pure_substitution_exempts_and_prints_the_map(tmp_path):
    repo = _substitution_repo(tmp_path, lambda i, t: t.replace("\\beta", "\\coef"))
    code, out = run(repo)
    assert code == 0, out
    assert "pure substitution" in out
    assert "'\\\\beta' -> '\\\\coef'" in out


def test_substitution_plus_an_inserted_word_is_measured(tmp_path):
    def edit(i, t):
        t = t.replace("\\beta", "\\coef")
        return t.replace("is fixed", "is not fixed") if i == 7 else t
    code, out = run(_substitution_repo(tmp_path, edit))
    assert code == 1, out


def test_substitution_plus_a_rewritten_line_is_measured(tmp_path):
    def edit(i, t):
        t = t.replace("\\beta", "\\coef")
        return t.replace("Unchanged line.", "Something else entirely") if i == 5 else t
    code, out = run(_substitution_repo(tmp_path, edit))
    assert code == 1, out


@pytest.mark.parametrize("old,new", [
    ("x == y", "x != y"),          # punctuation changes meaning
    ("flag = true", "flag = false"),  # a logic word
    ("n = 3", "n = 4"),            # a number
    ("x == y", "x == y.z"),        # a token inserted, not swapped
])
def test_substitution_that_changes_meaning_is_measured(tmp_path, old, new):
    repo = _substitution_repo(tmp_path, lambda i, t: t.replace(old, new))
    code, out = run(repo)
    assert code == 1, out


def test_hunks_strip_the_tab_git_adds_after_a_name_with_a_space():
    diff = ("diff --git a/my page.qmd b/my page.qmd\n--- a/my page.qmd\t\n"
            "+++ b/my page.qmd\t\n@@ -1 +1 @@\n-old\n+new\n")
    assert [p for p, _, _ in cps._hunks(diff)] == ["my page.qmd"]
    assert cps.substitution_map(diff, lambda p: p == "my page.qmd") is None


def test_inconsistent_substitution_is_measured(tmp_path):
    repo = _substitution_repo(
        tmp_path, lambda i, t: t.replace("\\beta", "\\coef" if i else "\\slope"))
    code, out = run(repo)
    assert code == 1, out


def test_substitution_with_an_added_line_is_measured(tmp_path):
    def edit(i, t):
        t = t.replace("\\beta", "\\coef")
        return t + "New sentence.\n" if i == 3 else t
    code, out = run(_substitution_repo(tmp_path, edit))
    assert code == 1, out


def test_more_than_the_substitution_limit_is_measured(tmp_path):
    def renumber(k):
        """`\\beta` everywhere, plus pages below k retopiced: k + 1 entries."""
        def edit(i, t):
            t = t.replace("\\beta", "\\coef")
            return t.replace(f"topic{i}.", f"subject{i}.") if i < k else t
        return edit
    limit = cps.MAX_SUBSTITUTIONS
    (tmp_path / "over").mkdir()
    (tmp_path / "at").mkdir()
    code, out = run(_substitution_repo(tmp_path / "over", renumber(limit)))
    assert code == 1, out
    code, out = run(_substitution_repo(tmp_path / "at", renumber(limit - 1)))
    assert code == 0, out


def test_substitution_map_refuses_binary_and_deleted_files():
    binary = "diff --git a/x.png b/x.png\nBinary files a/x.png and b/x.png differ\n"
    assert cps.substitution_map(binary) is None
    deleted = ("diff --git a/x.qmd b/x.qmd\ndeleted file mode 100644\n--- a/x.qmd\n"
               "+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n")
    assert cps.substitution_map(deleted) is None
    assert cps.substitution_map("") is None


def test_substitution_map_skips_ignored_paths():
    diff = ("diff --git a/a.qmd b/a.qmd\n--- a/a.qmd\n+++ b/a.qmd\n@@ -1 +1 @@\n-old x\n+new x\n"
            "diff --git a/b.lock b/b.lock\n--- a/b.lock\n+++ b/b.lock\n@@ -1 +1,2 @@\n-a\n+b\n+c\n")
    assert cps.substitution_map(diff) is None
    assert cps.substitution_map(diff, lambda p: p.endswith(".lock")) == {"old": "new"}
