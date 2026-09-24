#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Write the .qmd files a course can give to students.

A source that keeps each answer beside its question, in a div only the
answer key shows, can never be handed out itself, and neither can one whose
included fragments carry the answers. This writes a self-contained copy of
each source that students can open and render themselves:

- every {{< include >}} is inlined, recursively, resolved the way Quarto
  resolves it, and an included fragment's own front matter is dropped
  (Quarto merges it instead, so a key other than `filters` is warned
  about);
- every answer-key-only div is removed with everything inside it: a div
  with a hidden class (braced, or Pandoc's `::: sol` shorthand), and every
  div Quarto shows only under an answer profile;
- whole-line `#` comments in the front matter are removed;
- HTML comments outside code are removed first, since they carry
  instructor notes, and so that a `:::` line inside one cannot open or
  close a div (code blocks and code spans are left alone, and a comment
  that spans a `:::` line is an error);
- optionally, fenced code blocks holding a `quarto render` command are
  removed, with any div they leave empty;
- blank runs left behind are collapsed.

It fails, rather than guess, on a missing include, unbalanced divs, a code
fence that is never closed, or a comment that is never closed.

It also fails on an answer written in a raw HTML `<div>` rather than a `:::`
div: a `<div>` with a hidden class, or a `content-visible` or
`content-hidden` one with a profile attribute. Pandoc reads such a tag as the
same div as `:::` syntax, so the assign filter hides it, but this removes
only `:::` divs and would copy the answer into the student file. The error
names the file and line and asks for `:::` syntax; it does not depend on the
check running. Code blocks, code spans and HTML comments are not scanned.

It works line by line; check_student_qmd.py reads its output with Pandoc
instead, so the two do not share the parser that removes divs and comments.
The raw HTML div refusal is the one scan they share, since both apply it to
the source rather than to the student file.

Ported from Morrison-Lab/mlg's tools/make_student_qmd.py (mlg#22), itself a
port of Morrison-Lab/epi204's scripts/generate-assign-qmd.R.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from student_qmd_common import (  # noqa: E402
    CODE_SPAN,
    DEFAULT_ANSWER_PROFILES,
    DEFAULT_HIDDEN_CLASSES,
    DEFAULT_STUDENT_PROFILE,
    Config,
    FENCE,
    StudentQmdError,
    check_unique_names,
    expand_includes,
    fence_closes,
    find_sources,
    front_matter_end,
    hides,
    output_path,
    parse_bool,
    raw_answer_divs,
    split_list,
)
from student_qmd_macros import MacroError, macro_groups, prune_macros  # noqa: E402

DIV_OPEN = re.compile(r"^\s*:{3,}\s*\S")
DIV_CLOSE = re.compile(r"^\s*(:{3,})\s*$")
# A div opener's attributes: `::: {.a #b k="v"}`, or Pandoc's shorthand
# `::: a`, which means `::: {.a}`.
# A quoted value may hold a `}`, as in {data-note="}" .sol}.
BRACED = re.compile(r"""^\s*:{3,}\s*\{((?:[^}"']|"[^"]*"|'[^']*')*)\}""")
QUOTED = re.compile(r"""="[^"]*"|='[^']*'""")
BARE = re.compile(r"^\s*:{3,}\s*([\w-]+)\s*:*\s*$")
# Pandoc accepts the value quoted or, as a single word, bare.
PROFILE = re.compile(
    r"""(?<![\w-])(when|unless)-profile\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'}]+))"""
)
# Stands in for a removed render chunk until empty divs are dropped. It holds
# a NUL, which no source line can.
REMOVED = "\x00removed render chunk\x00"


def answer_only(line: str, cfg: Config) -> bool:
    """Whether a div opener starts content only the answer key shows."""
    if m := BARE.match(line):
        return hides({m.group(1)}, [], cfg)
    m = BRACED.match(line)
    if not m:
        return False
    attrs = m.group(1)
    bare = QUOTED.sub("=", attrs)  # so a value like ".sol" is not a class
    classes = set(re.findall(r"(?<![\w-])\.([\w-]+)", bare))
    profiles = [(f"{kind}-profile", "".join(values)) for kind, *values in PROFILE.findall(attrs)]
    return hides(classes, profiles, cfg)


