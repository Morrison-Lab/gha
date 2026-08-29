#!/usr/bin/env python3
"""Flag code in a PR that is highly similar to a caller-supplied corpus.

Wraps `JPlag <https://github.com/jplag/JPlag>`_, which computes every
similarity **locally** --- nothing is uploaded.  That is the whole reason it
was chosen over MOSS, which submits source to Stanford's servers (gha#296).

The comparison set is supplied by the caller: a directory of prior submissions
it has already checked out, downloaded as an artifact, or added as a
submodule.  JPlag's own ``--new`` / ``--old`` split maps onto that directly.

**Every failure path here is loud, and that is the design rather than
caution.**  A similarity check that cannot run looks exactly like a similarity
check that found nothing: both print no findings and both exit 0 if you let
them.  So a missing corpus, an empty corpus, a corpus too small to compare
against, a checksum mismatch, a JPlag crash, and a missing results file are
all errors -- never a quiet pass.  The only thing that exits 0 is a run that
actually compared submissions and found nothing above the threshold.

Usage::

    python3 check_code_similarity.py --path . --corpus-path corpus \\
        --language rlang [--threshold 0.8] [--fail] [--base-code-path skel]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

# Pinned by version AND digest: a floating download is a supply-chain hole in
# a tool that reads every line of the caller's source.
DEFAULT_JPLAG_VERSION = "6.3.0"
DEFAULT_JPLAG_SHA256 = "5f2c21e8b88ed77134effcb3a5a3ab13d188f6a3e16d401387f7479e92db9aa2"
JPLAG_URL = (
    "https://github.com/jplag/JPlag/releases/download/v{v}/"
    "jplag-{v}-jar-with-dependencies.jar"
)

# Exit codes. 2 is reserved for "the check did not run", so a caller can tell
# that apart from "the check ran and found something" (1).
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def die(message: str) -> "typing.NoReturn":  # noqa: F821
    print(f"::error::check-code-similarity: {message}", file=sys.stderr)
    raise SystemExit(EXIT_ERROR)


def emit(name: str, value: str) -> None:
    """Append a step output, when running inside Actions."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def count_submissions(root: pathlib.Path) -> int:
    """Count the immediate child directories JPlag would treat as submissions.

    JPlag takes a ROOT directory whose children are submissions, so a corpus
    handed a flat pile of files has nothing to compare and would silently
    produce an empty result.
    """
    if not root.is_dir():
        return 0
    return sum(1 for child in root.iterdir() if child.is_dir())


def resolve_jar(args) -> pathlib.Path:
    """Return a verified JPlag jar, downloading it only if necessary."""
    if args.jar:
        jar = pathlib.Path(args.jar)
        if not jar.is_file():
            die(f"--jar {jar} does not exist")
        # owned=False: a jar the caller pointed us at is not ours to delete.
        verify_digest(jar, args.jplag_sha256, owned=False)
        return jar

    cache = pathlib.Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    jar = cache / f"jplag-{args.jplag_version}.jar"
    if jar.is_file():
        verify_digest(jar, args.jplag_sha256)
        return jar

    url = JPLAG_URL.format(v=args.jplag_version)
    print(f"Downloading JPlag {args.jplag_version}...")
    try:
        with urllib.request.urlopen(url, timeout=args.download_timeout) as response:
            jar.write_bytes(response.read())
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        die(f"could not download JPlag from {url}: {exc}")
    verify_digest(jar, args.jplag_sha256)
    return jar


def verify_digest(jar: pathlib.Path, expected: str, *, owned: bool = True) -> None:
    """Refuse to run a jar whose digest does not match the pin.

    ``owned`` says whether this file is ours to delete. A bad jar in OUR cache
    must go, or the next run reuses it and the pin protects nothing. A bad jar
    the caller passed via ``--jar`` is a file we were merely pointed at, and
    deleting it would destroy something the action does not own -- found the
    hard way while testing the mismatch path against a local download.
    """
    if not expected:
        die(
            "no expected SHA-256 given for the JPlag jar. Refusing to run an "
            "unverified binary over the caller's source."
        )
    actual = hashlib.sha256(jar.read_bytes()).hexdigest()
    if actual == expected.lower():
        return
    detail = ""
    if owned:
        jar.unlink(missing_ok=True)
        detail = " The cached download was removed rather than kept."
    die(
        f"JPlag jar digest mismatch (expected {expected.lower()}, got "
        f"{actual}).{detail}"
    )


def run_jplag(jar: pathlib.Path, args, workdir: pathlib.Path) -> str:
    result_root = workdir / "result"
    command = [
        args.java,
        "-jar",
        str(jar),
        "--mode",
        "RUN",
        "--csv-export",
        "-l",
        args.language,
        "-r",
        str(result_root),
        "--new",
        str(args.path),
        "--old",
        str(args.corpus_path),
    ]
    if args.base_code_path:
        command += ["--base-code", str(args.base_code_path)]
    if args.min_tokens:
        command += ["-t", str(args.min_tokens)]

    completed = subprocess.run(command, capture_output=True, text=True)
    stderr = completed.stderr or ""

    # JPlag's R grammar does not parse R's native pipe `|>`, so a corpus in
    # this lab's house style emits one ANTLR error per piped line. Measured on
    # gha#296: detection still scored a renamed-identifier copy at 1.0, and a
    # copy whose pipe style had been rewritten also at 1.0, so it degrades
    # rather than defeats. Surfaced as a count rather than swallowed, because
    # a parse error means tokens were dropped and a marginal pair could be
    # missed.
    parse_errors = stderr.count("ANTLR error")
    if parse_errors:
        print(
            f"::warning::JPlag reported {parse_errors} parse error(s). Tokens "
            "on those lines were dropped, so similarity is a lower bound. R's "
            "native pipe `|>` is a known cause (see the action's README)."
        )

    if completed.returncode != 0:
        sys.stderr.write(stderr[-4000:])
        die(f"JPlag exited {completed.returncode}; no comparison was performed")

    csv_path = result_root / "results.csv"
    if not csv_path.is_file():
        die(
            f"JPlag exited 0 but wrote no {csv_path.name}, so nothing was "
            "compared. Treating as a failed run rather than a clean result."
        )
    return csv_path.read_text(encoding="utf-8")


