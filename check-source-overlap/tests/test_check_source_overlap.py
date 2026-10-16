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

        # a quote over 600 characters must not shift the pairing and hide the prose after it
        long_quote = "x" * 700
        doc.write_text(f'"{long_quote}" {SOURCE.lower()} "end"\n')
        assert run(root / "corpus", doc, "--fail").returncode == 1, "long quote hid a copy"

        # words either side of a removed quote do not join into a run
        half = " ".join(words[:7]).lower()
        rest = " ".join(words[7:14]).lower()
        doc.write_text(f'{half} "an unrelated quotation of some length" {rest}\n')
        assert run(root / "corpus", doc, "--min-run", "13", "--density", "0.99", "--fail").returncode == 0, \
            "quote joined the words around it"

        # a code span that names the opt-out is not the opt-out
        doc.write_text(f"Write `<!-- overlap-ok: reason -->` to exempt text. {SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "code span exempted a copy"

        # an overlap-ok comment on its own lines above the paragraph exempts it
        doc.write_text(f"<!-- overlap-ok:\nchecked by hand -->\n{SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 0, "comment above did not exempt"

        # an HTML comment inside a paragraph does not split it
        doc.write_text(" ".join(words[:12]).lower() + "\n<!-- note -->\n" + " ".join(words[12:24]).lower() + "\n")
        assert run(root / "corpus", doc, "--min-run", "20", "--fail").returncode == 1, "comment split the paragraph"

        # a line-wrapped code span and a double-backtick span naming the opt-out do not opt out
        doc.write_text(f"Write `<!-- overlap-ok:\nreason -->` to exempt text. {SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "wrapped code span exempted a copy"
        doc.write_text(f"Write `` `<!-- overlap-ok: reason -->` `` to exempt. {SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "double-backtick span exempted a copy"

        # a backtick inside an earlier comment pairs with nothing outside it
        doc.write_text(f"<!-- a `\nnote --> Write `<!-- overlap-ok: reason -->` here. {SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "comment backtick exposed the opt-out"

        # a blank line inside a comment still splits paragraphs, so one opt-out does not reach the next
        doc.write_text(f"Fine. <!-- overlap-ok: x -->\n<!-- break\n\n-->\n{SOURCE.lower()}\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "opt-out leaked across a comment"

        # mixed or stray quote marks must not pair across prose and hide it
        body = SOURCE.lower()
        for text in (
            f'He said “hello" and then {body} and later said “goodbye" to us.',
            f'On a 15" screen, {body}, which is "ok" here.',
            f'See [ref](https://example.com "eq. (1)") where {body}, called "ok" here.',
        ):
            doc.write_text(text + "\n")
            assert run(root / "corpus", doc, "--fail").returncode == 1, f"quotes hid a copy: {text[:30]}"

        # inline math wrapped across a line does not hide prose between two spans
        doc.write_text(f"Take $a +\nb$ and {body} then $c +\nd$ here.\n")
        assert run(root / "corpus", doc, "--fail").returncode == 1, "wrapped math hid a copy"

        # a missing file and a corpus with no text are refused, not read as a pass
        assert run(root / "corpus", root / "nope.qmd").returncode == 2, "missing file passed"
        assert run(root / "corpus", doc, "--exclude", "x").returncode == 2, "--exclude without --git-diff accepted"
        blank = root / "blank"
        blank.mkdir()
        (blank / "scan.txt").write_text("\n")
        assert run(blank, doc).returncode == 2, "textless corpus passed"

        # soft hyphens and a hyphenation split by a pdftotext page break are joined in the corpus
        messy = root / "messy"
        messy.mkdir()
        (messy / "book.txt").write_text(SOURCE.replace("expected", "expect\u00aded")
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
    r = diff_run(repo, corpus, "--fail", "--exclude", "_vendor")
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