def code_mask(lines: list[str]) -> list[bool]:
    """Mark each line that is a code fence or inside one."""
    mask = []
    fence: str | None = None
    for line in lines:
        if fence is None:
            if m := FENCE.match(line):
                fence = m.group(1)
            mask.append(fence is not None)
        else:
            mask.append(True)
            if fence_closes(line, fence):
                fence = None
    if fence is not None:
        raise StudentQmdError(f"a {fence} code fence is never closed")
    return mask


def opener(lines: list[str], i: int) -> str:
    """The div opener starting at line `i`, joined with any lines its
    attribute block continues onto, since Pandoc allows `{.sol` and `}` on
    separate lines."""
    text = lines[i]
    j = i
    while "{" in text and not BRACED.match(text):
        j += 1
        if j >= len(lines) or DIV_OPEN.match(lines[j]) or DIV_CLOSE.match(lines[j]):
            raise StudentQmdError(f"line {i + 1}: a div's attribute block is never closed")
        text += " " + lines[j]
    return text


def drop_hidden_divs(lines: list[str], cfg: Config) -> list[str]:
    """Remove every answer-key-only div, with everything inside it."""
    out: list[str] = []
    depth = 0  # div nesting depth, counting only lines outside code
    skip_from = 0  # the depth of the hidden div being dropped, or 0
    for i, (line, in_code) in enumerate(zip(lines, code_mask(lines))):
        if not in_code and DIV_CLOSE.match(line):
            depth -= 1
            if depth < 0:
                raise StudentQmdError(f"unmatched ::: closer: {line!r}")
            if skip_from:
                if depth < skip_from:
                    skip_from = 0
                continue
        elif not in_code and DIV_OPEN.match(line):
            depth += 1
            if not skip_from and answer_only(opener(lines, i), cfg):
                skip_from = depth
        if not skip_from:
            out.append(line)
    if depth != 0:
        raise StudentQmdError(f"unbalanced ::: divs (depth {depth} at end of document)")
    return out


def find_comment_start(line: str, start: int = 0) -> int:
    """Index of the first `<!--` at or after `start` outside a code span, or -1."""
    spans = [m.span() for m in CODE_SPAN.finditer(line)]
    i = line.find("<!--", start)
    while i >= 0 and any(a <= i < b for a, b in spans):
        i = line.find("<!--", i + 1)
    return i


def drop_html_comments(lines: list[str]) -> list[str]:
    """Remove <!-- ... --> comments, including multi-line ones, outside code.

    This runs before drop_hidden_divs, so a `:::` line inside a comment can
    never open or close a div there. A comment is not allowed to span a
    `:::` line at all: if one does, whether by design or because a stray
    `<!--` started one by accident, a div boundary would silently vanish, so
    this fails instead.
    """
    out: list[str] = []
    in_comment = False
    fence = ""
    for n, line in enumerate(lines, start=1):
        if fence:
            out.append(line)
            if fence_closes(line, fence):
                fence = ""
            continue
        if in_comment and (DIV_OPEN.match(line) or DIV_CLOSE.match(line)):
            raise StudentQmdError(
                f"line {n}: an HTML comment spans a ::: line; close the comment "
                "first, or put div syntax in a comment inside a code block"
            )
        if not in_comment and (m := FENCE.match(line)):
            fence = m.group(1)
            out.append(line)
            continue
        kept = ""
        rest = line
        while rest:
            if in_comment:
                end = rest.find("-->")
                if end < 0:
                    rest = ""
                else:
                    in_comment = False
                    rest = rest[end + 3 :]
            else:
                start = find_comment_start(rest)
                if start < 0:
                    kept += rest
                    rest = ""
                else:
                    kept += rest[:start]
                    in_comment = True
                    rest = rest[start + 4 :]
        # A line that held nothing but comment goes entirely: left blank, it
        # would split the paragraph it sat in.
        if kept.strip() or not line.strip():
            out.append(kept)
    if in_comment:
        raise StudentQmdError("unclosed <!-- comment")
    if fence:
        raise StudentQmdError(f"a {fence} code fence is never closed")
    return out


