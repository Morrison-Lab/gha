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

        empty = root / "empty"
        empty.mkdir()
        assert run(empty, doc).returncode == 2, "empty corpus passed silently"
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
