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

        # a short quote must not pair with the next one and hide the prose between them
        doc.write_text(f'He said "hello" and then {SOURCE.lower()} and later said "goodbye" to us.\n')
        r = run(root / "corpus", doc, "--fail")
        assert r.returncode == 1, ("short quotes hid a copy", r.stdout)

        # only the `>` lines of a paragraph are quoted; a copied line beside them is still checked
        doc.write_text(f"> a quoted line\n{SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "copy beside a blockquote passed"

        # naming the opt-out in prose is not the opt-out
        doc.write_text(f"Add an overlap-ok comment to exempt text. {SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "prose mention exempted a copy"

        # a comment with a blank line inside is not prose, and an overlap-ok comment that spans one still opts out
        doc.write_text(f"Before.\n\n<!-- note\n\n{SOURCE.lower()}\n-->\n\nAfter.\n")
        assert run(root / "corpus", doc, "--fail").returncode == 0, "multi-line comment scanned as prose"
        doc.write_text(f"{SOURCE.lower()} <!-- overlap-ok: first line\n\nsecond paragraph of the note -->\n")
        assert run(root / "corpus", doc, "--fail").returncode == 0, "multi-line overlap-ok ignored"

        # named files and --git-diff together are ambiguous, so they are refused
        r = run(root / "corpus", doc, "--git-diff", "HEAD")
        assert r.returncode == 2, ("files with --git-diff accepted", r.stdout)

        # soft hyphens and a hyphenation split by a pdftotext page break are joined in the corpus
        messy = root / "messy"
        messy.mkdir()
        (messy / "book.txt").write_text(SOURCE.replace("expected", "expect­ed")
                                        .replace("prediction", "predic-\n\x0ction") + "\n")
        doc.write_text("Note that " + SOURCE.lower() + " That is the point.\n")
        assert run(messy, doc, "--fail").returncode == 1, "soft hyphen or page break split the corpus words"

        # two books that each hold part of a paragraph do not add up to a copy of either
        words = SOURCE.split()
        parts = root / "parts"
        parts.mkdir()
        for name, (lo, hi) in {"a": (0, 12), "b": (6, 18), "c": (12, 24)}.items():
            (parts / f"{name}.txt").write_text(" ".join(words[lo:hi]) + "\n")
        doc.write_text(" ".join(words[:24]).lower() + "\n")
        r = run(parts, doc, "--min-run", "13", "--density", "0.9", "--fail")
        assert r.returncode == 0, ("n-grams from different books were added together", r.stdout)

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
    (repo / "_vendor").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (repo / "old.qmd").write_text("A page that will be deleted later on in the change.\n")
    (repo / "keep.qmd").write_text("Intro.\n\nSecond paragraph of unrelated prose stays put here.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    git(repo, "tag", "base")

    git(repo, "rm", "-q", "old.qmd")
    with (repo / "keep.qmd").open("a") as f:
        f.write("\nNote that " + SOURCE.lower() + " That is the point.\n")
    (repo / "_vendor" / "lib.md").write_text(SOURCE + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")

    r = diff_run(repo, corpus, "--fail")
    assert r.returncode == 1 and "keep.qmd:" in r.stdout and "_vendor" in r.stdout, ("diff copy", r.stdout, r.stderr)
    r = diff_run(repo, corpus, "--fail", "--exclude", ":(exclude)_vendor")
    assert r.returncode == 1 and "_vendor" not in r.stdout, ("exclude ignored", r.stdout)
    assert "old.qmd" not in r.stdout and r.stderr == "", ("deleted file mishandled", r.stderr)

    git(repo, "tag", "-f", "base", "HEAD")
    (repo / "keep.qmd").write_text("Intro.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "only deletes")
    r = diff_run(repo, corpus, "--fail")
    assert r.returncode == 0 and "examined 0" in r.stdout, ("deletion-only change", r.stdout, r.stderr)


if __name__ == "__main__":
    sys.exit(main())
