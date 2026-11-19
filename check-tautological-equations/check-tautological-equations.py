#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an equation whose two sides render identically.

A definition such as ``\bform{\matr{A}}{\vx}{\vy} \eqdef \tp{\vx} \matr{A} \vy``
reads well in the source, but ``\bform`` expands to ``\tp{#2} #1 #3``, so the
reader sees the same glyphs on both sides of the definitional equals: a
tautology that says nothing (Morrison-Lab/mds#835, Ezra 2026-11-19).  The
check expands the shared macros on each side of an equality and compares what
TeX would typeset.

How a side is normalized:

- every macro defined in the macros file (``TE_MACROS_FILE``, default
  ``latex-macros/macros.qmd``; several paths may be given) is expanded, with
  its arguments, until none is left;
- spacing (``\,``, ``\;``, ``\quad``, whitespace, ``~``), sizing
  (``\left``, ``\right``, ``\big`` and kin), ``\mathopen{}``-style empty
  groups, ``\tag``, ``\label`` and ``\nonumber`` are dropped, because they do
  not change which glyphs appear;
- a group around one token is unwrapped (``x^{2}`` is ``x^2``);
- trailing punctuation (``.``, ``,``, ``;``) is dropped.

Which relations are compared: ``=``, ``:=``, ``=:``, ``\coloneqq``,
``\eqqcolon``, ``\equiv``, ``\triangleq``, ``\doteq``, an ``=`` under
``\stackrel``, ``\overset`` or ``\underset``, and any argument-free macro that
expands to one of those (``\eqdef``).  Only a relation at the top level of the
equation is a split point: one inside braces, parentheses, ``\left...\right``
or an environment other than an alignment (``aligned``, ``align``, ``split``,
``gathered`` and kin) belongs to a subexpression such as ``\Pr(X = x)``.  In an
alignment, ``&`` is ignored and a row that opens with a relation continues the
chain of the row before it.  Each pair of neighbouring sides in a chain is
compared.

What is checked: ``$...$`` and ``$$...$$`` math in ``.qmd``, ``.Rmd`` and
``.md`` files.  What is not: code fences and spans, HTML comments, YAML front
matter, math that defines a macro, and an equation carrying, or following,
``<!-- check-tautological-equations: allow -->`` (for a reflexivity example).

Design notes, in the model of ``check-macro-expansions``:

- **Diff-scoped by default.** An equation is reported when a line of it was
  added since ``TE_BASE_REF``; an added line whose exact text was also deleted
  counts as moved.  ``TE_WHOLE_TREE=true`` scans everything.
- **Skip, not fall back.** With no base ref, or when the diff cannot be
  computed, the check skips with a warning instead of scanning the whole tree.
  A missing macros file also skips, since without it nothing expands.
- **Blocking by default** (``TE_FAIL`` defaults to true): a tautology is
  never what the writer meant.
- **The search space is reported.** Every run prints how many files, lines,
  equations and macros it examined.

Configuration (environment variables, set by the composite action):
  TE_BASE_REF      Git ref/SHA to diff against.  Empty and not whole-tree =>
                   skip the check.
  TE_MACROS_FILE   Whitespace-separated paths of macros files.
  TE_GLOBS         Space-separated git pathspecs.
  TE_PATHS_IGNORE  Comma/newline-separated glob patterns to skip.
  TE_FAIL          "true" => exit 1 on a finding.
  TE_WHOLE_TREE    "true" => scan every tracked matching file in full.
"""

import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

_ENGINE_PATH = Path(__file__).resolve().parent.parent / "check-write-idiom" / "check-write-idiom.py"
_spec = importlib.util.spec_from_file_location("check_write_idiom_engine", _ENGINE_PATH)
assert _spec is not None and _spec.loader is not None
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "check-common"))
import diffscope  # noqa: E402
import mdmask  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_GLOBS = "*.qmd *.Rmd *.md"
DEFAULT_MACROS_FILE = "latex-macros/macros.qmd"
_DEFAULT_FAIL = True
# Expansion steps allowed for one side; a runaway (a recursive macro) gives up.
MAX_STEPS = 20000

ALLOW_RE = re.compile(r"<!--\s*check-tautological-equations:\s*allow\s*-->")
DEFINES_MACRO_RE = re.compile(
    r"\\(?:providecommand|newcommand|renewcommand|def|DeclareMathOperator)(?![A-Za-z])")

TOKEN_RE = re.compile(r"\\[A-Za-z]+\*?|\\.|#\d|\s+|.", re.S)

ALIGN_ENVS = {"aligned", "align", "align*", "alignat", "alignat*", "alignedat",
              "split", "gathered", "gather", "gather*", "eqnarray", "eqnarray*",
              "multline", "multline*", "equation", "equation*", "flalign",
              "flalign*"}
RELATION_WORDS = {"\\coloneqq", "\\eqqcolon", "\\equiv", "\\triangleq",
                  "\\doteq", "\\coloneq", "\\eqcolon"}
STACK_WORDS = {"\\stackrel", "\\overset", "\\underset"}
DROP_WORDS = {"\\,", "\\;", "\\:", "\\!", "\\ ", "\\>", "~", "\\quad", "\\qquad",
              "\\thinspace", "\\medspace", "\\thickspace", "\\negthinspace",
              "\\negmedspace", "\\negthickspace", "\\enspace",
              "\\mathopen", "\\mathclose", "\\left", "\\right", "\\middle",
              "\\big", "\\Big", "\\bigg", "\\Bigg", "\\bigl", "\\bigr",
              "\\Bigl", "\\Bigr", "\\biggl", "\\biggr", "\\Biggl", "\\Biggr",
              "\\bigm", "\\Bigm", "\\biggm", "\\Biggm",
              "\\displaystyle", "\\textstyle", "\\nonumber", "\\notag",
              "\\allowbreak", "\\relax"}
DROP_WITH_ARG = {"\\tag", "\\tag*", "\\label", "\\hspace", "\\hspace*",
                 "\\vphantom", "\\phantom", "\\hphantom", "\\kern", "\\mkern"}
TRAILING_PUNCT = {".", ",", ";"}
OPENERS = {"(": ")", "\\{": "\\}", "\\langle": "\\rangle", "\\lvert": "\\rvert",
           "\\lVert": "\\rVert"}
CLOSERS = {v: k for k, v in OPENERS.items()}


class Macro(NamedTuple):
    nargs: int
    default: Optional[List[str]]  # the optional first argument's default
    body: List[str]


class Finding(NamedTuple):
    line: int
    relation: str
    left: str
    right: str


# -- tokens ------------------------------------------------------------------

def tokenize(text: str) -> List[str]:
    """TeX tokens; a run of whitespace is one ``" "`` token."""
    out = []
    for tok in TOKEN_RE.findall(text):
        if tok.isspace():
            if out and out[-1] == " ":
                continue
            out.append(" ")
        else:
            out.append(tok)
    return out


def _skip_space(toks: List[str], i: int) -> int:
    while i < len(toks) and toks[i] == " ":
        i += 1
    return i


def read_group(toks: List[str], i: int) -> Tuple[Optional[List[str]], int]:
    """The argument starting at ``toks[i]``: a braced group's inside, or one token."""
    i = _skip_space(toks, i)
    if i >= len(toks):
        return None, i
    if toks[i] != "{":
        if toks[i] == "}":
            return None, i
        return [toks[i]], i + 1
    depth = 0
    for j in range(i, len(toks)):
        if toks[j] == "{":
            depth += 1
        elif toks[j] == "}":
            depth -= 1
            if depth == 0:
                return toks[i + 1:j], j + 1
    return None, len(toks)


def read_optional(toks: List[str], i: int) -> Tuple[Optional[List[str]], int]:
    """A ``[...]`` argument at ``toks[i]`` (skipping space), or ``None``."""
    j = _skip_space(toks, i)
    if j >= len(toks) or toks[j] != "[":
        return None, i
    depth = 0
    bdepth = 0
    for k in range(j, len(toks)):
        t = toks[k]
        if t == "{":
            depth += 1
        elif t == "}":
            depth -= 1
        elif depth == 0 and t == "[":
            bdepth += 1
        elif depth == 0 and t == "]":
            bdepth -= 1
            if bdepth == 0:
                return toks[j + 1:k], k + 1
    return None, i


# -- the macros file -----------------------------------------------------------

_HEAD_RE = re.compile(
    r"\\(?P<kind>providecommand|newcommand|renewcommand|DeclareMathOperator)\*?\s*"
    r"(?:\{\s*\\(?P<n1>[A-Za-z]+)\s*\}|\\(?P<n2>[A-Za-z]+))"
    r"|\\def\s*\\(?P<n3>[A-Za-z]+)(?P<params>(?:#\d)*)")


def load_macros(paths: List[str]) -> Optional[Dict[str, Macro]]:
    """Every macro the files define, or ``None`` when no file can be read."""
    macros: Dict[str, Macro] = {}
    read_any = False
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        read_any = True
        _parse_definitions(text, macros)
    return macros if read_any else None


def _parse_definitions(text: str, macros: Dict[str, Macro]) -> None:
    for m in _HEAD_RE.finditer(text):
        name = "\\" + (m.group("n1") or m.group("n2") or m.group("n3"))
        rest = tokenize(text[m.end():m.end() + 4000])
        nargs, default, i = 0, None, 0
        if m.group("n3"):
            nargs = len(m.group("params")) // 2
        elif m.group("kind") == "DeclareMathOperator":
            arg, _ = read_group(rest, 0)
            if arg is not None:
                macros[name] = Macro(0, None, ["\\operatorname", "{", *arg, "}"])
            continue
        else:
            count, i = read_optional(rest, 0)
            if count is not None:
                try:
                    nargs = int("".join(count).strip())
                except ValueError:
                    continue
                default, i = read_optional(rest, i)
        body, _ = read_group(rest, i)
        if body is None:
            continue
        if m.group("kind") == "providecommand" and name in macros:
            continue
        macros[name] = Macro(nargs, default, body)


# -- expansion and normalization -------------------------------------------------

def expand(toks: List[str], macros: Dict[str, Macro]) -> Optional[List[str]]:
    """``toks`` with every known macro expanded, or ``None`` on a runaway."""
    stack = list(reversed(toks))
    out: List[str] = []
    steps = 0
    while stack:
        tok = stack.pop()
        mac = macros.get(tok)
        if mac is None:
            out.append(tok)
            continue
        steps += 1
        if steps > MAX_STEPS:
            return None
        rest = list(reversed(stack))
        i = 0
        args: List[List[str]] = []
        if mac.default is not None:
            opt, i = read_optional(rest, i)
            args.append(mac.default if opt is None else opt)
        while len(args) < mac.nargs:
            arg, i = read_group(rest, i)
            if arg is None:
                return None
            args.append(arg)
        body: List[str] = []
        for b in mac.body:
            if re.fullmatch(r"#\d", b) and 0 < int(b[1]) <= len(args):
                body.extend(args[int(b[1]) - 1])
            else:
                body.append(b)
        # A control word swallows the space after it, so a body ending in one
        # must not glue onto the next letter: keep a separating space.
        stack = list(reversed(body + [" "] + rest[i:]))
    return out


def _drop_noise(toks: List[str]) -> List[str]:
    out: List[str] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == " " or t in DROP_WORDS:
            if t in ("\\left", "\\right", "\\middle"):
                j = _skip_space(toks, i + 1)
                if j < len(toks) and toks[j] == ".":
                    i = j + 1
                    continue
            i += 1
            continue
        if t in DROP_WITH_ARG:
            j = i + 1
            if t.startswith("\\kern") or t.startswith("\\mkern"):
                while j < len(toks) and toks[j] not in ("{",) and not toks[j].isalpha():
                    j += 1
                while j < len(toks) and toks[j].isalpha():
                    j += 1
                i = j
                continue
            _, i = read_group(toks, j)
            continue
        out.append(t)
        i += 1
    return out


def _unwrap(toks: List[str]) -> List[str]:
    """Remove empty groups and groups around a single token, to a fixed point."""
    changed = True
    while changed:
        changed = False
        out: List[str] = []
        i = 0
        while i < len(toks):
            if toks[i] == "{" and i + 1 < len(toks) and toks[i + 1] == "}":
                i += 2
                changed = True
                continue
            if (toks[i] == "{" and i + 2 < len(toks) and toks[i + 2] == "}"
                    and toks[i + 1] not in ("{", "}")):
                out.append(toks[i + 1])
                i += 3
                changed = True
                continue
            out.append(toks[i])
            i += 1
        toks = out
    return toks


def normalize(toks: List[str], macros: Dict[str, Macro]) -> Optional[str]:
    """What TeX would typeset for ``toks``, as a comparable string."""
    expanded = expand(toks, macros)
    if expanded is None:
        return None
    cleaned = _unwrap(_drop_noise(expanded))
    while cleaned and cleaned[-1] in TRAILING_PUNCT:
        cleaned.pop()
    # Separate a control word from a following letter, so `\alpha x` and
    # `\alphax` stay distinct.
    return " ".join(cleaned)


# -- splitting an equation into sides ---------------------------------------------

def _classify(tok: str, macros: Dict[str, Macro],
              cache: Dict[str, str]) -> str:
    """'relation', 'begin', 'end' or '' for an argument-free macro."""
    if tok in cache:
        return cache[tok]
    kind = ""
    mac = macros.get(tok)
    if mac is not None and mac.nargs == 0:
        body = expand(mac.body, macros) or []
        body = [b for b in body if b != " "]
        text = "".join(body)
        if text in ("=", ":=", "=:") or (len(body) == 1 and body[0] in RELATION_WORDS):
            kind = "relation"
        elif body and body[0] in STACK_WORDS and text.endswith("{=}"):
            kind = "relation"
        elif len(body) >= 4 and body[0] in ("\\begin", "\\end") and body[1] == "{":
            env = "".join(body[2:body.index("}")]) if "}" in body else ""
            if env in ALIGN_ENVS and body.index("}") == len(body) - 1:
                kind = body[0][1:]
    cache[tok] = kind
    return kind


def split_chains(toks: List[str], macros: Dict[str, Macro]
                 ) -> List[List[Tuple[str, List[str]]]]:
    """Chains of ``(relation, side)``; a chain's first relation is ``""``."""
    cache: Dict[str, str] = {}
    rows: List[List[Tuple[str, List[str]]]] = [[("", [])]]
    depth = 0  # braces, delimiters and non-alignment environments
    i = 0
    n = len(toks)

    def cur() -> List[str]:
        return rows[-1][-1][1]

    def relate(rel: str) -> None:
        side = cur()
        if rel == "=" and side and side[-1] == ":":
            side.pop()
            rel = ":="
        rows[-1].append((rel, []))

    while i < n:
        t = toks[i]
        kind = _classify(t, macros, cache) if depth == 0 else ""
        if t in ("\\begin", "\\end"):
            env, j = read_group(toks, i + 1)
            name = "".join(env or [])
            if name in ALIGN_ENVS and depth == 0:
                if name.startswith("alignat") and t == "\\begin":
                    _, j = read_group(toks, j)
                i = j
                continue
            depth += 1 if t == "\\begin" else -1
            cur().extend(toks[i:j])
            i = j
            continue
        if kind in ("begin", "end"):
            i += 1
            continue
        if t in ("{", "\\left") or t in OPENERS:
            depth += 1
        elif t in ("}", "\\right") or t in CLOSERS:
            depth = max(depth - 1, 0)
        if depth == 0:
            if t == "&":
                i += 1
                continue
            if t == "\\\\":
                rows.append([("", [])])
                _, i = read_optional(toks, i + 1)
                continue
            if t == "=" :
                if i + 1 < n and toks[i + 1] == ":":
                    relate("=:")
                    i += 2
                    continue
                relate("=")
                i += 1
                continue
            if t in RELATION_WORDS or kind == "relation":
                relate(t)
                i += 1
                continue
            if t in STACK_WORDS:
                over, j = read_group(toks, i + 1)
                base, k = read_group(toks, j)
                if over is not None and base is not None and \
                        [b for b in base if b != " "] == ["="]:
                    relate(t + "{" + "".join(over) + "}{=}")
                    i = k
                    continue
        cur().append(t)
        i += 1

    # Join the rows into chains: a row whose first side is empty continues
    # the chain before it.
    chains: List[List[Tuple[str, List[str]]]] = []
    for row in rows:
        first_empty = not [x for x in row[0][1] if x != " "]
        if first_empty and len(row) > 1 and chains:
            chains[-1].extend(row[1:])
        else:
            chains.append(row)
    return chains


def tautologies(math: str, macros: Dict[str, Macro]) -> List[Tuple[str, str, str]]:
    """``(relation, left, right)`` for each pair of sides that render alike."""
    found = []
    for chain in split_chains(tokenize(math), macros):
        for (_, left), (rel, right) in zip(chain, chain[1:]):
            a = normalize(left, macros)
            b = normalize(right, macros)
            if a and b and a == b:
                found.append((rel, "".join(left).strip(), "".join(right).strip()))
    return found


# -- scanning a file ---------------------------------------------------------------

def equations(lines: List[str]) -> List[Tuple[int, int, str]]:
    """``(first line, last line, math)`` for each math span in a Markdown file."""
    out: List[Tuple[int, int, str]] = []
    fence: Optional[Tuple[str, int]] = None
    in_comment = False
    in_display = False
    buf: List[str] = []
    buf_start = 0
    in_front = bool(lines) and lines[0].strip() == "---"
    for number, raw in enumerate(lines, 1):
        if in_front:
            if number > 1 and raw.strip() in ("---", "..."):
                in_front = False
            continue
        m = mdmask.FENCE_RE.match(raw)
        if fence is None and m and not in_comment and not in_display:
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1] \
                    and not m.group(2):
                fence = None
            continue
        masked, in_comment = mdmask.mask_markdown_line(raw, in_comment)
        was_display = in_display
        spans, in_display = mdmask.math_spans(masked, in_display)
        for s, e in spans:
            display = (s == 0 and was_display) or masked[max(s - 2, 0):s] == "$$"
            was_display = False
            if not display:
                out.append((number, number, masked[s:e]))
                continue
            if not buf:
                buf_start = number
            buf.append(masked[s:e])
            if masked[e:e + 2] == "$$":
                out.append((buf_start, number, "\n".join(buf)))
                buf = []
    if buf:
        out.append((buf_start, len(lines), "\n".join(buf)))
    return out


def scan_file(lines: List[str], macros: Dict[str, Macro]
              ) -> Tuple[List[Tuple[int, int, Finding]], int]:
    """``([(first, last, Finding), ...], equations examined)``."""
    found = []
    eqs = equations(lines)
    for first, last, math in eqs:
        if DEFINES_MACRO_RE.search(math):
            continue
        window = lines[max(first - 2, 0):last]
        if any(ALLOW_RE.search(w) for w in window):
            continue
        for rel, left, right in tautologies(math, macros):
            found.append((first, last, Finding(first, rel, left, right)))
    return found, len(eqs)


def format_message(finding: Finding) -> str:
    return (f"{finding.left} {finding.relation} {finding.right}: both sides "
            f"render identically once the macros are expanded, so the reader "
            f"sees a tautology. Give the left side its own notation (a symbol "
            f"or function name for the object being defined), or mark a "
            f"deliberate case with <!-- check-tautological-equations: allow -->.")


class Report(NamedTuple):
    findings: List[Tuple[str, Finding]]
    files: int
    lines: int
    equations: int
    skipped: bool


def run_check(base_ref: str, globs: List[str], ignores: List["re.Pattern[str]"],
              macros: Dict[str, Macro], whole_tree: bool) -> Report:
    """Scan equations touched since ``base_ref``, or all when whole-tree."""
    wanted: Dict[str, Optional[Set[int]]] = {}
    if whole_tree:
        paths = diffscope.git_paths(["ls-files", "--", *globs])
        if paths is None:
            return Report([], 0, 0, 0, True)
        for rel in paths:
            if not diffscope.ignored(rel, ignores):
                wanted[rel] = None
    else:
        if not base_ref:
            return Report([], 0, 0, 0, True)
        base = diffscope.run_git(["merge-base", base_ref, "HEAD"])
        if base is None or not base.strip():
            return Report([], 0, 0, 0, True)
        diff = diffscope.run_git([*engine.GIT_DIFF_ARGS, base.strip(), "--", *globs])
        if diff is None:
            return Report([], 0, 0, 0, True)
        added, deleted = diffscope.parse_diff(diff)
        for rel, numbered in added.items():
            if diffscope.ignored(rel, ignores):
                continue
            wanted[rel] = {n for n, text in numbered.items()
                           if not (text.strip() and text in deleted)}

    findings: List[Tuple[str, Finding]] = []
    files = lines = eq_count = 0
    for rel in sorted(wanted):
        content = diffscope.read_lines(rel)
        if content is None:
            continue
        files += 1
        keep = wanted[rel]
        lines += len(content) if keep is None else len(keep)
        hits, examined = scan_file(content, macros)
        eq_count += examined
        for first, last, finding in hits:
            if keep is None or any(first <= k <= last for k in keep):
                findings.append((rel, finding))
    return Report(findings, files, lines, eq_count, False)


def main() -> int:
    base_ref = os.environ.get("TE_BASE_REF", "").strip()
    macros_files = (os.environ.get("TE_MACROS_FILE", "").split()
                    or [DEFAULT_MACROS_FILE])
    globs = os.environ.get("TE_GLOBS", DEFAULT_GLOBS).split() or DEFAULT_GLOBS.split()
    ignores = diffscope.compile_ignores(
        diffscope.split_list(os.environ.get("TE_PATHS_IGNORE", "")))
    fail = diffscope.env_flag("TE_FAIL", _DEFAULT_FAIL)
    whole_tree = diffscope.env_flag("TE_WHOLE_TREE", False)

    macros = load_macros(macros_files)
    if macros is None:
        print(
            f"::warning::Skipping the tautological-equation check: no macros "
            f"file found among {' '.join(macros_files)}. Check out the "
            f"latex-macros submodule (submodules: true) or set 'macros-file'."
        )
        return 0

    report = run_check(base_ref, globs, ignores, macros, whole_tree)
    if report.skipped:
        reason = f"could not diff against '{base_ref}'" if base_ref else "no base-ref given"
        level = "::warning::" if base_ref else ""
        print(
            f"{level}Skipping the tautological-equation check for this run "
            f"({reason}; not falling back to a whole-tree scan)."
        )
        return 0

    scope = "whole tree" if whole_tree else f"equations touched since {base_ref}"
    print(
        f"Examined {report.lines} line(s) and {report.equations} equation(s) "
        f"across {report.files} file(s), expanding {len(macros)} macro(s) from "
        f"{' '.join(macros_files)} (scope: {scope})."
    )
    if not report.findings:
        print("No equation has two sides that render identically.")
        return 0

    severity = "error" if fail else "warning"
    for rel, finding in report.findings:
        print(f"::{severity} file={rel},line={finding.line}::"
              f"{format_message(finding)}")
    print(f"\n{len(report.findings)} equation(s) render as a tautology.")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
