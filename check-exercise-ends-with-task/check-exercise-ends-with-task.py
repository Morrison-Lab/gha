#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
r"""
Flag an exercise that does not end with a question or an instruction.

The lab's rule (Ezra, 2026-11-09; Morrison-Lab/psw#548, design in psw#549):
the last thing a reader meets in an exercise is its task. The last paragraph
of an exercise div (id ``exr-...``) must hold a task sentence, and nothing but
a task may follow the last task sentence: a figure, table, code block or
include shortcode after it is flagged.

Task sentences are recognised by ``is_task`` in check-exercise-question-paragraph
(a question mark, or an imperative task verb such as Show, Find or Derive), which
this check imports rather than copies, so the two checks cannot disagree.

Not examined: nested solution divs (``#sol-``, ``.sol``, ``.solution``,
``.answer``), callouts (hints), HTML comments, display math, headings, lists
and block quotes (all neutral: they are skipped when finding the last block).
A nested ``#fig-`` or ``#tbl-`` div counts as a figure or table block. An
exercise nested inside another exercise is part of the outer one.
``<!-- ends-with-task-ok: reason -->`` inside an exercise exempts it.

Diff-scoped: a finding is reported only when the diff adds a line inside the
exercise div. With no base ref the check skips rather than scanning the whole
tree. ``EET_WHOLE_TREE=true`` measures a corpus.

Configuration (environment variables, set by the composite action):
  EET_BASE_REF    Git ref/SHA to diff against. Empty and not whole-tree => skip.
  EET_GLOBS       Space-separated git pathspecs (default: '*.qmd').
  EET_FAIL        "true" (default) => exit 1 on a finding; "false" => warnings.
  EET_WHOLE_TREE  "true" => scan every tracked matching file in full.
"""

import importlib.util
import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional, Set

SIBLING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "check-exercise-question-paragraph",
                       "check-exercise-question-paragraph.py")
_spec = importlib.util.spec_from_file_location("eqp", SIBLING)
eqp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eqp)

DEFAULT_GLOBS = "*.qmd"
ADVICE = ("end the exercise with its question or instruction; "
          "move any figure, table, code or include above it")

OK_RE = re.compile(r"<!--\s*ends-with-task-ok:")
LABEL_DIV_RE = re.compile(r"#(fig|tbl)-")
IMAGE_RE = re.compile(r"^\s*!\[")
TABLE_RE = re.compile(r"^\s*\|")
SHORTCODE_RE = re.compile(r"^\s*\{\{<")
# A paragraph that opens with a lowercase word continues the sentence a display interrupted.
CONTINUATION_RE = re.compile(r"^[*_]*[a-z]")
# Marks a skipped block (a solution or callout div): it adds no block but ends the paragraph
# before it, so the paragraph after it cannot continue that one's sentence.
BREAK = "\0\0"
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")
NEUTRAL_RE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|>)")


class Finding(NamedTuple):
    line: int
    end: int
    reason: str


def verdict(blocks: List[tuple]) -> Optional[str]:
    """Why the last block is not a task, or None when the exercise is fine."""
    if not blocks:
        return "it has no text"
    kind, text = blocks[-1]
    if kind != "prose":
        return f"its last block is a {kind}, not a task"
    if not any(eqp.is_task(s) for s in eqp.sentences(text)):
        return "its last paragraph holds no question or instruction"
    return None


def blocks_of(body: List[str]) -> List[tuple]:
    """(kind, text) blocks of an exercise body, in order."""
    out: List[tuple] = []
    para: List[str] = []
    # True while the last block is a paragraph that a display equation interrupted,
    # so a paragraph after the display that opens in lowercase ("where ...") continues
    # its sentence and is judged with it (gha#1843).
    continues = False
    adjacent = False  # the last block is a paragraph, with only blank lines after it
    # A display inside a list item: a lowercase paragraph after it in the same item
    # continues the item's sentence and is judged with it. "join" appends it to the
    # paragraph before the display; "item" judges it with the text of the item's marker
    # line, which is otherwise neutral and adds no block.
    item_carry = ""
    item_text = ""  # the text of the current list item's marker line, until a paragraph closes
    item_para = False  # like adjacent, for a paragraph inside a list item

    def close() -> None:
        nonlocal continues, adjacent, item_carry, item_text, item_para
        if para:
            text = " ".join(para)
            carry_ok = item_carry and in_list and CONTINUATION_RE.match(text)
            if carry_ok and item_carry.startswith("item:"):
                out.append(("prose", item_carry[5:] + " " + text))
            elif ((continues or carry_ok) and out and out[-1][0] == "prose"
                  and CONTINUATION_RE.match(text)):
                out[-1] = ("prose", out[-1][1] + " " + text)
            else:
                out.append(("prose", text))
            para.clear()
            continues = False
            item_carry = item_text = ""
            adjacent = not in_list  # a list paragraph's sentence ends with its list item
            item_para = in_list

    in_math = False
    # Inside a list item: its indented and lazy lines are judged as before, but a display
    # there cannot carry a list paragraph's sentence on to a paragraph after the list.
    in_list = False
    prev_blank = True
    for raw in body:
        stripped = raw.strip()
        if raw == BREAK:
            close()
            continues = adjacent = item_para = False
            item_carry = item_text = ""
            continue
        if stripped and not in_math:
            if LIST_ITEM_RE.match(raw):
                in_list = True
            elif prev_blank and raw[:1] not in (" ", "\t"):
                in_list = False
        prev_blank = not stripped
        if stripped.startswith("$$"):
            if not in_math:
                joinable = (bool(para) or adjacent) and not in_list
                carry = ""
                if in_list:
                    if para or item_para:
                        carry = "join"
                    elif item_text:
                        carry = "item:" + item_text
                close()
                continues = joinable
                item_carry = carry
            in_math = not (in_math or (stripped.endswith("$$") and len(stripped) > 2))
            continue
        if in_math:
            in_math = "$$" not in raw
            continue
        if stripped and (raw.startswith("\0") or SHORTCODE_RE.match(raw) or TABLE_RE.match(raw)
                         or NEUTRAL_RE.match(raw) or (IMAGE_RE.match(raw) and not para)):
            close()
            continues = adjacent = False  # another block sits between the paragraph and what follows
            item_carry = item_text = ""
            item_para = False
            if LIST_ITEM_RE.match(raw):
                item_text = LIST_ITEM_RE.sub("", raw, count=1).strip()
        if not stripped:
            close()
        elif raw.startswith("\0"):
            close()
            out.append((raw[1:], ""))
        elif SHORTCODE_RE.match(raw):
            close()
            out.append(("include", stripped))
        elif TABLE_RE.match(raw):
            close()
            out.append(("table", stripped))
        elif NEUTRAL_RE.match(raw):
            close()
        elif IMAGE_RE.match(raw) and not para:
            out.append(("figure", stripped))
        else:
            para.append(stripped)
    close()
    return out


