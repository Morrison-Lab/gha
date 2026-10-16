#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Flag prose that overlaps a reference text, as a guard against unintentional plagiarism.

Reference texts (textbooks, papers, other courses' notes) are plain-text files
the caller extracts first (`pdftotext book.pdf book.txt`, without `-layout`, which interleaves a two-column page) from copies held in
`Morrison-Lab/mlr`; their text is never committed anywhere.
A chapter's prose is cut into paragraphs and compared with the corpus by word n-grams:

* a paragraph is flagged when at least `--min-run` consecutive words occur verbatim in a source
  (a close paraphrase that keeps a clause or two still trips this), or
* when at least `--density` of its n-grams occur in a source (a near copy with scattered edits).

Text that quotes its source properly is skipped: blockquotes, text inside double quotation marks,
and paragraphs containing an `<!-- overlap-ok: reason -->` comment for a passage checked by hand.
Code fences, display math, inline math, URLs, citation keys and Quarto attributes are removed first.

A run is matched by 6-grams, not by position, so two 6-grams from different places in one book
that overlap by five words can stitch a run the book never prints; that needs a chance overlap
and is rare.

Advisory by default (exit 0); `--fail` exits 1 when anything is flagged.
Exit 2 means nothing could be checked (no corpus, or named files and no input), so an empty pass
is never silent.
The summary line always reports how many paragraphs were examined: a page that is wholly quoted,
or a `--git-diff` change that adds no prose, is a real pass with `examined 0`, and says so.

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
OVERLAP_OK = re.compile(r"<!--\s*overlap-ok\b")
BREAK = "qqbreakqq"  # replaces a removed quotation; no corpus holds it
KEEP = "\u2060"  # a non-space mark that keeps a blanked comment line inside its paragraph
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}


def normalize_words(text: str) -> list[str]:
    text = text.lower().replace("’", "'").replace("‘", "'")
    # a soft hyphen (U+00AD) and \x0c the form feed pdftotext writes between pages
    text = text.replace("\r\n", "\n").replace("\u00ad", "").replace("-\n\x0c", "").replace("-\n", "")
    text = text.replace("\x0c", "\n")
    for ligature, letters in LIGATURES.items():  # pdftotext keeps ligatures as single characters
        text = text.replace(ligature, letters)
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
    # Fenced code, HTML comments and code spans are replaced in one pass, so whichever
    # construct starts first wins: a backtick inside a comment opens no code span,
    # and a comment marker inside a fence or a code span is not a comment.
    raw = CONSTRUCT.sub(shield_construct, raw)
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
        # lines that only hold a blanked comment are not prose: skip them for the start and the diff test
        prose = [(i, line) for i, line in block if line.replace(KEEP, "").strip()]
        if not prose:
            continue
        start = prose[0][0]
        if only_lines is not None and not any(i in only_lines for i, _ in prose):
            continue
        if OVERLAP_OK.search("\n".join(line for _, line in block)):
            continue
        # a line that opens with `>` is quoted, so only the other lines of the paragraph are checked
        text = "\n".join(line for _, line in block if not line.lstrip().startswith(">"))
        if not text.strip():
            continue
        text = strip_markup(text)
        text = re.sub(r"“([^”]*)”", unquote_long, text)  # curly-quoted
        text = re.sub(r'"([^"]*)"', unquote_long, text)  # straight-quoted, possibly wrapped
        yield start, text


CONSTRUCT = re.compile(
    r"^[ \t]*(?P<fence>```+|~~~+).*?^[ \t]*(?P=fence)\s*$"  # fenced code
    r"|<!--.*?-->"  # HTML comment
    r"|(?P<tick>`+)(?!`)(?:(?!\n[ \t]*\n).)+?(?<!`)(?P=tick)(?!`)",  # code span, possibly wrapped
    re.S | re.M,
)


def shield_construct(m: re.Match) -> str:
    """Replace a fence, comment or code span with text that keeps the line count.

    A fence becomes blank lines.
    A code span becomes a placeholder, so a span that names the opt-out is not the opt-out.
    A comment keeps its blank lines, which split paragraphs as they did before,
    and each other line becomes a non-space mark so the comment never splits a paragraph.
    An `overlap-ok` comment keeps a marker on its first and last line,
    so the paragraph before it and the paragraph after it both opt out.
    """
    text = m.group(0)
    if m.group("fence"):
        return "\n" * text.count("\n")
    if m.group("tick"):
        return "`_`" + "\n" * text.count("\n")
    lines = [KEEP if line.strip() else "" for line in text.split("\n")]
    if OVERLAP_OK.match(text):
        lines[0] = lines[-1] = "<!-- overlap-ok -->"
    return " " + "\n".join(lines) + " "


def unquote_long(m: re.Match) -> str:
    """Replace a quoted passage of 20 or more characters with a break and keep a short quoted phrase.

    Quote marks are paired left to right with no length cap, so a long quote never lets
    the pairing slip and hide the prose between two quotes.
    The break word is in no corpus, so words on either side of a removed quote
    never join into one run.
    """
    return f" {BREAK} " if len(m.group(1)) >= 20 else m.group(0)


def wordy(gram) -> bool:
    """An n-gram of mostly digits and symbols (a table, a numeric listing) is not prose."""
    return sum(w.isalpha() for w in gram) >= N - 1


