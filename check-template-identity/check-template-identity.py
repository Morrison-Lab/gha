#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Fail a repository made from a template while it still carries the template's identity.

"Use this template" copies a template's files once, so a new site starts with
the template's own site URL, repository URL, title and placeholder author.
Nothing reports them: the site renders, and its "Edit this page" link opens
the template's repository (Morrison-Lab/gha#2154, Morrison-Lab/qwt#207).

The check reads the tracked files that match ``files`` and reports every line
that still holds one of:

- the template's repository URL, ``github.com/<owner>/<name>``;
- the template's Pages URL, ``<owner>.github.io/<name>``;
- a literal listed in ``strings``, such as the template's title.

Matching ignores case, and a match that is part of a longer name on either
side (``github.com/<owner>/<name>-fork``, ``my-<owner>.github.io/<name>``)
does not count; that holds for the listed literals too. A dot with a letter
or digit after it carries a name on (``<name>.v2``), except the ``.git`` of a
clone URL; a dot that ends a sentence does not. A line that holds
``check-template-identity: allow: <reason>`` passes.

In the template itself (``repository`` equals ``template``) there is nothing
to check, and the script says so and exits 0. Elsewhere it stops with an
error when no tracked file matches ``files``, whatever ``fail`` says, so a
wrong list cannot pass by reading nothing.

Configuration (environment variables, set by the composite action):
  CTI_TEMPLATE     owner/name of the template repository (required).
  CTI_REPOSITORY   owner/name of this repository (default: GITHUB_REPOSITORY).
  CTI_FILES        Space-separated git pathspecs of the files to read.
  CTI_STRINGS      Newline-separated extra literals a derived repository must not keep.
  CTI_FAIL         "false" => warn only; default "true".
"""

import os
import re
import sys
from typing import List, NamedTuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

DEFAULT_FILES = "_quarto.yml _quarto-website.yml _quarto-book.yml DESCRIPTION index.qmd"
_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")
_ALLOW_RE = re.compile(r"check-template-identity:\s*allow:\s*\S")


class Finding(NamedTuple):
    path: str
    line: int
    needle: str


def forbidden_strings(template: str, extra: List[str]) -> List[str]:
    """The literals a derived repository must not keep, lower-cased."""
    owner, name = template.split("/", 1)
    derived = ["github.com/%s/%s" % (owner, name), "%s.github.io/%s" % (owner, name)]
    return [text.lower() for text in derived + extra]


def _in_name(char: str) -> bool:
    return char.isalnum() or char in "-_"


def _continues(rest: str) -> bool:
    """True when ``rest``, the text after a match, carries the name on.

    A repository name may hold a dot, so ``<name>.v2`` is a longer name. A dot
    that ends a sentence is not, and neither is the ``.git`` of a clone URL.
    """
    if not rest:
        return False
    if _in_name(rest[0]):
        return True
    if rest[0] != "." or len(rest) < 2 or not rest[1].isalnum():
        return False
    return not (rest.startswith(".git") and not _continues(rest[4:]))


def _whole_name(line: str, start: int, end: int) -> bool:
    """True when ``line[start:end]`` is not part of a longer name on either side."""
    before = start > 0 and _in_name(line[start - 1])
    return not (before or _continues(line[end:]))


def find_in_line(line: str, needles: List[str]) -> List[str]:
    """The needles that occur in ``line``, ignoring case."""
    if _ALLOW_RE.search(line):
        return []
    lowered = line.lower()
    found = []
    for needle in needles:
        start = lowered.find(needle)
        while start != -1:
            if _whole_name(lowered, start, start + len(needle)):
                found.append(needle)
                break
            start = lowered.find(needle, start + 1)
    return found


def scan(paths: List[str], needles: List[str]) -> List[Finding]:
    findings = []
    for path in paths:
        lines = diffscope.read_lines(path)
        if lines is None:
            raise SystemExit("check-template-identity: cannot read '%s'" % path)
        for number, line in enumerate(lines, start=1):
            for needle in find_in_line(line, needles):
                findings.append(Finding(path, number, needle))
    return findings


def tracked_files(globs: List[str]) -> List[str]:
    paths = diffscope.git_paths(["ls-files", "--"] + globs)
    if paths is None:
        raise SystemExit("check-template-identity: git ls-files failed; run it inside a git checkout")
    return [path for path in paths if os.path.isfile(path)]


def main() -> int:
    template = os.environ.get("CTI_TEMPLATE", "").strip()
    repository = (os.environ.get("CTI_REPOSITORY", "").strip()
                  or os.environ.get("GITHUB_REPOSITORY", "").strip())
    for label, value in (("template", template), ("repository", repository)):
        if not _REPO_RE.match(value):
            print("::error title=Template identity::%s must be owner/name, got '%s'"
                  % (label, value))
            return 2
    if template.lower() == repository.lower():
        print("check-template-identity: %s is the template itself; nothing to check"
              % repository)
        return 0
    globs = os.environ.get("CTI_FILES", "").split() or DEFAULT_FILES.split()
    extra = [s.strip() for s in os.environ.get("CTI_STRINGS", "").splitlines() if s.strip()]
    fail = diffscope.env_flag("CTI_FAIL", True)
    paths = tracked_files(globs)
    if not paths:
        print("::error title=Template identity::no tracked file matches '%s'; "
              "the check read nothing" % " ".join(globs))
        return 2
    findings = scan(paths, forbidden_strings(template, extra))
    level = "error" if fail else "warning"
    for f in findings:
        print("::%s file=%s,line=%d,title=Template identity::still holds the "
              "template's '%s'; replace it with this repository's own value"
              % (level, f.path, f.line, f.needle))
    print("check-template-identity: examined %d file(s), %d finding(s)"
          % (len(paths), len(findings)))
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
