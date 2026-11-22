#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag a geometric claim in prose that has no figure nearby.

The lab's rule (Ezra, 2026-11-16): every geometric claim in course notes,
such as "the loss term has elliptical contours" or "the penalty has circular
contours centered at the origin", is paired with a graphical illustration
nearby.

A line is a geometric claim when its prose (outside code fences, HTML
comments, and ``$...$`` math) uses geometric vocabulary matched by
``CLAIM_RE``: contour, ellipse, circle, level set or curve, tangent line,
hyperplane, decision boundary, perpendicular, "projects onto", "geometric
interpretation", "right angle". The list is deliberately narrow: convex,
angle, orthogonal and projection alone are ordinary algebra and are not
matched.

The claim has a figure when one of these lies within ``GEOM_WINDOW`` lines
(default 40) of it in the same file, or anywhere in a div that encloses it:
an image, a ``fig-`` labeled chunk or div, an ``@fig-`` reference, or an
include of a ``_fig`` subfile (the test ``check-exm-figures`` uses).
``<!-- no-figure: reason -->`` in the same span exempts a claim that no
figure can show; the reason is required.

A second rule (Ezra, 2026-11-22): a ``#def-`` div whose title or bold term
names a geometric object (``GEOM_TERM_RE``: curve, plane, distance, margin,
boundary, region and the rest) is followed by an example with a figure.
``check_definitions`` finds the next ``#exm-`` div after the definition,
following ``include`` shortcodes in the definition's file and, for a
subfile, in each parent page after its include. It stops at the next
definition, result, exercise or solution, and reports the definition when
the diff touches the definition or that example. The example's own
``no-figure`` marker does not excuse it, because the rule is that the
definition gets a figure; a ``no-figure`` marker inside the definition does.

Why a check can only approximate the rule: it sees that *a* figure is near
the claim, not that the figure shows *this* claim. The Claude review prompt
carries the second half (see psw ``chapters/teaching.qmd``).

Design notes, as in ``check-visualization-figures``, whose div parser this
script reuses:

- **Diff-scoped by default**: only a claim on a line the diff adds is
  reported; an added line whose exact text was also deleted is moved.
- **One finding per paragraph**: the first claim line of a paragraph.
- **Skip, not fall back** when there is no base to diff against;
  ``GEOM_WHOLE_TREE=true`` scans every tracked file.
- **Blocking by default** (``GEOM_FAIL`` defaults to true).

Configuration (environment variables, set by the composite action):
  GEOM_BASE_REF      Git ref/SHA to diff against.
  GEOM_GLOBS         Space-separated git pathspecs (default: '*.qmd').
  GEOM_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  GEOM_FAIL          "false" => warn only; default "true".
  GEOM_WHOLE_TREE    "true" => scan every tracked matching file in full.
  GEOM_WINDOW        Lines either side of a claim searched for a figure.
"""

import importlib.util
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_sibling(name: str):
    """Import a sibling check's script, whose directory name has hyphens."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, os.pardir, name, name + ".py")
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402

viz = _load_sibling("check-visualization-figures")
exf = _load_sibling("check-exm-figures")
ods = viz.ods

DEFAULT_GLOBS = "*.qmd"
DEFAULT_WINDOW = 40
_DEFAULT_FAIL = True

ADVICE = (
    "add a figure that shows it within a few lines (a plot, a diagram, or a "
    "`_fig` include), or add <!-- no-figure: reason --> if nothing can show it"
)

CLAIM_RE = re.compile(
    r"\bcontours?\b"
    r"|\bellips\w*|\belliptical\b"
    r"|\bcircles?\b|\bcircular\b"
    r"|\blevel\s+(?:sets?|curves?|surfaces?)\b"
    r"|\btangent\s+(?:to|line|plane|at)\b"
    r"|\bhyperplanes?\b"
    r"|\bdecision\s+boundar(?:y|ies)\b"
    r"|\bperpendicular\b"
    r"|\bproject(?:s|ed|ion)?\s+onto\b"
    r"|\bgeometric(?:ally)?\s+(?:interpretation|picture|view)\b|\bgeometrically\b"
    r"|\bright\s+angles?\b",
    re.IGNORECASE,
)
INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")
EXEMPT_RE = re.compile(r"<!--\s*no-figure:\s*(?!-->)\S")