def build_index(corpus: Path):
    """Map each hashed n-gram to a bit mask of the sources that hold it (bit i is source i).

    `hash` of a tuple of strings is salted per process, so build and use the index in one run
    and never write it to disk.
    """
    index: dict[int, int] = {}
    names: list[str] = []
    empty: list[str] = []
    files = sorted(p for p in corpus.rglob("*.txt") if p.is_file())
    for p in files:
        names.append(str(p.relative_to(corpus)))
        sid = len(names) - 1
        words = normalize_words(p.read_text(encoding="utf-8", errors="replace"))
        grams = 0
        for k in range(len(words) - N + 1):
            gram = tuple(words[k:k + N])
            if wordy(gram):
                h = hash(gram)
                index[h] = index.get(h, 0) | (1 << sid)
                grams += 1
        if not grams:
            empty.append(names[-1])
    return index, names, empty


def longest_run(hits):
    """Words in the longest stretch of overlapping matching n-grams."""
    best = run = 1
    for a, b in zip(hits, hits[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    return best + N - 1


def check(words, index, n_sources, min_run, min_density):
    """Return (flagged, run, density, source id) for the source that matches the paragraph best.

    Each source is scored alone, so n-grams from two books never add up to a run or a density
    that neither book has.
    A source that trips a threshold is preferred to one that only matches more words.
    """
    marks = [(k, index.get(hash(tuple(words[k:k + N])), 0)) for k in range(len(words) - N + 1)]
    best = (False, 0, 0.0, 0)
    for sid in range(n_sources):
        hits = [k for k, mask in marks if mask >> sid & 1]
        if not hits:
            continue
        run = longest_run(hits)
        density = len(hits) / max(1, len(words) - N + 1)
        flagged = run >= min_run or (density >= min_density and len(hits) >= 6)
        if (flagged, run, density) > best[:3]:
            best = (flagged, run, density, sid)
    return best


def changed_lines(base: str, excludes=()):
    """Map each existing .qmd/.md file to the line numbers the change adds, relative to the cwd.

    `excludes` are git pathspecs such as ':(exclude)_extensions'.
    """
    cmd = ["git", "diff", "-U0", "--relative", f"{base}...HEAD", "--", "*.qmd", "*.md", *excludes]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    added, cur = defaultdict(set), None
    for line in out.splitlines():
        if line.startswith("+++ "):
            # `+++ /dev/null` is a deleted file; its hunks add nothing and must not reach the last file
            cur = Path(line[6:]) if line.startswith("+++ b/") else None
        elif line.startswith("@@") and cur:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            s, c = int(m.group(1)), int(m.group(2) or 1)
            if c and cur.is_file():  # a pure deletion adds no lines
                added[cur].update(range(s, s + c))
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--git-diff", metavar="BASE", default=None)
    ap.add_argument("--min-run", type=int, default=12, help="verbatim words that flag a paragraph")
    ap.add_argument("--density", type=float, default=0.25)
    ap.add_argument("--fail", action="store_true")
    ap.add_argument("--exclude", action="append", default=[], metavar="PATHSPEC",
                    help="path to leave out of --git-diff, e.g. _extensions or ':(exclude)_extensions' (repeatable)")
    ap.add_argument("files", nargs="*", type=Path)
    a = ap.parse_args()

    if not a.corpus.is_dir():
        print(f"error: corpus {a.corpus} is not a directory", file=sys.stderr)
        return 2
    index, names, empty = build_index(a.corpus)
    if not names:
        print(f"error: no .txt files under {a.corpus}", file=sys.stderr)
        return 2
    for name in empty:
        print(f"warning: {name} holds no text to compare (is the PDF scanned?)", file=sys.stderr)
    if not index:
        print("error: no source holds any text to compare", file=sys.stderr)
        return 2
    if a.git_diff is not None and a.files:
        print("error: name files or use --git-diff, not both", file=sys.stderr)
        return 2
    if a.exclude and a.git_diff is None:
        print("error: --exclude applies only to --git-diff", file=sys.stderr)
        return 2
    if a.git_diff is not None:
        excludes = [e if e.startswith(":") else f":(exclude){e}" for e in a.exclude]
        targets = changed_lines(a.git_diff, excludes)
    else:
        missing = [p for p in a.files if not p.is_file()]
        if missing or not a.files:
            print("error: no input files" if not a.files else
                  f"error: not a file: {', '.join(map(str, missing))}", file=sys.stderr)
            return 2
        targets = {p: None for p in a.files}

    examined = flagged = 0
    for path, lines in sorted(targets.items()):
        for start, text in paragraphs(path, lines):
            words = normalize_words(text)
            if len(words) < N + 2:
                continue
            examined += 1
            hit, run, dens, sid = check(words, index, len(names), a.min_run, a.density)
            if hit:
                flagged += 1
                print(f"{path}:{start}: {run} verbatim words, {dens:.0%} of {N}-grams shared "
                      f"[{names[sid]}]")
    print(f"examined {examined} paragraphs against {len(names)} sources ({len(index)} n-grams); "
          f"flagged {flagged}")
    return 1 if (flagged and a.fail) else 0


if __name__ == "__main__":
    sys.exit(main())
