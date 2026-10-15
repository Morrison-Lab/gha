#!/usr/bin/env python3
"""Self-test for check_source_overlap.py: it must flag a copy, spare a quote, and refuse an empty run."""

import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "check_source_overlap.py"
SOURCE = ("The bias variance tradeoff describes how the expected prediction error of a flexible "
          "model splits into three pieces, so that lowering one piece tends to raise another.")


def run(corpus: Path, doc: Path, *extra):
    return subprocess.run([sys.executable, str(TOOL), "--corpus", str(corpus), *extra, str(doc)],
                          capture_output=True, text=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "corpus").mkdir()
        (root / "corpus" / "book.txt").write_text(SOURCE + "\n")
        doc = root / "page.qmd"

        doc.write_text("Intro text.\n\nNote that " + SOURCE.lower() + " That is the point.\n")
        r = run(root / "corpus", doc, "--fail")
        assert r.returncode == 1 and "page.qmd:3" in r.stdout, ("copy not flagged", r.stdout)

        doc.write_text(f'As the book puts it, "{SOURCE}" [@book, p. 1].\n')
        r = run(root / "corpus", doc, "--fail")
        assert r.returncode == 0 and "flagged 0" in r.stdout, ("quote flagged", r.stdout)

        doc.write_text("> " + SOURCE + "\n")
        assert run(root / "corpus", doc, "--fail").returncode == 0, "blockquote flagged"

        doc.write_text(SOURCE + " <!-- overlap-ok: checked by hand -->\n")
        assert run(root / "corpus", doc, "--fail").returncode == 0, "opt-out ignored"

        doc.write_text("```python\n# " + SOURCE + "\n\nprint(1)\n```\n")
        assert run(root / "corpus", doc, "--fail").returncode == 0, "code fence flagged"

        doc.write_text("An unrelated sentence about gradient descent and learning rates in practice.\n")
        assert "flagged 0" in run(root / "corpus", doc).stdout

        words = SOURCE.split()
        wrapped = " ".join(words[:8]) + "\n" + " ".join(words[8:])
        doc.write_text(f'As the book puts it, "{wrapped}" [@book, p. 1].\n')
        r = run(root / "corpus", doc, "--fail")
        assert r.returncode == 0 and "flagged 0" in r.stdout, ("wrapped quote flagged", r.stdout)

        # a near copy with an edit every few words has no long verbatim run; the density rule catches it
        edited = " ".join(w if i % 9 else "zzz" + w for i, w in enumerate(words))
        doc.write_text(f"{edited}\n")
        r = run(root / "corpus", doc, "--min-run", "99", "--fail")
        assert r.returncode == 1, ("density rule did not fire", r.stdout)

        empty = root / "empty"
        empty.mkdir()
        assert run(empty, doc).returncode == 2, "empty corpus passed silently"

        git_diff_cases(root, root / "corpus")
    print("ok")
    return 0


def git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org",  # phi-allow
                    *args], check=True, capture_output=True)


def diff_run(repo: Path, corpus: Path, *extra):
    return subprocess.run([sys.executable, str(TOOL), "--corpus", str(corpus), "--git-diff", "base",
                           *extra], cwd=repo, capture_output=True, text=True)


def git_diff_cases(root: Path, corpus: Path):
    """The `--git-diff` path: added lines only, deletions and renames survive, excludes apply."""
    repo = root / "repo"
    (repo / "vendor").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "old.qmd").write_text("A page that will be deleted later on in the change.\n")
    (repo / "keep.qmd").write_text("Intro.\n\nSecond paragraph of unrelated prose stays put here.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "tag", "base")

    git(repo, "rm", "-q", "old.qmd")
    with (repo / "keep.qmd").open("a") as f:
        f.write("\nNote that " + SOURCE.lower() + " That is the point.\n")
    (repo / "vendor" / "lib.md").write_text(SOURCE + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")

    r = diff_run(repo, corpus, "--fail")
    assert r.returncode == 1 and "keep.qmd:" in r.stdout and "vendor" in r.stdout, ("diff copy", r.stdout, r.stderr)
    r = diff_run(repo, corpus, "--fail", "--exclude", ":!vendor")
    assert r.returncode == 1 and "vendor" not in r.stdout, ("exclude ignored", r.stdout)
    assert "old.qmd" not in r.stdout and r.stderr == "", ("deleted file mishandled", r.stderr)

    git(repo, "tag", "-f", "base", "HEAD")
    (repo / "keep.qmd").write_text("Intro.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "only deletes")
    r = diff_run(repo, corpus, "--fail")
    assert r.returncode == 0 and "examined 0" in r.stdout, ("deletion-only change", r.stdout, r.stderr)


if __name__ == "__main__":
    sys.exit(main())