def exercises(lines: List[str]) -> List[Finding]:
    """One finding per exercise div that does not end with a task."""
    found: List[Finding] = []
    fence: Optional[str] = None
    in_comment = False
    depth = 0
    cur: Optional[Dict] = None
    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if cur is not None and OK_RE.search(raw):
            cur["ok"] = True
        if in_comment:
            in_comment = "-->" not in raw
            continue
        if raw.lstrip().startswith("<!--"):
            in_comment = "-->" not in raw
            continue
        fm = eqp.FENCE_RE.match(raw)
        if fence is not None:
            if fm and fm.group(1)[0] == fence:
                fence = None
            continue
        if fm:
            fence = fm.group(1)[0]
            if cur is not None and cur["skip"] is None:
                cur["body"].append("\0code block")
            continue
        dm = eqp.DIV_RE.match(raw)
        if dm:
            if dm.group(2):
                attrs = dm.group(2)
                if cur is None and eqp.EXR_RE.search(attrs):
                    cur = {"depth": depth, "skip": None, "body": [], "ok": False,
                           "start": lineno}
                elif cur is not None and cur["skip"] is None:
                    if eqp.SKIP_DIV_RE.search(attrs):
                        cur["skip"] = depth
                        cur["body"].append(BREAK)  # not judged, but it still splits a sentence
                    elif LABEL_DIV_RE.search(attrs):
                        cur["skip"] = depth
                        kind = "figure" if "#fig-" in attrs else "table"
                        cur["body"].append("\0" + kind)
                depth += 1
            elif depth > 0:
                depth -= 1
                if cur is not None and depth == cur["depth"]:
                    if not cur["ok"]:
                        reason = verdict(blocks_of(cur["body"]))
                        if reason:
                            found.append(Finding(cur["start"], lineno, reason))
                    cur = None
                elif cur is not None and cur["skip"] == depth:
                    cur["skip"] = None
            continue
        if cur is not None and cur["skip"] is None:
            cur["body"].append(raw)
    return found


def touched(item: Finding, keep: Optional[Set[int]]) -> bool:
    """Whether the diff adds a line inside the exercise (None = every line)."""
    if keep is None:
        return True
    return any(item.line <= n <= item.end for n in keep)


def main() -> int:
    base_ref = os.environ.get("EET_BASE_REF", "").strip()
    globs = os.environ.get("EET_GLOBS", DEFAULT_GLOBS).split() or [DEFAULT_GLOBS]
    fail = eqp._flag("EET_FAIL", True)
    whole = eqp._flag("EET_WHOLE_TREE", False)
    wanted = eqp.wanted_lines(base_ref, globs, whole)
    if wanted is None:
        level = "::warning::" if base_ref else ""
        print(f"{level}Skipping the exercise-ends-with-task check for this run "
              f"({'could not diff against ' + repr(base_ref) if base_ref else 'no base-ref given'}).")
        return 0
    severity = "error" if fail else "warning"
    findings = 0
    for rel in sorted(wanted):
        try:
            with open(rel, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().split("\n")
        except OSError:
            continue
        for item in exercises(lines):
            if touched(item, wanted[rel]):
                findings += 1
                print(f"::{severity} file={rel},line={item.line}::Exercise does not "
                      f"end with a task: {item.reason}. Fix: {ADVICE}")
    print(f"Examined {len(wanted)} file(s); {findings} exercise(s) flagged.")
    return 1 if findings and fail else 0


if __name__ == "__main__":
    sys.exit(main())
