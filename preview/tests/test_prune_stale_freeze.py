"""Tests for `preview/prune-stale-freeze.py`.

The script may only err toward re-executing more. So the cases that matter are
the ones where a stale page would survive: a change reaching a page only
through an include or a data file, and a cache whose source commit cannot be
read. Each is paired with a control that keeps an unrelated page frozen, so a
script that simply wipes everything cannot pass.
"""

import subprocess

from conftest import git, write


def commit(work, message):
    git(work, "add", "-A")
    git(work, "commit", "-m", message)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=work, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


def key_for(sha):
    return f"quarto-freezer-Linux--{sha}-1"


def site(work):
    """A two-page site, both pages frozen, plus a data file one page reads."""
    write(work, "chapters/a.qmd", "# A\n\n{{< include _subfiles/a/_part.qmd >}}\n")
    write(work, "chapters/_subfiles/a/_part.qmd", "Part one.\n")
    write(work, "chapters/b.qmd", '# B\n\n```{r}\nread.csv("data/b.csv")\n```\n')
    write(work, "chapters/data/b.csv", "x\n1\n")
    write(work, "chapters/c.qmd", "# C\n\nSee [A](a.qmd).\n")
    sha = commit(work, "site")
    for page in ("a", "b", "c"):
        write(work, f"_freeze/chapters/{page}/execute-results/html.json", "{}")
    return sha


def run(pruner, monkeypatch, work, key):
    monkeypatch.setenv("PROJECT_DIR", str(work))
    monkeypatch.delenv("FREEZE_DIR", raising=False)
    monkeypatch.setenv("MATCHED_KEY", key)
    assert pruner.main() == 0


def frozen(work):
    root = work / "_freeze" / "chapters"
    if not root.is_dir():
        return set()
    return {path.name for path in root.iterdir()}


def test_changed_subfile_unfreezes_its_parent_only(pruner, monkeypatch, repo_factory):
    work = repo_factory(published=None)
    source = site(work)
    write(work, "chapters/_subfiles/a/_part.qmd", "Part one, revised.\n")
    commit(work, "edit subfile")

    run(pruner, monkeypatch, work, key_for(source))

    assert frozen(work) == {"b", "c"}


def test_changed_data_file_unfreezes_the_page_that_reads_it(pruner, monkeypatch, repo_factory):
    work = repo_factory(published=None)
    source = site(work)
    write(work, "chapters/data/b.csv", "x\n2\n")
    commit(work, "edit data")

    run(pruner, monkeypatch, work, key_for(source))

    assert frozen(work) == {"a", "c"}


def test_a_link_to_a_changed_page_does_not_unfreeze_the_linking_page(
    pruner, monkeypatch, repo_factory
):
    """c.qmd links to a.qmd; editing a.qmd must not re-execute c.qmd."""
    work = repo_factory(published=None)
    source = site(work)
    write(work, "chapters/a.qmd", "# A, retitled\n\n{{< include _subfiles/a/_part.qmd >}}\n")
    commit(work, "edit page")

    run(pruner, monkeypatch, work, key_for(source))

    assert frozen(work) == {"b", "c"}


def test_unchanged_tree_keeps_everything(pruner, monkeypatch, repo_factory):
    work = repo_factory(published=None)
    source = site(work)

    run(pruner, monkeypatch, work, key_for(source))

    assert frozen(work) == {"a", "b", "c"}


def test_source_commit_is_fetched_when_missing(pruner, monkeypatch, repo_factory):
    """CI checks out one commit, so the cache's source commit is usually absent."""
    work = repo_factory(published=None)
    source = site(work)
    git(work, "push", "origin", "main")
    write(work, "chapters/_subfiles/a/_part.qmd", "Part one, revised.\n")
    head = commit(work, "edit subfile")
    git(work, "push", "origin", "main")

    shallow = work.parent / "shallow"
    origin = work.parent.joinpath("origin.git").as_uri()
    git(work.parent, "clone", "--depth=1", origin, str(shallow))
    for page in ("a", "b", "c"):
        write(shallow, f"_freeze/chapters/{page}/execute-results/html.json", "{}")
    probe = subprocess.run(["git", "cat-file", "-e", f"{source}^{{commit}}"], cwd=shallow)
    assert probe.returncode != 0, "the fixture must start without the source commit"
    assert head

    run(pruner, monkeypatch, shallow, key_for(source))

    assert frozen(shallow) == {"b", "c"}


def test_unreachable_source_commit_discards_the_freeze(pruner, monkeypatch, repo_factory):
    work = repo_factory(published=None)
    site(work)

    run(pruner, monkeypatch, work, key_for("0" * 40))

    assert not (work / "_freeze").exists()


def test_key_without_a_commit_discards_the_freeze(pruner, monkeypatch, repo_factory):
    work = repo_factory(published=None)
    site(work)

    run(pruner, monkeypatch, work, "Linux-quarto-freezer-main-")

    assert not (work / "_freeze").exists()


def test_nothing_restored_is_a_no_op(pruner, monkeypatch, repo_factory):
    work = repo_factory(published=None)
    site(work)

    run(pruner, monkeypatch, work, "")

    assert frozen(work) == {"a", "b", "c"}
