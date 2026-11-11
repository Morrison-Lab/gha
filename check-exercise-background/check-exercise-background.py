#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an exercise whose title names an object that the body never mentions.

The lab's rule (Ezra, 2026-10-29; Morrison-Lab/psw teaching chapter): an
exercise body gives the background its title implies. If the title says
"Maximizing a gamma-family kernel", the body says what a gamma distribution
and its kernel are, links them, and says why anyone cares. This check covers
only the first step, naming the object: it cannot tell whether the body
links or explains it, so a pass does not mean the background is adequate.

What is flagged: an exercise div (id ``exr-...``) with a heading title or a
``title="..."`` attribute in which some content word does not occur in the
body. The body excludes nested solution divs (``#sol-``, ``.sol``,
``.solution``, ``.answer``), so a solution cannot hide a missing word. The
body also takes in the text of every div it cites or links (``@exr-``,
``@def-``, ``@thm-``, ``@sol-``, ``#def-...`` and the rest), followed
transitively, since citing is how a body gives background (gha#1481); a cited
exercise lends its text but not its solutions. An exercise that cites an
``exr-`` the scanned files do not hold is skipped. A word counts as present
when another word in the body shares its first five letters, so "Maximizing"
matches "maximum". Generic task verbs (find, compute, check, classify, ...)
and ordinary connecting words are never reported. Math in the title, code
fences and HTML comments are ignored.

This is a heuristic. A title word that the body expresses with a synonym is
reported too, which is why the check warns by default. Say the word in the
body, with its link, or reword the title.

Diff-scoped like check-bare-yes-no: a finding is reported only when the diff
adds a line of the exercise, an untouched exercise keeps its form, and with no
base ref the check skips rather than scanning the whole tree.
``EXB_WHOLE_TREE=true`` measures a corpus. Needs Python 3.9 or later.

Configuration (environment variables, set by the composite action):
  EXB_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  EXB_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  EXB_FAIL        "true" => exit 1 on a finding; default "false" => warnings.
  EXB_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import os
import re
import subprocess
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

DEFAULT_GLOBS = "*.qmd"
ADVICE = ("say it in the body and link its definition, "
          "or reword the title; give the background the title implies")

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
DIV_RE = re.compile(r"^ {0,3}(:{3,})\s*(.*?)\s*:*\s*$")
EXR_RE = re.compile(r"#exr-")
DEF_RE = re.compile(r"#def-")
# A later part of an exercise builds on the setup of an earlier exercise, which
# gives the background; the part itself need not repeat it.
CONTINUATION_RE = re.compile(r"\b(?:setup|set-up|situation|model|data) of @exr-|^\s*Use (?:the )?\w+ of @exr-",
                             re.MULTILINE)
# A cross-reference or link to another div brings that div's text in as
# background (gha#1481): citing a definition or an earlier exercise is how a
# body gives the background a title names.
REF_RE = re.compile(r"(?:@|#)(exr-[\w-]*\w)|(?:@|#)((?:thm|lem|prp|cor|exm|def|sol)-[\w-]*\w)")
ID_RE = re.compile(r"#((?:exr|thm|lem|prp|cor|exm|def|sol)-[\w-]*\w)")
SOL_RE = re.compile(r"#sol-|\.(?:sol|solution|answer)(?![\w-])")
ATTR_TITLE_RE = re.compile(r'title="([^"]*)"')
TITLE_RE = re.compile(r"^#{1,6}\s+(.*?)\s*(?:\{[^}]*\})?\s*$")
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
MATH_RE = re.compile(r"\$[^$]*\$")
LINK_RE = re.compile(r"\]\([^)]*\)")
WORD_RE = re.compile(r"[a-z]+")
STEM = 5

# Task verbs and connecting words that a title may use without the body
# repeating them.
GENERIC = frozenset("""
    about above after again against also another answer apply approximate
    ask assess based before below between both calculate change check choose
    classify compare compute conclude confirm connect consider construct
    count decide define demonstrate derive describe determine differentiate
    does each estimate evaluate every example exercise explain express
    extend find first from give given having how identify implement
    include interpret into justify list make many match more most name
    need other over part plot predict prove read recognize relate rewrite
    same say second see select show simplify solve some state step steps
    still such take test than that their them then there these they this
    those three through time under until use used using value values
    verify what when where whether which while whose will with within
    without work write your
""".split())


GENERIC_STEMS = frozenset(w[:STEM] for w in GENERIC)


class Finding(NamedTuple):
    line: int
    title: str
    missing: List[str]
    start: int
    end: int


def _words(text: str) -> List[str]:
    text = MATH_RE.sub(" ", text)
    text = LINK_RE.sub("]", text)
    return WORD_RE.findall(text.lower())


def _stems(words: List[str]) -> Set[str]:
    return {w[:STEM] for w in words if len(w) >= 3}


def defined_stems(lines: List[str]) -> Set[str]:
    """Stems of the words in the titles of the ``#def-`` divs in ``lines``."""
    stems: Set[str] = set()
    for idx, raw in enumerate(lines):
        dm = DIV_RE.match(raw)
        if not (dm and dm.group(2) and DEF_RE.search(dm.group(2))):
            continue
        attr_title = ATTR_TITLE_RE.search(dm.group(2))
        if attr_title:
            stems |= _stems(_words(attr_title.group(1)))
            continue
        for follow in lines[idx + 1:idx + 4]:
            tm = TITLE_RE.match(follow)
            if tm:
                stems |= _stems(_words(tm.group(1)))
                break
    return stems


def missing_words(title: str, body: str,
                  defined: Optional[Set[str]] = None) -> List[str]:
    """Content words of ``title`` with no counterpart in ``body``.

    With ``defined`` given, only a word that is a defined term (a word in the
    title of some ``#def-`` div) is reported: the rule is about the background
    of technical terms, and an ordinary word needs none.
    """
    present = _stems(_words(body))
    out: List[str] = []
    for word in _words(title):
        if len(word) < 4 or word[:STEM] in GENERIC_STEMS:
            continue
        if defined is not None and word[:STEM] not in defined:
            continue
        singular = word[:-1] if word.endswith("s") else word
        if word[:STEM] in present or singular[:STEM] in present or word in out:
            continue
        out.append(word)
    return out


def div_texts(lines: List[str]) -> Dict[str, str]:
    """The text of each div with a cross-reference id in ``lines``, by id.

    An exercise's text is its title and body without solutions, the background
    a later exercise that cites it can lean on.
    """
    texts: Dict[str, str] = {}
    stack: List[Tuple[Optional[str], bool, List[str]]] = []
    fence: Optional[str] = None
    for raw in lines:
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                im = ID_RE.search(dm.group(2))
                title = ATTR_TITLE_RE.search(dm.group(2))
                buf = [title.group(1)] if title else []
                sol = bool(SOL_RE.search(dm.group(2)))
                stack.append((im.group(1) if im else None, sol, buf))
            elif stack:
                ident, sol, buf = stack.pop()
                text = "\n".join(buf)
                if ident:
                    texts[ident] = text
                if not sol:
                    for _, _, outer in stack[-1:]:
                        outer.append(text)
            continue
        for _, _, buf in stack[-1:]:
            buf.append(raw)
    return texts


def background(body: str, index: Dict[str, str],
               own: Optional[str] = None) -> Optional[str]:
    """The text of the divs ``body`` builds on, followed transitively.

    Returns None when ``body`` cites an exercise ``index`` does not hold:
    its background is elsewhere, so no title word can be judged missing.
    """
    seen: Set[str] = {own} if own else set()
    parts: List[str] = []
    todo = [body]
    while todo:
        for exr, other in REF_RE.findall(todo.pop()):
            ident = exr or other
            if ident in seen:
                continue
            seen.add(ident)
            if ident not in index:
                if exr:
                    return None
                continue
            parts.append(index[ident])
            todo.append(index[ident])
    return "\n".join(parts)


def exercises(lines: List[str], defined: Optional[Set[str]] = None,
              index: Optional[Dict[str, str]] = None) -> List[Finding]:
    """Each exercise div whose title has a defined term its body never uses."""
    if index is None:
        index = div_texts(lines)
    found: List[Finding] = []
    fence: Optional[str] = None
    in_comment = False
    depth = 0
    cur: Optional[Dict] = None
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if raw.lstrip().startswith("<!--"):
            in_comment = "-->" not in raw
            continue
        fm = FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            continue
        dm = DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                attrs = dm.group(2)
                if cur is None and EXR_RE.search(attrs):
                    attr_title = ATTR_TITLE_RE.search(attrs)
                    own_id = re.search(r"#(exr-[\w-]+)", attrs)
                    cur = {"depth": depth, "start": lineno, "skip": None,
                           "title": attr_title.group(1) if attr_title else None,
                           "title_line": lineno, "body": [],
                           "id": own_id.group(1) if own_id else None}
                elif cur is not None:
                    if cur["skip"] is None and SOL_RE.search(attrs):
                        cur["skip"] = depth
                    if cur["skip"] is None:
                        cur["body"].append(raw)
                depth += 1
            elif depth > 0:
                depth -= 1
                if cur is not None and depth == cur["depth"]:
                    missing = []
                    body = "\n".join(cur["body"])
                    extra = background(body, index, cur["id"])
                    if (cur["title"] and extra is not None
                            and not CONTINUATION_RE.search(body)):
                        missing = missing_words(cur["title"], body + "\n" + extra,
                                                defined)
                    if missing:
                        found.append(Finding(cur["title_line"], cur["title"], missing,
                                             cur["start"], lineno))
                    cur = None
                elif cur is not None:
                    if cur["skip"] == depth:
                        cur["skip"] = None
                    elif cur["skip"] is None:
                        cur["body"].append(raw)
            continue
        if cur is None or cur["skip"] is not None:
            continue
        tm = TITLE_RE.match(raw)
        if tm and cur["title"] is None and not any(b.strip() for b in cur["body"]):
            cur["title"] = tm.group(1)
            cur["title_line"] = lineno
            continue
        cur["body"].append(raw)
    return found


def added_lines(diff: str) -> Dict[str, Set[int]]:
    """Added line numbers per path from ``git diff -U0`` output."""
    added: Dict[str, Set[int]] = {}
    path: Optional[str] = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].rstrip("\t")
            path = None if target == "/dev/null" else target.removeprefix("b/")
            if path is not None:
                added.setdefault(path, set())
            continue
        m = HUNK_RE.match(line)
        if m and path is not None:
            start = int(m.group(1))
            count = 1 if m.group(2) is None else int(m.group(2))
            added[path].update(range(start, start + count))
    return added


def _git(args: List[str]) -> Optional[str]:
    res = subprocess.run(["git", "-c", "core.quotepath=false", *args],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace")
    return res.stdout if res.returncode == 0 else None


def wanted_lines(base_ref: str, globs: List[str], whole_tree: bool
                 ) -> Optional[Dict[str, Optional[Set[int]]]]:
    """Files to scan, each with its added lines (None = every line)."""
    if whole_tree:
        out = _git(["ls-files", "--", *globs])
        return None if out is None else {p: None for p in out.splitlines() if p}
    if not base_ref:
        return None
    base = _git(["merge-base", base_ref, "HEAD"])
    if not base or not base.strip():
        return None
    diff = _git(["diff", "-U0", "--no-color", "--no-ext-diff", base.strip(),
                 "--", *globs])
    return None if diff is None else dict(added_lines(diff))


def corpus(globs: List[str]) -> Tuple[Set[str], Dict[str, str]]:
    """Defined-term stems, and the text of each cross-referenced div, from
    every tracked file the globs match."""
    out = _git(["ls-files", "--", *globs]) or ""
    stems: Set[str] = set()
    index: Dict[str, str] = {}
    for rel in out.splitlines():
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        stems |= defined_stems(lines)
        index.update(div_texts(lines))
    return stems, index


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


def touched(finding: Finding, keep: Optional[Set[int]]) -> bool:
    """Whether the diff adds a line of the exercise."""
    if keep is None:
        return True
    return any(finding.start <= n <= finding.end for n in keep)


def main() -> int:
    base_ref = os.environ.get("EXB_BASE_REF", "").strip()
    globs = os.environ.get("EXB_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = _flag("EXB_FAIL", False)
    whole = _flag("EXB_WHOLE_TREE", False)
    wanted = wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the exercise background check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    findings = 0
    defined, index = corpus(globs)
    if not defined:
        print("::notice::No #def- titles found in the scanned files, so no title word can be "
              "reported as a defined term; the check reports nothing.")
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        for item in exercises(lines, defined, index):
            if touched(item, wanted[rel]):
                findings += 1
                words = ", ".join(item.missing)
                print(f"::{severity} file={rel},line={item.line}::Exercise title "
                      f"'{item.title[:50]}' uses {words}, which the body never "
                      f"mentions. Fix: {ADVICE}")
    print(f"Examined {len(wanted)} file(s); {findings} exercise(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