def replace_render_chunks(lines: list[str]) -> list[str]:
    """Replace each fenced code block holding `quarto render` with REMOVED.

    These are the commands an instructor keeps in a source to build its
    handouts; they mean nothing to a student.
    """
    out: list[str] = []
    block: list[str] = []
    fence = ""
    for line in lines:
        if fence:
            block.append(line)
            if fence_closes(line, fence):
                fence = ""
                if any("quarto render" in b for b in block):
                    out.append(REMOVED)
                else:
                    out.extend(block)
                block = []
            continue
        if m := FENCE.match(line):
            fence = m.group(1)
            block = [line]
            continue
        out.append(line)
    if fence:
        raise StudentQmdError(f"a {fence} code fence is never closed")
    return out


def drop_emptied_divs(lines: list[str]) -> list[str]:
    """Remove each div whose body is only blank lines and removed chunks,
    at least one of them, so a wrapper such as `::: hidden` around a render
    chunk goes too. A div that was empty in the source stays: `::: {#refs}`
    places the bibliography. A removed div counts as a removed chunk for the
    div around it."""
    changed = True
    while changed:
        changed = False
        mask = code_mask(lines)
        stack: list[int] = []
        for i, line in enumerate(lines):
            if mask[i]:
                continue
            if DIV_CLOSE.match(line):
                if not stack:
                    raise StudentQmdError(f"unmatched ::: closer: {line!r}")
                start = stack.pop()
                body = lines[start + 1 : i]
                if REMOVED in body and all(b == REMOVED or not b.strip() for b in body):
                    lines = lines[:start] + [REMOVED] + lines[i + 1 :]
                    changed = True
                    break
            elif DIV_OPEN.match(line):
                stack.append(i)
    return [line for line in lines if line != REMOVED]


def drop_render_chunks(lines: list[str]) -> list[str]:
    return drop_emptied_divs(replace_render_chunks(lines))


