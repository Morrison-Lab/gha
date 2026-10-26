"""Unit tests for check-exercise-before-result (gha#1242).

A result div (thm, lem, cor, prp) that is added or edited needs an exercise and
its solution just before it (Ezra, 2026-10-26).

The script's name has a hyphen, so load it by path.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_exercise_before_result", _DIR / "check-exercise-before-result.py"
)
assert _spec is not None and _spec.loader is not None
ceb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ceb)


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def bad(root: Path, chapter: str = "ch.qmd"):
    ceb._CACHE.clear()
    blocks = ceb.blocks_of(str(root / chapter), str(root))
    return [(Path(b.path).name, b.kind) for b in ceb.unpaired_results(blocks, ceb._lines_of)]


def chapter(*lines: str) -> str:
    return "\n".join(lines) + "\n"


@pytest.fixture
def tree(tmp_path):
    for kind in ("exr", "sol", "thm", "lem", "exm", "rem"):
        write(tmp_path, f"_sub/_{kind}-a.qmd", f"::: {{#{kind}-a}}\nBody.\n:::\n")
    return tmp_path


def test_a_result_after_exercise_and_solution_passes(tree):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_exr-a.qmd >}}", "", "{{< slidebreak >}}", "",
        "{{< include _sub/_sol-a.qmd >}}", "", "{{< slidebreak >}}", "",
        "{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == []


def test_a_result_with_no_pair_is_flagged(tree):
    write(tree, "ch.qmd", chapter("{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == [("_thm-a.qmd", "thm")]


def test_an_example_between_solution_and_result_breaks_adjacency(tree):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_exr-a.qmd >}}", "{{< include _sub/_sol-a.qmd >}}",
        "{{< include _sub/_exm-a.qmd >}}", "{{< include _sub/_lem-a.qmd >}}"))
    assert bad(tree) == [("_lem-a.qmd", "lem")]


def test_a_heading_between_solution_and_result_breaks_adjacency(tree):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_exr-a.qmd >}}", "{{< include _sub/_sol-a.qmd >}}",
        "## Next", "{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == [("_thm-a.qmd", "thm")]


def test_a_solution_without_an_exercise_is_flagged(tree):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_sol-a.qmd >}}", "{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == [("_thm-a.qmd", "thm")]


def test_only_the_last_pair_counts(tree):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_exr-a.qmd >}}", "{{< include _sub/_sol-a.qmd >}}",
        "{{< include _sub/_exr-a.qmd >}}", "{{< include _sub/_sol-a.qmd >}}",
        "{{< include _sub/_cor-a.qmd >}}"))
    assert bad(tree) == []


def test_quoted_include_paths_are_followed(tree):
    write(tree, "ch.qmd", chapter(
        '{{< include "_sub/_exr-a.qmd" >}}', "{{< include '_sub/_sol-a.qmd' >}}",
        "{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == []


def test_an_id_inside_a_quoted_attribute_is_not_the_divs_kind(tree):
    write(tree, "ch.qmd", chapter(
        '::: {.callout title="See #exr-1" #thm-x}', "Claim.", ":::"))
    assert bad(tree) == [("ch.qmd", "thm")]


def test_an_indented_heading_breaks_adjacency(tree):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_exr-a.qmd >}}", "{{< include _sub/_sol-a.qmd >}}",
        "  ## Next", "{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == [("_thm-a.qmd", "thm")]


def test_an_unclosed_comment_marker_in_a_fence_hides_nothing(tree):
    write(tree, "ch.qmd", chapter(
        "```html", "<!--", "```", "::: {#thm-x}", "Claim.", ":::", "<!-- note -->"))
    assert bad(tree) == [("ch.qmd", "thm")]


def test_inline_divs_count_as_blocks(tree):
    write(tree, "ch.qmd", chapter(
        "::: {#exr-x}", "Show it.", ":::", "", "::: {#sol-x}", "Done.", ":::", "",
        "::: {#thm-x}", "Claim.", ":::"))
    assert bad(tree) == []
    write(tree, "ch.qmd", chapter("::: {#thm-x}", "Claim.", ":::"))
    assert bad(tree, "ch.qmd")[0][1] == "thm"


def test_allow_marker_exempts_a_result(tree):
    write(tree, "_sub/_thm-a.qmd",
          "::: {#thm-a}\n<!-- check-exercise-before-result: allow -->\nBody.\n:::\n")
    write(tree, "ch.qmd", chapter("{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == []


def test_commented_out_includes_are_ignored(tree):
    write(tree, "ch.qmd", chapter(
        "<!-- {{< include _sub/_exr-a.qmd >}} -->", "{{< include _sub/_sol-a.qmd >}}",
        "{{< include _sub/_thm-a.qmd >}}"))
    assert bad(tree) == [("_thm-a.qmd", "thm")]


def test_code_fences_are_not_read(tree):
    write(tree, "ch.qmd", chapter(
        "```", "::: {#thm-x}", ":::", "```"))
    assert bad(tree) == []


def test_defaults_agree_between_script_and_action():
    action = (_DIR / "action.yml").read_text(encoding="utf-8")
    assert ceb._DEFAULT_FAIL is True
    assert "default: 'true'" in action.split("fail:")[1]
    assert ceb.DEFAULT_GLOBS == "*.qmd"
    workflow = (_DIR.parent / ".github" / "workflows"
                / "check-exercise-before-result.yml").read_text(encoding="utf-8")
    assert "default: true" in workflow.split("fail:")[1]
    assert "default: '*.qmd'" in workflow.split("globs:")[1]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                    "-c", "user.email=t@t", *args], check=True,
                   stdout=subprocess.DEVNULL)


@pytest.fixture
def repo(tree, monkeypatch):
    write(tree, "ch.qmd", chapter(
        "{{< include _sub/_exr-a.qmd >}}", "{{< include _sub/_sol-a.qmd >}}",
        "{{< include _sub/_thm-a.qmd >}}", "{{< include _sub/_lem-a.qmd >}}"))
    _git(tree, "init", "-q", "-b", "main")
    _git(tree, "add", ".")
    _git(tree, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tree)
    ceb._CACHE.clear()
    return tree


def test_run_check_ignores_an_unchanged_unpaired_result(repo):
    # _lem-a has no pair, but the PR does not touch it.
    (repo / "_sub" / "_thm-a.qmd").write_text("::: {#thm-a}\nEdited.\n:::\n")
    ceb._CACHE.clear()
    report = ceb.run_check("HEAD", ["*.qmd"], [], False)
    assert report.findings == []


def test_run_check_flags_an_edited_unpaired_result(repo):
    (repo / "_sub" / "_lem-a.qmd").write_text("::: {#lem-a}\nEdited.\n:::\n")
    ceb._CACHE.clear()
    report = ceb.run_check("HEAD", ["*.qmd"], [], False)
    assert [(Path(f.path).name, f.kind) for f in report.findings] == [("_lem-a.qmd", "lem")]


def test_run_check_whole_tree_reads_every_result(repo):
    report = ceb.run_check("", ["*.qmd"], [], True)
    assert [(Path(f.path).name, f.kind) for f in report.findings] == [("_lem-a.qmd", "lem")]


def test_run_check_skips_an_unresolvable_base(repo):
    assert ceb.run_check("no-such-ref", ["*.qmd"], [], False).skipped


def test_run_check_skips_an_empty_base(repo):
    assert ceb.run_check("", ["*.qmd"], [], False).skipped