def parse_pairs(text: str) -> list[tuple[str, str, float]]:
    """Return (a, b, maxSimilarity) rows from JPlag's results CSV."""
    rows = list(csv.DictReader(text.splitlines()))
    required = {"submissionName1", "submissionName2", "maxSimilarity"}
    if not rows:
        die("JPlag's results CSV has no rows, so no pair was compared")
    missing = required - set(rows[0])
    if missing:
        die(f"JPlag's results CSV is missing column(s): {', '.join(sorted(missing))}")

    pairs = []
    for row in rows:
        try:
            similarity = float(row["maxSimilarity"])
        except (TypeError, ValueError):
            die(f"unparseable maxSimilarity in JPlag output: {row['maxSimilarity']!r}")
        pairs.append((row["submissionName1"], row["submissionName2"], similarity))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=".", type=pathlib.Path)
    parser.add_argument("--corpus-path", required=True, type=pathlib.Path)
    parser.add_argument("--base-code-path", default="", type=str)
    parser.add_argument("--language", default="rlang")
    parser.add_argument("--threshold", default="0.8")
    parser.add_argument("--min-tokens", default="")
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--jar", default=os.environ.get("JPLAG_JAR", ""))
    parser.add_argument("--java", default=os.environ.get("JAVA_BIN", "java"))
    parser.add_argument("--cache-dir", default=os.environ.get("JPLAG_CACHE_DIR", ".jplag-cache"))
    parser.add_argument("--work-dir", default=os.environ.get("JPLAG_WORK_DIR", ""))
    parser.add_argument("--jplag-version", default=DEFAULT_JPLAG_VERSION)
    parser.add_argument("--jplag-sha256", default=DEFAULT_JPLAG_SHA256)
    parser.add_argument("--download-timeout", type=int, default=300)
    args = parser.parse_args(argv)

    try:
        threshold = float(args.threshold)
    except ValueError:
        die(f"--threshold must be a number between 0 and 1; got {args.threshold!r}")
    if not 0.0 <= threshold <= 1.0:
        die(f"--threshold must be between 0 and 1; got {threshold}")

    if not args.path.is_dir():
        die(f"--path {args.path} is not a directory")
    if not args.corpus_path.is_dir():
        die(
            f"--corpus-path {args.corpus_path} is not a directory. A missing "
            "corpus is an error, not an empty comparison."
        )

    # The corpus is the input most likely to arrive empty -- an artifact that
    # did not download, a submodule that was not initialised, a glob that
    # matched nothing. Every one of those looks like "no similar code found".
    corpus_n = count_submissions(args.corpus_path)
    if corpus_n == 0:
        die(
            f"--corpus-path {args.corpus_path} contains no submission "
            "directories. JPlag treats each CHILD directory as one "
            "submission, so a flat pile of files compares against nothing. "
            "Refusing to report a clean result over an empty corpus."
        )
    own_n = count_submissions(args.path)
    if own_n == 0:
        die(
            f"--path {args.path} contains no submission directories, so there "
            "is nothing to compare against the corpus."
        )
    print(f"Comparing {own_n} submission(s) against {corpus_n} corpus submission(s).")

    if not shutil.which(args.java):
        die(
            f"`{args.java}` is not on PATH. JPlag {args.jplag_version} needs "
            "Java 25 or newer."
        )

    work = pathlib.Path(args.work_dir) if args.work_dir else pathlib.Path(".jplag-run")
    work.mkdir(parents=True, exist_ok=True)

    jar = resolve_jar(args)
    pairs = parse_pairs(run_jplag(jar, args, work))

    # Only pairs that actually involve the submission under review. JPlag also
    # compares corpus entries with each other, and two prior submissions
    # resembling one another is not this PR's problem.
    own_names = {child.name for child in args.path.iterdir() if child.is_dir()}

    def involves_submission(a: str, b: str) -> bool:
        return any(side.split("/")[-1] in own_names for side in (a, b))

    relevant = [p for p in pairs if involves_submission(p[0], p[1])]
    flagged = sorted(
        (p for p in relevant if p[2] >= threshold), key=lambda p: -p[2]
    )
    highest = max((p[2] for p in relevant), default=0.0)

    emit("max-similarity", f"{highest:.4f}")
    emit("flagged-count", str(len(flagged)))
    emit("report-dir", str(work / "result"))

    if not flagged:
        print(
            f"No pair at or above {threshold:g}. Highest similarity involving "
            f"this submission: {highest:.4f} across {len(relevant)} pair(s)."
        )
        return EXIT_OK

    print(f"::group::{len(flagged)} pair(s) at or above {threshold:g}")
    for a, b, similarity in flagged:
        print(f"  {similarity:.4f}  {a}  <->  {b}")
    print("::endgroup::")

    summary = (
        f"{len(flagged)} submission pair(s) scored at or above {threshold:g} "
        "similarity. This is a review signal, not a verdict: shared skeleton "
        "code, a common idiom, and a genuinely small assignment all raise "
        "similarity legitimately. Use --base-code-path to exclude a provided "
        "framework."
    )
    if args.fail:
        print(f"::error::{summary}")
        return EXIT_FINDINGS
    print(f"::warning::{summary}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
