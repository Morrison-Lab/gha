#!/usr/bin/env python3
"""Flag prose that overlaps a reference text, as a guard against unintentional plagiarism.

Reference texts (textbooks, papers, other courses' notes) are plain-text files
the caller extracts first (`pdftotext -layout book.pdf book.txt`) from copies held in
`Morrison-Lab/mlr`; their text is never committed anywhere.
A chapter's prose is cut into paragraphs and compared with the corpus by word n-grams:

* a paragraph is flagged when at least `--min-run` consecutive words occur verbatim in a source
  (a close paraphrase that keeps a clause or two still trips this), or
* when at least `--density` of its n-grams occur in a source (a near copy with scattered edits).

Text that quotes its source properly is skipped: blockquotes, text inside double quotation marks,
and paragraphs carrying an `{#id}`-less `[!NOTE]`-style opt-out comment
`<!-- overlap-ok: reason -->` for a passage checked by hand.
Code fences, display math, inline math, URLs, citation keys and Quarto attributes are removed first.

Advisory by default (exit 0); `--fail` exits 1 when anything is flagged.
Exit 2 means nothing could be checked (no corpus or no input), so an empty pass is never silent.

Usage:
    check_source_overlap.py --corpus DIR_OF_TXT chapters/foo.qmd [more.qmd ...]
    check_source_overlap.py --corpus DIR --git-diff origin/main   # only lines a PR adds
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

N = 6  # shingle length in words


def normalize_words(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = text.replace("­", "").replace("-\n", "")
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text)


def strip_markup(text: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"^[ \t]*(```+|~~~+).*?^[ \t]*\1\s*$", " ", text, flags=re.S | re.M)
    text = re.sub(r"^\s*\|.*$", " ", text, flags=re.M)  # table rows
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"\$[^$\n]+\$", " ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\{\{<.*?>\}\}", " ", text)
    text = re.sub(r"\[@[^\]]*\]", " ", text)
    text = re.sub(r"@[A-Za-z][\w:.-]*", " ", text)
    text = re.sub(r"\]\([^)]*\)", "] ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\{[#.=][^}]*\}", " ", text)
    text = re.sub(r"^:{3,}.*$", " ", text, flags=re.M)
    return text


def paragraphs(path: Path, only_lines: set[int] | None):
    """Yield (first_line, text) for each paragraph that survives the quoting exemptions."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Blank out fenced code before splitting on blank lines, which also occur inside a fence;
    # the newlines stay so reported line numbers still match the file.
    raw = re.sub(r"^[ \t]*(```+|~~~+).*?^[ \t]*\1\s*$",
                 lambda m: "\n" * m.group(0).count("\n"), raw, flags=re.S | re.M)
    lines = raw.split("\n")
    block, start = [], 1
    out = []
    for i, line in enumerate(lines, 1):
        if line.strip():
            if not block:
                start = i
            block.append((i, line))
        elif block:
            out.append((start, block))
            block = []
    if block:
        out.append((start, block))
    for start, block in out:
        if only_lines is not None and not any(i in only_lines for i, _ in block):
            continue
        text = "\n".join(line for _, line in block)
        if "overlap-ok" in text or all(line.lstrip().startswith(">") for _, line in block):
            continue
        text = strip_markup(text)
        text = re.sub(r"“[^”]*”", " ", text)  # curly-quoted
        text = re.sub(r'"[^"\n]{20,}"', " ", text)  # straight-quoted
        yield start, text


def wordy(gram) -> bool:
    """An n-gram of mostly digits and symbols (a table, a numeric listing) is not prose."""
    return sum(w.isalpha() for w in gram) >= N - 1


def build_index(corpus: Path):
    """Map each hashed n-gram to the first source that holds it."""
    index: dict[int, int] = {}
    names: list[str] = []
    files = sorted(p for p in corpus.rglob("*.txt") if p.is_file())
    for p in files:
        names.append(str(p.relative_to(corpus)))
        sid = len(names) - 1
        words = normalize_words(p.read_text(encoding="utf-8", errors="replace"))
        for k in range(len(words) - N + 1):
            gram = tuple(words[k:k + N])
            if wordy(gram):
                index.setdefault(hash(gram), sid)
    return index, names


def check(words, index):
    hits = [k for k in range(len(words) - N + 1) if hash(tuple(words[k:k + N])) in index]
    if not hits:
        return 0, 0.0, []
    # longest run of overlapping matching n-grams, in words
    best = run = 1
    for a, b in zip(hits, hits[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    density = len(hits) / max(1, len(words) - N + 1)
    return best + N - 1, density, hits


def changed_lines(base: str):
    out = subprocess.run(["git", "diff", "-U0", f"{base}...HEAD", "--", "*.qmd", "*.md"],
                         capture_output=True, text=True, check=True).stdout
    added, cur = defaultdict(set), None
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            cur = Path(line[6:])
        elif line.startswith("@@") and cur:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            s, c = int(m.group(1)), int(m.group(2) or 1)
            added[cur].update(range(s, s + c))
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--git-diff", metavar="BASE")
    ap.add_argument("--min-run", type=int, default=12, help="verbatim words that flag a paragraph")
    ap.add_argument("--density", type=float, default=0.25)
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("files", nargs="*", type=Path)
    a = ap.parse_args()

    if not a.corpus.is_dir():
        print(f"error: corpus {a.corpus} is not a directory", file=sys.stderr)
        return 2
    index, names = build_index(a.corpus)
    if not names:
        print(f"error: no .txt files under {a.corpus}", file=sys.stderr)
        return 2
    targets = {p: None for p in a.files}
    if a.git_diff:
        targets.update(changed_lines(a.git_diff))
    if not targets:
        print("error: no input files", file=sys.stderr)
        return 2

    examined = flagged = 0
    for path, lines in sorted(targets.items()):
        for start, text in paragraphs(path, lines):
            words = normalize_words(text)
            if len(words) < N + 2:
                continue
            examined += 1
            run, dens, hits = check(words, index)
            if run >= a.min_run or (dens >= a.density and len(hits) >= 6):
                flagged += 1
                print(f"{path}:{start}: {run} verbatim words, {dens:.0%} of {N}-grams shared "
                      f"[{names[index[hash(tuple(words[hits[0]:hits[0] + N]))]]}]")
    print(f"examined {examined} paragraphs against {len(names)} sources ({len(index)} n-grams); "
          f"flagged {flagged}")
    return 1 if (flagged and a.fail) else 0


if __name__ == "__main__":
    sys.exit(main())