def prose_of(lines: List[str]) -> List[Optional[str]]:
    """Each line's prose, or None inside code fences, comments, display math."""
    out: List[Optional[str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_math = False
    for raw in lines:
        if fence is None:
            text, in_comment = ods.strip_comments(raw, in_comment)
        else:
            text = raw
        m = ods.FENCE_RE.match(text)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            out.append(None)
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            out.append(None)
            continue
        if text.count("$$") % 2 == 1:
            in_math = not in_math
            out.append(None)
            continue
        if in_math or ods.DIV_RE.match(text) or viz.HEADING_RE.match(text):
            out.append(None)
            continue
        out.append(INLINE_MATH_RE.sub(" ", text))
    return out


def has_figure_or_exemption(body: List[str]) -> bool:
    return exf.has_figure(body) or any(EXEMPT_RE.search(x) for x in body)


def check_lines(lines: List[str], keep: Optional[Set[int]],
                window: int = DEFAULT_WINDOW) -> Tuple[List[int], int]:
    """1-based lines of unpaired claims (first per paragraph) and claim count."""
    prose = prose_of(lines)
    divs = viz.scan_divs(lines)
    missing: List[int] = []
    seen = 0
    paragraph_done = False
    for idx, text in enumerate(prose):
        if not lines[idx].strip():
            paragraph_done = False
            continue
        if text is None or not CLAIM_RE.search(text):
            continue
        seen += 1
        n = idx + 1
        if paragraph_done or (keep is not None and n not in keep):
            continue
        near = lines[max(0, idx - window):idx + window + 1]
        if has_figure_or_exemption(near):
            continue
        if any(d.start <= n <= d.end
               and has_figure_or_exemption(lines[d.start - 1:d.end])
               for d in divs):
            continue
        missing.append(n)
        paragraph_done = True
    return missing, seen


# --- Geometric definitions (Ezra, 2026-11-22) ------------------------------
# A definition of a term that names a geometric object is followed by an
# example with a figure. The term is the div's title or a bold phrase in it.

GEOM_TERM_RE = re.compile(
    r"\bcurves?\b|\bsurfaces?\b|\b(?:hyper)?planes?\b|\bhalf-?spaces?\b"
    r"|\bdistances?\b|\bmargins?\b|\bboundar(?:y|ies)\b|\bregions?\b"
    r"|\bcontours?\b|\blevel\s+sets?\b|\bcircles?\b|\bellipses?\b"
    r"|\bspheres?\b|\bballs?\b|\bangles?\b|\bpolygons?\b|\bpolytopes?\b"
    r"|\bconvex\s+hulls?\b|\bprojections?\b|\bline\s+segments?\b"
    r"|\bsimplex\b|\bsimplices\b|\bcones?\b|\bmanifolds?\b",
    re.IGNORECASE,
)
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
INCLUDE_RE = re.compile(r"\{\{<\s*include\s+(\S+?)\s*>\}\}")
RESULT_PREFIXES = ("def-", "thm-", "lem-", "prp-", "cor-", "exr-", "sol-",
                   "cnj-", "conj-")
ID_RE = re.compile(r"#([a-z]+-[\w:.-]+)")

DEF_ADVICE = (
    "add a figure that draws the object to the example after the definition "
    "(a plot, a diagram, or a `_fig` include), or add "
    "<!-- no-figure: reason --> inside the definition if nothing can show it"
)


def div_id(attrs: str) -> str:
    m = ID_RE.search(attrs)
    return m.group(1) if m else ""


def geometric_term(lines: List[str], div) -> Optional[str]:
    """The geometric word in a definition's title or bold terms, if any."""
    texts = [viz.title_of(lines, div)]
    for raw in lines[div.start:div.end - 1]:
        texts.extend(BOLD_RE.findall(raw))
    for text in texts:
        text = LINK_TARGET_RE.sub("]", text or "")  # a URL is not the term
        m = GEOM_TERM_RE.search(text)
        if m:
            return m.group(0)
    return None


def code_and_comment_mask(lines: List[str]) -> List[Optional[str]]:
    """Each line without HTML comments, or None inside a code fence."""
    out: List[Optional[str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    for raw in lines:
        if fence is None:
            text, in_comment = ods.strip_comments(raw, in_comment)
        else:
            text = raw
        m = ods.FENCE_RE.match(text)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not m.group(2).strip()):
                fence = None
            out.append(None)
            continue
        if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = (m.group(1)[0], len(m.group(1)))
            out.append(None)
            continue
        out.append(text)
    return out


def resolve_include(including: str, target: str) -> str:
    """The repository path an include shortcode in ``including`` names."""
    if target.startswith("/"):
        return os.path.normpath(target.lstrip("/"))
    return os.path.normpath(os.path.join(os.path.dirname(including), target))


class Found(NamedTuple):
    path: str
    lines: List[str]
    div: object  # viz.Div


class Walk(NamedTuple):
    example: Optional[Found]
    reached_end: bool


def first_theorem_div(lines: List[str]):
    """The first top-level theorem-type div of a file, or None."""
    divs = sorted(viz.scan_divs(lines), key=lambda d: d.start)
    for d in divs:
        if any(o.start < d.start and d.end < o.end for o in divs):
            continue
        ident = div_id(d.attrs)
        if ident.startswith("exm-") or ident.startswith(RESULT_PREFIXES):
            return d
    return None


def walk_after(path: str, lines: List[str], after: int,
               reader, depth: int = 0) -> Walk:
    """The first example after 1-based line ``after``, following includes.

    Stops at the next definition, result, exercise or solution, because the
    example a definition needs comes right after it.
    """
    masked = code_and_comment_mask(lines)
    divs = {d.start: d for d in viz.scan_divs(lines)}
    idx = after  # 0-based index of the line after ``after``
    while idx < len(lines):
        text = masked[idx]
        n = idx + 1
        if text is None:
            idx += 1
            continue
        d = divs.get(n)
        if d is not None:
            ident = div_id(d.attrs)
            if ident.startswith("exm-"):
                return Walk(Found(path, lines, d), False)
            if ident.startswith(RESULT_PREFIXES):
                return Walk(None, False)
            idx = d.end
            continue
        inc = INCLUDE_RE.search(text)
        if inc and "{{</*" not in text and depth < 5:
            target = resolve_include(path, inc.group(1))
            sub = reader(target)
            if sub is not None:
                d = first_theorem_div(sub)
                if d is not None:
                    if div_id(d.attrs).startswith("exm-"):
                        return Walk(Found(target, sub, d), False)
                    return Walk(None, False)
        idx += 1
    return Walk(None, True)


def next_example(path: str, lines: List[str], div, reader,
                 parents) -> Optional[Found]:
    """The example after a definition, in its file or after its include."""
    walk = walk_after(path, lines, div.end, reader)
    if walk.example is not None or not walk.reached_end:
        return walk.example
    for parent, line in parents(path):
        plines = reader(parent)
        if plines is None:
            continue
        found = walk_after(parent, plines, line, reader).example
        if found is not None:
            return found
    return None


def touched(keep: Optional[Set[int]], start: int, end: int) -> bool:
    return keep is None or any(start <= n <= end for n in keep)


def check_definitions(files: Dict[str, List[str]],
                      wanted: Optional[Dict[str, Optional[Set[int]]]]
                      ) -> Tuple[List[Tuple[str, int, str]], int]:
    """Geometric definitions whose next example has no figure.

    ``files`` maps every scanned path to its lines; ``wanted`` maps the paths
    a diff touched to their added lines (None for the whole tree). A
    definition is reported when the diff touches it or its example.
    """
    def reader(rel: str) -> Optional[List[str]]:
        if rel in files:
            return files[rel]
        got = diffscope.read_lines(rel)
        if got is not None:
            files[rel] = got
        return got

    index: Dict[str, List[Tuple[str, int]]] = {}
    for rel, content in list(files.items()):
        for i, text in enumerate(code_and_comment_mask(content)):
            inc = INCLUDE_RE.search(text or "")
            if inc and "{{</*" not in text:
                index.setdefault(resolve_include(rel, inc.group(1)),
                                 []).append((rel, i + 1))

    def parents(rel: str) -> List[Tuple[str, int]]:
        return index.get(os.path.normpath(rel), [])

    def keep_of(rel: str) -> Tuple[bool, Optional[Set[int]]]:
        if wanted is None:
            return True, None
        if rel not in wanted:
            return False, set()
        return True, wanted[rel]

    findings: List[Tuple[str, int, str]] = []
    seen = 0
    for rel in sorted(files):
        content = files[rel]
        for d in viz.scan_divs(content):
            if not div_id(d.attrs).startswith("def-"):
                continue
            word = geometric_term(content, d)
            if word is None:
                continue
            seen += 1
            body = content[d.start - 1:d.end]
            if any(EXEMPT_RE.search(x) for x in body):
                continue
            example = next_example(rel, content, d, reader, parents)
            if example is None:
                continue  # check-example-after-def's job
            in_def, keep = keep_of(rel)
            hit = in_def and touched(keep, d.start, d.end)
            in_ex, ex_keep = keep_of(example.path)
            ex = example.div
            hit = hit or (in_ex and touched(ex_keep, ex.start, ex.end))
            if not hit:
                continue
            if exf.has_figure(example.lines[ex.start - 1:ex.end]):
                continue
            findings.append((rel, d.start, (
                f"Definition of a geometric term (\"{word}\") is followed by "
                f"an example ({div_id(ex.attrs)}, {example.path}) with no "
                f"figure. Fix: {DEF_ADVICE}")))
    return findings, seen


def format_message(text: str) -> str:
    match = CLAIM_RE.search(text)
    word = match.group(0) if match else "geometric word"
    return (f"Geometric claim (\"{word}\") has no figure nearby. "
            f"Fix: {ADVICE}")


class Report(NamedTuple):
    findings: List[Tuple[str, int, str]]  # (path, line, line text)
    files: int
    lines: int
    claims: int
    skipped: bool
    definitions: List[Tuple[str, int, str]] = []  # (path, line, message)
    geometric_defs: int = 0


def run_check(base_ref: str, globs: List[str], ignores: list,
              whole_tree: bool, window: int) -> Report:
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        out = diffscope.git_paths(["ls-files", "--", *globs])
        if out is None:
            return Report([], 0, 0, 0, True)
        for rel in out:
            if rel and not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = diffscope.run_git(["diff", "-U0", "--no-color", "--no-ext-diff",
                                  base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if text.strip() and text not in deleted}

    findings: List[Tuple[str, int, str]] = []
    files = lines = claims = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        missing, seen = check_lines(content, keep, window)
        claims += seen
        findings.extend((rel, n, content[n - 1]) for n in missing)

    tracked = diffscope.git_paths(["ls-files", "--", *globs]) or []
    corpus: Dict[str, List[str]] = {}
    for rel in tracked:
        if rel and not diffscope.ignored(rel, ignores):
            got = diffscope.read_lines(rel)
            if got is not None:
                corpus[rel] = got
    defs, geo_defs = check_definitions(corpus, None if whole_tree else wanted)
    return Report(findings, files, lines, claims, False, defs, geo_defs)


def main() -> int:
    base_ref = os.environ.get("GEOM_BASE_REF", "").strip()
    globs = os.environ.get("GEOM_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("GEOM_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("GEOM_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("GEOM_WHOLE_TREE", False)
    try:
        window = int(os.environ.get("GEOM_WINDOW", DEFAULT_WINDOW))
    except ValueError:
        window = DEFAULT_WINDOW

    report = run_check(base_ref, globs, ignores, whole_tree, window)

    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the geometric-figure check for this run "
              f"({reason}; not falling back to a whole-tree scan).")
        return 0

    scope = "whole tree" if whole_tree else f"lines added since {base_ref}"
    print(f"Examined {report.lines} line(s) across {report.files} file(s), "
          f"{report.claims} geometric claim line(s) (scope: {scope}).")
    severity = "error" if fail else "warning"
    print(f"Found {report.geometric_defs} definition(s) of a geometric term.")
    for rel, line, text in report.findings:
        print(f"::{severity} file={rel},line={line}::{format_message(text)}")
    for rel, line, message in report.definitions:
        print(f"::{severity} file={rel},line={line}::{message}")
    if not report.findings and not report.definitions:
        print("Every examined geometric claim has a figure nearby or a stated "
              "exemption, and every examined geometric definition's example "
              "has a figure.")
        return 0
    if report.findings:
        print(f"\n{len(report.findings)} geometric claim(s) have no figure nearby.")
    if report.definitions:
        print(f"\n{len(report.definitions)} geometric definition(s) have an "
              "example with no figure.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
