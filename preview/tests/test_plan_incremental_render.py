"""Tests for `preview/plan-incremental-render.py`.

The planner may only err toward the full render. Each case that must stay
incremental is paired with one that must not, so a planner that always answers
`full` (or always `incremental`) cannot pass.
"""

import json
import subprocess

from conftest import git, write

FULL = "_quarto*.yml\n_extensions/\nfilters/\n*.scss\n*.bib\ntools/\n"
IGNORE = ".github/\nREADME.md\n"


def commit(work, message):
    git(work, "add", "-A")
    git(work, "commit", "-m", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=work, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def site(work):
    write(work, "_quarto.yml", "project:\n  type: website\n")
    write(work, "chapters/a.qmd", "# A\n\n{{< include _subfiles/a/_part.qmd >}}\n")
    write(work, "chapters/_subfiles/a/_part.qmd", "Part.\n")
    write(work, "chapters/b.qmd", '# B\n\n```{r}\nread.csv("data/b.csv")\n```\n')
    write(work, "chapters/data/b.csv", "x\n1\n")
    write(work, "chapters/c.qmd", "# C\n")
    write(work, "_site/index.html", "x")
    write(work, ".quarto/xref/x", "x")
    return commit(work, "site")


def plan(planner, work, sha, max_pages=15, key=None):
    # As `quarto inspect` does on HEAD: a deleted page is not listed.
    inputs = [str(work / f"chapters/{n}.qmd") for n in "abc"
              if (work / f"chapters/{n}.qmd").exists()]
    inspect = work.parent / f"{work.name}-inspect.json"
    inspect.write_text(json.dumps({"files": {"input": inputs}}), encoding="utf-8")
    pruner = planner._load_pruner()
    mode, reason, pages = planner.decide(
        work, key if key is not None else f"quarto-incremental-Linux--{sha}-1",
        inspect, planner.patterns(FULL), planner.patterns(IGNORE),
        max_pages, pruner,
    )
    return mode, reason, pages


def test_changed_subfile_renders_its_parent_only(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    write(work, "chapters/_subfiles/a/_part.qmd", "Part, revised.\n")
    commit(work, "edit subfile")
    assert plan(planner, work, sha)[::2] == ("incremental", ["chapters/a.qmd"])


def test_changed_data_file_renders_the_page_that_reads_it(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    write(work, "chapters/data/b.csv", "x\n2\n")
    commit(work, "edit data")
    assert plan(planner, work, sha)[::2] == ("incremental", ["chapters/b.qmd"])


def test_ignored_path_renders_nothing(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    write(work, ".github/workflows/x.yml", "a: 1\n")
    commit(work, "ci")
    assert plan(planner, work, sha)[::2] == ("incremental", [])


def test_config_change_forces_full(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    write(work, "_quarto.yml", "project:\n  type: website\n  title: t\n")
    commit(work, "config")
    assert plan(planner, work, sha)[0] == "full"


def test_unreachable_file_forces_full(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    write(work, "images/new.png", "png")
    commit(work, "image nobody references")
    assert plan(planner, work, sha)[0] == "full"


def test_deleted_page_forces_full(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    (work / "chapters/c.qmd").unlink()
    commit(work, "delete page")
    assert plan(planner, work, sha)[0] == "full"


def test_too_many_stale_pages_force_full(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    for name in "abc":
        write(work, f"chapters/{name}.qmd", f"# {name.upper()} edited\n")
    commit(work, "edit all")
    assert plan(planner, work, sha, max_pages=2)[0] == "full"
    assert plan(planner, work, sha, max_pages=3)[0] == "incremental"


def test_missing_cache_or_bad_key_forces_full(planner, repo_factory):
    work = repo_factory(published=None)
    sha = site(work)
    assert plan(planner, work, sha, key="")[0] == "full"
    assert plan(planner, work, sha, key="quarto-incremental-Linux--nosha-1")[0] == "full"
    (work / "_site" / "index.html").unlink()
    (work / "_site").rmdir()
    assert plan(planner, work, sha)[0] == "full"
