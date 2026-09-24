#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Check that each student .qmd file carries no answers and nothing else changed.

make_student_qmd.py writes the files line by line. This reads each written
file and its source with Quarto's own Pandoc (`quarto pandoc`), so it shares
no parser for removing divs and comments with the generator. A file fails if
it:

- is missing, or still has an include shortcode, so it is not self-contained;
- has an answer-key-only div (a div with a hidden class, or a div Quarto
  shows only under an answer profile), an HTML comment, or a `#` comment in
  its front matter (Pandoc drops YAML comments on both sides, so they are
  refused outright rather than compared);
- with render-chunk removal on, still has a code block running `quarto render`;
- differs in any other way from its source's Pandoc AST with those divs,
  comments and render chunks taken out. That covers a leaked answer however
  short, a dropped question, and changed metadata.

It also refuses a source that has no answer-key-only div at all, since then
nothing was tested, and a source div classed `.solution`, `.answer` or the
like but no hidden class: the assign filter passes such a div through
untouched, so an answer written in one would reach every render and the
student file with nothing else noticing. It refuses an answer written in a
raw HTML `<div>` too, as the generator does, since the generator cannot
remove one.

Ported from the --student-qmd half of Morrison-Lab/mlg's
tools/check_student_copy.py (mlg#22).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_student_qmd import config_args, config_from  # noqa: E402
from student_qmd_common import (  # noqa: E402
    INCLUDE,
    Config,
    StudentQmdError,
    check_unique_names,
    expand_includes,
    find_sources,
    front_matter_end,
    hides,
    output_path,
    parse_bool,
    raw_answer_divs,
)
from student_qmd_macros import MacroError, macro_groups  # noqa: E402

# Answer lines shorter than this are too generic to name in the report; the
# whole-document comparison still covers them.
MIN_SOLUTION_LINE = 20
WHITESPACE = ("Space", "SoftBreak")


def pandoc(text: str, *args: str) -> str:
    """Run Quarto's bundled Pandoc on `text` and return its output."""
    quarto = shutil.which("quarto")
    if quarto is None:
        raise StudentQmdError(
            "quarto is not on PATH; this check reads documents with its Pandoc "
            "(set install-quarto: true, or install Quarto before this step)"
        )
    result = subprocess.run(
        [quarto, "pandoc", *args], input=text, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise StudentQmdError(f"pandoc {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


# An executable cell's opener, such as ```{r} or ```{zsh, eval = FALSE}.
# Quarto runs these before Pandoc sees the document; Pandoc itself does not
# read `{r}` as attributes, so it takes the whole cell for inline code and
# the parse of everything after it goes wrong.
EXEC_FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*\{\s*([A-Za-z][^}]*)\}\s*$")


def cells_as_code(text: str) -> str:
    """Rewrite each executable cell's opener so Pandoc reads a code block.

    The cell's header is kept whole, hex-encoded in an attribute, so a
    difference in it still counts. Both sides get the same rewrite.
    """
    lines = []
    for line in text.splitlines():
        if m := EXEC_FENCE.match(line):
            indent, fence, info = m.groups()
            line = f'{indent}{fence} {{.cell data-info="{info.strip().encode().hex()}"}}'
        lines.append(line)
    return "\n".join(lines)


def parse(text: str) -> dict:
    """Parse Markdown into Pandoc's JSON AST."""
    return json.loads(pandoc(cells_as_code(text), "-f", "markdown", "-t", "json"))


def is_type(node: object, *types: str) -> bool:
    return isinstance(node, dict) and node.get("t") in types


def div_classes(node: dict) -> set[str]:
    return set(node["c"][0][1])


def answer_div(node: object, cfg: Config) -> bool:
    """Whether an AST node is a div only the answer key shows."""
    if not is_type(node, "Div"):
        return False
    _, classes, pairs = node["c"][0]
    profiles = [(k, v) for k, v in pairs if k in ("when-profile", "unless-profile")]
    return hides(set(classes), profiles, cfg)


def misnamed_answer_div(node: object, cfg: Config) -> bool:
    return (
        is_type(node, "Div")
        and not div_classes(node) & cfg.hidden_classes
        and bool(cfg.misnamed & div_classes(node))
    )


def exercise_div(node: object) -> bool:
    return is_type(node, "Div") and node["c"][0][0].startswith("exr-")


def comment(node: object) -> bool:
    """Whether an AST node is raw HTML carrying an HTML comment."""
    return (
        is_type(node, "RawBlock", "RawInline")
        and node["c"][0] == "html"
        and "<!--" in node["c"][1]
    )


def render_chunk(node: object) -> bool:
    return is_type(node, "CodeBlock") and "quarto render" in node["c"][1]


def find(node: object, test) -> list:
    """Every node in `node` for which `test` holds, including nested ones."""
    found = []
    if test(node):
        found.append(node)
    if isinstance(node, dict):
        for value in node.values():
            found.extend(find(value, test))
    elif isinstance(node, list):
        for item in node:
            found.extend(find(item, test))
    return found


def without_answers(node: object, cfg: Config) -> object:
    """A copy of `node` with answer-key-only divs and comments removed, and
    render chunks too when the generator removes them.

    It is also normalized: runs of spaces and soft breaks become one space,
    and empty paragraphs go, so a comment removed from the text and one
    removed from the AST come out the same.
    """
    if isinstance(node, dict):
        node = {k: without_answers(v, cfg) for k, v in node.items()}
        # A metadata value emptied by removing its answer is empty whatever
        # its type: the student file writes it as an empty string.
        if is_type(node, "MetaBlocks", "MetaInlines") and not node["c"]:
            return {"t": "MetaString", "c": ""}
        # Pandoc numbers citations in order, so removing an answer that cites
        # something renumbers every later citation.
        if "citationNoteNum" in node:
            node["citationNoteNum"] = 0
        return node
    if not isinstance(node, list):
        return node
    out: list = []
    for item in node:
        if answer_div(item, cfg) or comment(item):
            continue
        if cfg.drop_render_chunks and render_chunk(item):
            continue
        stripped = without_answers(item, cfg)
        # A div that removing a render chunk left empty goes too, as the
        # generator drops it; one that was empty in the source stays.
        if (
            cfg.drop_render_chunks
            and is_type(item, "Div")
            and not stripped["c"][1]
            and find(item, render_chunk)
        ):
            continue
        if is_type(stripped, "Para", "Plain") and not stripped["c"]:
            continue
        if is_type(stripped, *WHITESPACE):
            if not out or is_type(out[-1], "Space"):
                continue
            stripped = {"t": "Space"}
        out.append(stripped)
    while out and is_type(out[-1], "Space"):
        out.pop()
    return out


def raw_tex(node: object) -> bool:
    return is_type(node, "RawBlock") and node["c"][0] in ("tex", "latex")


def without_macro_defs(node: object, found: list[str]) -> object:
    """A copy of `node` with every macro definition taken out of its raw TeX
    blocks, each appended to `found`, and any block left empty dropped.

    With prune-macros on, both sides go through this before they are
    compared, since the student file keeps only the definitions it uses.
    """
    if raw_tex(node):
        lines = node["c"][1].split("\n")
        kept = lines
        try:
            groups = macro_groups(lines)
        except MacroError as err:
            # Left in place, so the block is still compared as it stands;
            # the caller reports entries starting "!" as failures.
            found.append(f"!{err}")
            return node
        for g in reversed(groups):
            found.append("\n".join(lines[g.start : g.end]))
            kept = kept[: g.start] + kept[g.end :]
        text = "\n".join(kept)
        return {"t": "RawBlock", "c": [node["c"][0], text]} if text.strip() else None
    if isinstance(node, dict):
        return {k: without_macro_defs(v, found) for k, v in node.items()}
    if isinstance(node, list):
        items = (without_macro_defs(item, found) for item in node)
        return [item for item in items if item is not None]
    return node


def plain(doc: dict, blocks: list) -> str:
    """Render AST blocks as plain text."""
    body = {"pandoc-api-version": doc["pandoc-api-version"], "meta": {}, "blocks": blocks}
    return pandoc(json.dumps(body), "-f", "json", "-t", "plain", "--wrap=none")


def squash(text: str) -> str:
    return " ".join(text.split())


def first_difference(doc: dict, want: list, got: list) -> str:
    """Describe the first block where `got` differs from `want`."""

    def show(block: object) -> str:
        if not block:
            return "(nothing)"
        if text := squash(plain(doc, [block]))[:70]:
            return text
        # A block with no text, such as an empty `::: {#refs}` div or raw
        # TeX, would otherwise read as ''; name its type, and its id if any.
        kind = block.get("t", "?") if isinstance(block, dict) else "?"
        attr = block.get("c") if isinstance(block, dict) else None
        ident = attr[0][0] if kind == "Div" and attr and attr[0] and attr[0][0] else ""
        return f"(an empty {kind}{' #' + ident if ident else ''})"

    for i in range(max(len(want), len(got))):
        w = want[i] if i < len(want) else None
        g = got[i] if i < len(got) else None
        if w != g:
            return f"block {i + 1}: expected {show(w)!r}, found {show(g)!r}"
    return "the metadata differs"


# A quoted value that opens right after `key: ` and closes on the same line.
QUOTED_VALUE = re.compile(r""":\s+(?:"(?:[^"\\]|\\.)*"|'(?:[^']|'')*')""")


def yaml_comments(text: str) -> list[tuple[int, str]]:
    """Front-matter lines carrying a `#` comment, which Pandoc discards.

    A `#` at the start of a line or after whitespace starts a YAML comment,
    except inside a quoted value that opens after `key: ` and closes on the
    same line. Anything else with such a `#` is flagged, including a quoted
    value spanning lines and a line inside a multi-line value: this errs
    toward refusing.
    """
    lines = text.splitlines()
    end = front_matter_end(lines)
    found = []
    for i in range(1, end):
        if re.search(r"(^|\s)#", QUOTED_VALUE.sub(": ''", lines[i])):
            found.append((i + 1, lines[i]))
    return found


def check_source(src: Path, source: dict, cfg: Config, require_answers: bool = True) -> list[str]:
    """Problems with a source itself, whatever was generated from it.

    With `require_answers` off, a source with no answer-key-only div is
    warned about rather than refused; `main` still refuses a run in which no
    source had one.
    """
    failures = []
    for div in find(source["blocks"], lambda n: misnamed_answer_div(n, cfg)):
        classes = " ".join("." + c for c in div["c"][0][1])
        failures.append(
            f"{src}: a div classed {classes}, which the assign filter does not hide; "
            f"an answer goes in a div classed {' or '.join('.' + c for c in sorted(cfg.hidden_classes))}"
        )
    if cfg.prune_macros:
        for div in find(source["blocks"], lambda n: answer_div(n, cfg)):
            defs: list[str] = []
            without_macro_defs(div, defs)
            if defs:
                failures.append(
                    f"{src}: a macro definition inside an answer-key-only div, which "
                    f"prune-macros refuses: {defs[-1].lstrip('!').splitlines()[0][:70]!r}"
                )
    if not find(source["blocks"], lambda n: answer_div(n, cfg)):
        message = f"{src}: no answer-key-only divs found, so its student file was not tested"
        if require_answers:
            failures.append(message)
        else:
            print(f"::warning::{message}")
    return failures


def check_one(
    src: Path, dest: Path, cfg: Config, require_answers: bool = True
) -> tuple[list[str], int]:
    """Check one student file against its source; return failures and answers."""
    raw: list[str] = []
    expanded = expand_includes(
        src, warn=False, visit=lambda path, ls: raw.extend(raw_answer_divs(path, ls, cfg))
    )
    source = parse("\n".join(expanded))
    failures = raw + check_source(src, source, cfg, require_answers)
    if not dest.is_file():
        failures.append(f"{dest}: missing; was make_student_qmd.py run?")
        return failures, 0
    text = dest.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), start=1):
        if INCLUDE.match(line):
            failures.append(f"{dest}:{i}: an include shortcode, so it is not self-contained")
    for i, line in yaml_comments(text):
        failures.append(f"{dest}:{i}: a YAML comment in the front matter: {line.strip()[:70]!r}")
    student = parse(text)
    both = [student["blocks"], student["meta"]]
    if found := find(both, lambda n: answer_div(n, cfg)):
        failures.append(f"{dest}: {len(found)} answer-key-only div(s)")
    if found := find(both, comment):
        failures.append(f"{dest}: {len(found)} HTML comment(s), which may carry instructor notes")
    if cfg.drop_render_chunks and (found := find(both, render_chunk)):
        failures.append(f"{dest}: {len(found)} code block(s) running quarto render")
    answers = find(source["blocks"], lambda n: answer_div(n, cfg))
    source_blocks, student_blocks = source["blocks"], student["blocks"]
    if cfg.prune_macros:
        source_defs: list[str] = []
        student_defs: list[str] = []
        source_blocks = without_macro_defs(source_blocks, source_defs)
        student_blocks = without_macro_defs(student_blocks, student_defs)
        for path, defs in ((src, source_defs), (dest, student_defs)):
            for err in sorted({d for d in defs if d.startswith("!")}):
                failures.append(f"{path}: raw TeX {err[1:]}")
        for extra in sorted(set(student_defs) - set(source_defs)):
            if extra.startswith("!"):
                continue
            failures.append(
                f"{dest}: a macro definition its source does not have: "
                f"{extra.splitlines()[0][:70]!r}"
            )
    want = without_answers(source_blocks, cfg)
    got = without_answers(student_blocks, cfg)
    if want != got or without_answers(source["meta"], cfg) != without_answers(student["meta"], cfg):
        failures.append(
            f"{dest}: does not match {src} with its answers and comments removed; "
            + first_difference(source, want, got)
        )
    student_text = squash(plain(student, student["blocks"]))
    question_text = squash(plain(source, want))
    for div in answers:
        for line in plain(source, div["c"][1]).splitlines():
            line = squash(line)
            if len(line) >= MIN_SOLUTION_LINE and line in student_text and line not in question_text:
                failures.append(f"{dest}: contains solution text: {line[:70]!r}")
    n = len(find(student["blocks"], exercise_div))
    print(f"{dest.name}: {n} exercise(s); matches its source with {len(answers)} answer(s) removed")
    return failures, len(answers)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    config_args(parser)
    parser.add_argument(
        "--require-answers",
        default="true",
        help="fail a source with no answer-key-only div (default true); when false, "
        "warn instead, and fail only if no source has one",
    )
    args = parser.parse_args(argv)
    failures: list[str] = []
    compared = 0
    try:
        cfg = config_from(args)
        require_answers = parse_bool(args.require_answers, "require-answers")
        sources = find_sources(args.sources)
        check_unique_names(sources)
        for src in sources:
            try:
                found, n = check_one(src, output_path(args.output_dir, src), cfg, require_answers)
            except StudentQmdError as err:
                found, n = [f"{src}: {err}"], 0
            failures.extend(found)
            compared += n
        if not failures and compared == 0:
            failures.append("no source has an answer-key-only div, so nothing was tested")
    except StudentQmdError as err:
        failures.append(str(err))
    for failure in failures:
        print(f"::error::{failure}")
    if failures:
        return 1
    print(
        f"Checked {len(sources)} student .qmd file(s): "
        f"{compared} answer(s) removed, nothing else changed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
