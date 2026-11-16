#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a reference to a section, chapter or page by its title that does not
name the content type.

The lab's rule (Ezra, 2026-11-16, psw#660): when text refers to a section,
subsection, chapter, page and so on by its title, it names the type of content,
and only the title is the link text. Write "the [Practical
considerations](#practical-considerations) section", not "see [Practical
considerations](#practical-considerations)".

Flagged, on a line the diff adds: a Markdown link to an internal target
(``#anchor``, ``page.qmd#anchor``, ``page.html#anchor`` or ``page.qmd``) whose
text equals the title of the heading that target names (or, for a bare page
link, the page's ``title:``), when no type word sits immediately before or
after the link. A ``@sec-`` crossref renders its own "Section n" label, so it
passes; a link to a ``#def-`` or ``#thm-`` div does not target a heading, so a
term link never matches.

Not checkable: a book, article or video, whose title lives off-site. The psw
reviewer instruction covers those.

The heading index is read from every tracked ``.qmd`` file and keyed by the
anchor alone (a heading's explicit ``{#id}`` or its Pandoc slug) and, for
pages, by the file's base name, so the scan needs no path for the line it
reads. It skips code fences, code spans, HTML comments and front matter, and a
line carrying, or following, ``<!-- check-title-references: allow -->``.

The diff model, masking, skip-not-fall-back and failing default come from
``check-write-idiom``'s engine, as in ``check-avoided-words``; only the rule,
the index and the ``CTR_`` env prefix are its own.

Configuration (environment variables, set by the composite action):
  CTR_BASE_REF, CTR_GLOBS, CTR_PATHS_IGNORE, CTR_FAIL, CTR_WHOLE_TREE
as for ``check-write-idiom`` (see its docstring).
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_HERE = Path(__file__).resolve().parent
_ENGINE_PATH = _HERE.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)
diffscope = engine.diffscope

DEFAULT_GLOBS = engine.DEFAULT_GLOBS
_DEFAULT_FAIL = True
ALLOW_RE = re.compile(r"<!--\s*check-title-references:\s*allow\s*-->")

TYPE_WORDS = (
    "section|subsection|subsubsection|chapter|page|part|appendix|lecture|"
    "handout|unit|module"
)
BEFORE_RE = re.compile(
    r"(?i)\b(?:" + TYPE_WORDS + r")s?\s*(?:titled|called|named|entitled)?"
    r"\s*[\"'“‘]?\s*$"
)
AFTER_RE = re.compile(
    r"(?i)^[\"'”’]?\s*(?:" + TYPE_WORDS + r")s?\b"
)
LINK_RE = re.compile(
    r"(?<!!)\[(?P<text>[^\[\]]+)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)"
)
HEADING_RE = re.compile(r"^#{1,6}[ \t]+(\S.*?)(?:[ \t]+#+)?[ \t]*$")
ATTR_RE = re.compile(r"\s*\{([^{}]*)\}\s*$")
ID_RE = re.compile(r"#([\w:.-]+)")
TITLE_RE = re.compile(r"""^title:\s*(?:"(.*)"|'(.*)'|(.*?))\s*$""")

ADVICE = (
    "name the content type and link only the title, as in 'the [Title](#id) "
    "section' (psw#660), or add <!-- check-title-references: allow -->"
)


# A heading or table caption is the title itself, so a type word is out of place.
HEADING_OR_CAPTION_RE = re.compile(r"^\s*(#{1,6}\s|:\s)")


class Finding(NamedTuple):
    line: int
    rule: str
    phrase: str


def normalize(text: str) -> str:
    """Link or heading text without markup, in its own case.

    A link is a title reference only when its text is written as the title.
    A lowercase concept link such as ``[logistic regression](x.qmd)`` to a
    chapter titled "Logistic regression" is ordinary prose (gha#2054).
    """
    plain = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", plain).strip().strip("\"'").rstrip(".:")


def slugify(text: str) -> str:
    """Pandoc's automatic heading identifier."""
    plain = re.sub(r"[*_`]", "", text).lower()
    plain = re.sub(r"[^\w\s.-]", "", plain)
    plain = re.sub(r"\s+", "-", plain.strip())
    return re.sub(r"^[^a-z]+", "", plain)


def file_headings(lines: List[str]) -> Tuple[List[Tuple[str, str]], Optional[str]]:
    """(anchor, normalized title) for each heading, and the page title."""
    out: List[Tuple[str, str]] = []
    title: Optional[str] = None
    fence: Optional[str] = None
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines):
        if in_front:
            if number > 0 and raw.strip() in ("---", "..."):
                in_front = False
            elif number > 0:
                m = TITLE_RE.match(raw)
                if m:
                    title = normalize(m.group(1) or m.group(2) or m.group(3) or "")
            continue
        fm = re.match(r"^\s*(`{3,}|~{3,})", raw)
        if fm:
            marker = fm.group(1)[0]
            fence = None if fence == marker else (fence or marker)
            continue
        if fence:
            continue
        hm = HEADING_RE.match(raw)
        if not hm:
            continue
        body = hm.group(1)
        explicit = None
        am = ATTR_RE.search(body)
        if am:
            im = ID_RE.search(am.group(1))
            explicit = im.group(1) if im else None
            body = ATTR_RE.sub("", body)
        text = normalize(body)
        out.append((explicit or slugify(body), text))
    return out, title


_INDEX: Optional[Tuple[Dict[str, Set[str]], Dict[str, str]]] = None


def build_index() -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    """Anchor -> titles, and file base name -> page title, over tracked qmd."""
    anchors: Dict[str, Set[str]] = {}
    pages: Dict[str, str] = {}
    paths = diffscope.git_paths(["ls-files", "--", "*.qmd"]) or []
    for rel in paths:
        lines = diffscope.read_lines(rel)
        if lines is None:
            continue
        headings, title = file_headings(lines)
        for anchor, text in headings:
            anchors.setdefault(anchor, set()).add(text)
        if title:
            pages.setdefault(os.path.basename(rel), title)
    return anchors, pages


def index() -> Tuple[Dict[str, Set[str]], Dict[str, str]]:
    global _INDEX
    if _INDEX is None:
        _INDEX = build_index()
    return _INDEX


def reset_index() -> None:
    global _INDEX
    _INDEX = None


def target_titles(target: str) -> Set[str]:
    """Titles the internal ``target`` names; empty for an external one."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
        return set()
    anchors, pages = index()
    path, _, anchor = target.partition("#")
    if not path and anchor:
        return anchors.get(anchor, set())
    if path.endswith((".qmd", ".html")):
        if anchor:
            return anchors.get(anchor, set())
        page = pages.get(os.path.splitext(os.path.basename(path))[0] + ".qmd")
        return {page} if page else set()
    return set()


def _find(masked: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if HEADING_OR_CAPTION_RE.match(masked):
        return out
    for m in LINK_RE.finditer(masked):
        text = normalize(m.group("text"))
        if not text or text not in target_titles(m.group("target")):
            continue
        if BEFORE_RE.search(masked[:m.start()]) or AFTER_RE.match(masked[m.end():]):
            continue
        out.append(("title-ref", m.group("text")))
        break
    return out


def scan_file(lines: List[str]) -> Tuple[List[Finding], int]:
    """``([Finding, ...], lines examined)`` for a Markdown-family file."""
    hits, examined = engine.scan_markdown(lines, _find, ALLOW_RE)
    return [Finding(n, rule, phrase) for n, (rule, phrase) in hits], examined


def format_message(finding: Finding) -> str:
    return (f"Link text '{finding.phrase}' is a heading title with no content "
            f"type beside it. Fix: {ADVICE}")


def main() -> int:
    return engine.main(
        scan=scan_file, prefix="CTR_", name="title-references",
        clean="No link names a heading title without its content type.",
        summary="refer to a title without naming its content type.",
        format_finding=format_message, default_fail=_DEFAULT_FAIL)


if __name__ == "__main__":
    sys.exit(main())