def tidy(text: str) -> str:
    """Collapse runs of blank lines.

    Other trailing spaces are kept: two of them make a hard line break.
    """
    lines = [line if line.strip() else "" for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip("\n") + "\n"


def drop_yaml_comments(lines: list[str]) -> list[str]:
    """Remove whole-line `#` comments from the document's front matter.

    A comment at the end of a line is left alone, because `#` can also sit
    inside a quoted value; check_student_qmd.py refuses those.
    """
    end = front_matter_end(lines)
    if not end:
        return lines
    kept = [line for line in lines[1:end] if not line.lstrip().startswith("#")]
    return [lines[0], *kept, *lines[end:]]


def student_qmd(src: Path, cfg: Config) -> str:
    raw: list[str] = []
    expanded = expand_includes(src, visit=lambda path, ls: raw.extend(raw_answer_divs(path, ls, cfg)))
    if raw:
        raise StudentQmdError("; ".join(raw))
    lines = drop_html_comments(drop_yaml_comments(expanded))
    shown = drop_hidden_divs(lines, cfg)
    if cfg.drop_render_chunks:
        shown = drop_render_chunks(shown)
    if cfg.prune_macros:
        shown = prune_student_macros(lines, shown)
    return tidy("\n".join(shown))


def body_mask(lines: list[str]) -> list[bool]:
    """Mark the front matter and code, where no macro definition starts."""
    end = front_matter_end(lines)
    return [i < end or in_code for i, in_code in enumerate(code_mask(lines))]


def prune_student_macros(lines: list[str], shown: list[str]) -> list[str]:
    """Drop the macro definitions `shown` never uses.

    A definition inside an answer-key-only div is refused rather than
    dropped with the div: the check takes definitions out of its comparison,
    so an answer written into one would reach nothing that notices.
    """
    try:
        before = Counter(g.name for g in macro_groups(lines, body_mask(lines)))
        after = Counter(g.name for g in macro_groups(shown, body_mask(shown)))
    except MacroError as err:
        raise StudentQmdError(f"{err} (counting from the top, includes inlined)") from err
    if hidden := sorted(before - after):
        raise StudentQmdError(
            "a macro definition inside an answer-key-only div, which prune-macros "
            f"refuses: \\{hidden[0]}; move it out of the div, or turn prune-macros off"
        )
    return prune_macros(shown, body_mask(shown))


def write_index(out_dir: Path, names: list[str], title: str, back_href: str) -> None:
    items = "\n".join(
        f'    <li><a href="{html.escape(n)}" download>{html.escape(n)}</a></li>' for n in names
    )
    back = (
        f'  <a class="back" href="{html.escape(back_href)}">&larr; Back</a>\n' if back_href else ""
    )
    (out_dir / "index.html").write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: sans-serif; max-width: 600px; margin: 4em auto; color: #333; }}
    h1 {{ font-size: 1.8em; margin-bottom: 0.5em; }}
    p {{ color: #666; margin-bottom: 1.5em; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ margin: 0.5em 0; }}
    a {{ color: #0066cc; text-decoration: none; font-size: 1.05em; }}
    a:hover {{ text-decoration: underline; }}
    .back {{ display: inline-block; margin-bottom: 2em; color: #666; font-size: 0.95em; }}
  </style>
</head>
<body>
{back}  <h1>{html.escape(title)}</h1>
  <p>
    Each file has every question and no solutions, with nothing left to
    include, so a student can open and render it on its own.
    Click a file to download it.
  </p>
  <ul>
{items}
  </ul>
</body>
</html>
""",
        encoding="utf-8",
    )


def config_args(parser: argparse.ArgumentParser) -> None:
    """The options both scripts take, so they cannot disagree about them."""
    parser.add_argument("sources", nargs="+", help="source .qmd paths or globs")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--hidden-classes", default=" ".join(DEFAULT_HIDDEN_CLASSES))
    parser.add_argument("--answer-profiles", default=" ".join(DEFAULT_ANSWER_PROFILES))
    parser.add_argument("--student-profile", default=DEFAULT_STUDENT_PROFILE)
    parser.add_argument("--drop-render-chunks", default="false")
    parser.add_argument("--prune-macros", default="false")


def config_from(args: argparse.Namespace) -> Config:
    return Config(
        hidden_classes=frozenset(split_list(args.hidden_classes)),
        answer_profiles=frozenset(split_list(args.answer_profiles)),
        student_profile=args.student_profile.strip(),
        drop_render_chunks=parse_bool(args.drop_render_chunks, "drop-render-chunks"),
        prune_macros=parse_bool(args.prune_macros, "prune-macros"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    config_args(parser)
    parser.add_argument("--index-title", default="", help="write an index.html with this title")
    parser.add_argument("--index-back-href", default="", help="the index page's back link")
    parser.add_argument(
        "--list-file",
        type=Path,
        help="also write the absolute path of each file written, one per line",
    )
    args = parser.parse_args(argv)
    try:
        cfg = config_from(args)
        sources = find_sources(args.sources)
        check_unique_names(sources)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        names = []
        for src in sources:
            dest = output_path(args.output_dir, src)
            try:
                dest.write_text(student_qmd(src, cfg), encoding="utf-8")
            except StudentQmdError as err:
                raise StudentQmdError(f"{src}: {err}") from err
            names.append(dest.name)
            print(f"{src} -> {dest}")
        if args.index_title:
            write_index(args.output_dir, names, args.index_title, args.index_back_href)
        if args.list_file:
            args.list_file.write_text(
                "".join(f"{output_path(args.output_dir.resolve(), Path(n))}\n" for n in names),
                encoding="utf-8",
            )
    except StudentQmdError as err:
        print(f"::error::{err}")
        return 1
    print(f"Wrote {len(names)} student .qmd file(s) to {args.output_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
