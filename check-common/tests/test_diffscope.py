"""Unit tests for check-common/diffscope.py (gha#1856)."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diffscope  # noqa: E402


DIFF = """\
diff --git a/a.qmd b/a.qmd
--- a/a.qmd
+++ b/a.qmd
@@ -2 +2,2 @@
-old text
+new text
+++ not a header
"""


def test_parse_diff_reads_added_lines_and_deleted_texts():
    added, deleted = diffscope.parse_diff(DIFF)
    assert added == {"a.qmd": {2: "new text", 3: "++ not a header"}}
    assert deleted == {"old text"}


def test_a_deleted_file_adds_nothing():
    diff = "--- a/gone.qmd\n+++ /dev/null\n@@ -1 +0,0 @@\n-bye\n"
    added, deleted = diffscope.parse_diff(diff)
    assert added == {}
    assert deleted == {"bye"}


def test_parse_renames_keeps_only_renames():
    status = "R100\told.qmd\tnew.qmd\nM\tother.qmd\n"
    assert diffscope.parse_renames(status) == [("old.qmd", "new.qmd")]


def test_an_include_that_follows_a_rename_is_moved():
    deleted = {"{{< include _old.qmd >}}"}
    renames = [("ch/_old.qmd", "ch/_new.qmd")]
    assert diffscope.is_repointed_include("{{< include _new.qmd >}}", deleted, renames)
    assert not diffscope.is_repointed_include("{{< include _other.qmd >}}", deleted, renames)


def test_an_include_needs_a_matching_deleted_line():
    renames = [("ch/_old.qmd", "ch/_new.qmd")]
    assert not diffscope.is_repointed_include("{{< include _new.qmd >}}", set(), renames)


def test_globs_and_bare_directories_ignore_paths():
    ignores = diffscope.compile_ignores(["vendor", "**/*.md"])
    assert diffscope.ignored("vendor/x.qmd", ignores)
    assert diffscope.ignored("docs/deep/a.md", ignores)
    assert diffscope.ignored("a.md", ignores)
    assert not diffscope.ignored("vendors/x.qmd", ignores)
    assert not diffscope.ignored("a.qmd", ignores)


def test_split_list_takes_commas_and_newlines():
    assert diffscope.split_list(" a, b\n\nc ,") == ["a", "b", "c"]


def test_env_flag(monkeypatch):
    monkeypatch.delenv("DS_FLAG", raising=False)
    assert diffscope.env_flag("DS_FLAG", True) is True
    monkeypatch.setenv("DS_FLAG", " Yes ")
    assert diffscope.env_flag("DS_FLAG", False) is True
    monkeypatch.setenv("DS_FLAG", "false")
    assert diffscope.env_flag("DS_FLAG", True) is False


def test_read_lines(tmp_path):
    page = tmp_path / "p.qmd"
    page.write_text("one\ntwo\n", encoding="utf-8")
    assert diffscope.read_lines(str(page)) == ["one", "two"]
    assert diffscope.read_lines(str(tmp_path / "missing.qmd")) is None


def test_run_git_returns_none_on_failure(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    assert diffscope.run_git(["rev-parse", "--is-inside-work-tree"]) == "true\n"
    assert diffscope.run_git(["rev-parse", "no-such-ref"]) is None
