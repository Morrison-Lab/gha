#!/usr/bin/env python3
"""Decide the check-links verdict from lychee's JSON report (gha#1052).

lychee fails on every rejected link, including a 5xx from a host that is
briefly down. A github.com outage then fails every PR in every consumer,
for links in files the PR never touched. This script reads the report and
demotes a 5xx to a warning unless the link sits on a line the PR adds.
Every other failure (a 404, a network error, a timeout) still blocks.

Environment:
  LYCHEE_JSON      path to lychee's ``--format json`` report (required)
  LYCHEE_EXIT      lychee's exit code (required): 0 clean, 2 link failures,
                   anything else a tool or configuration error
  LINKS_BASE_REF   which 5xx block: empty means none do (no lines are known
                   to be added), ``all`` means every 5xx does (lychee's own
                   behaviour), anything else is a git ref, and a 5xx blocks
                   only when it is on a line added since its merge base
  LINKS_FAIL       ``true`` (default) exits 1 on a blocking failure
  LINKS_FAIL_IF_EMPTY  ``true`` exits 1 when lychee found no links

Exit status: 0 pass, 1 blocking failure, 2 unusable input.
"""

import json
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def _normalize_path(path: str) -> str:
    # Strip a `./` prefix only; lstrip("./") would eat the dot of `.github/`.
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def added_lines(base_ref: str) -> Dict[str, Set[int]]:
    """{file: {new-file line numbers}} added since the merge base of base_ref and HEAD.

    Raises subprocess.CalledProcessError when git cannot compute the diff.
    The header parsing follows check-quarto-prose's _added_line_numbers.
    """
    diff = subprocess.run(
        ["git", "-c", "core.quotePath=false", "diff", "--unified=0",
         "--no-color", f"{base_ref}...HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout
    result: Dict[str, Set[int]] = {}
    cur: Optional[str] = None
    lineno = 0
    in_hunk = False
    for raw in diff.split("\n"):
        if raw.startswith("diff "):
            in_hunk = False
            continue
        # Before the first "@@" these are headers; inside a hunk they are
        # a removed "-- x" or an added "++ y" line.
        if raw.startswith("--- ") and not in_hunk:
            continue
        if raw.startswith("+++ ") and not in_hunk:
            target = raw[4:].split("\t", 1)[0]
            if len(target) >= 2 and target[0] == '"' and target[-1] == '"':
                target = target[1:-1]
            if target == "/dev/null":
                cur = None
            else:
                cur = _normalize_path(target[2:] if target.startswith("b/") else target)
                result.setdefault(cur, set())
            continue
        if raw.startswith("@@"):
            in_hunk = True
            m = _HUNK_RE.match(raw)
            lineno = int(m.group(1)) if m else 0
            continue
        if raw.startswith("+"):
            if cur is not None:
                result[cur].add(lineno)
            lineno += 1
    return result


def _status_code(entry: dict) -> Optional[int]:
    code = (entry.get("status") or {}).get("code")
    return code if isinstance(code, int) else None


def _on_added_line(path: str, entry: dict, added: Dict[str, Set[int]]) -> bool:
    lines = added.get(_normalize_path(path), set())
    line = (entry.get("span") or {}).get("line")
    if isinstance(line, int):
        return line in lines
    # No span: lychee cannot say where the link is, so treat it as added
    # if the file has any added line at all (the conservative reading).
    return bool(lines)


def classify(
    report: dict, added: Optional[Dict[str, Set[int]]]
) -> Tuple[List[Tuple[str, dict]], List[Tuple[str, dict]]]:
    """Split failures into (blocking, demoted).

    ``added`` is None to make every 5xx block (``all``), or the added-line
    map (empty when no base ref was given) to block only 5xx on added lines.
    """
    blocking: List[Tuple[str, dict]] = []
    demoted: List[Tuple[str, dict]] = []
    for key in ("error_map", "timeout_map"):
        for path, entries in (report.get(key) or {}).items():
            for entry in entries:
                code = _status_code(entry)
                transient = (
                    key == "error_map"
                    and code is not None
                    and 500 <= code <= 599
                    and added is not None
                    and not _on_added_line(path, entry, added)
                )
                (demoted if transient else blocking).append((path, entry))
    return blocking, demoted


def _escape(text: str) -> str:
    # Workflow-command data escaping, so a URL cannot end the annotation early.
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _describe(entry: dict) -> str:
    code = _status_code(entry)
    status = (entry.get("status") or {}).get("text") or "unknown status"
    prefix = f"[{code}] " if code is not None else ""
    return f"{prefix}{entry.get('url', '?')}: {status}"


def _annotate(level: str, path: str, entry: dict, suffix: str = "") -> str:
    line = (entry.get("span") or {}).get("line")
    loc = f" file={_normalize_path(path)}"
    if isinstance(line, int):
        loc += f",line={line}"
    return f"::{level}{loc}::{_escape(_describe(entry) + suffix)}"


def _summary(blocking, demoted) -> str:
    out = ["## Link check", ""]
    out.append(f"{len(blocking)} blocking failure(s), {len(demoted)} demoted 5xx warning(s).")
    for title, rows in (("Blocking", blocking), ("Demoted 5xx (not on an added line)", demoted)):
        if rows:
            out += ["", f"### {title}", ""]
            out += [f"- `{_normalize_path(p)}`: {_describe(e)}" for p, e in rows]
    return "\n".join(out) + "\n"


def main() -> int:
    report_path = os.environ.get("LYCHEE_JSON", "")
    exit_raw = os.environ.get("LYCHEE_EXIT", "")
    base_ref = os.environ.get("LINKS_BASE_REF", "").strip()
    fail = _truthy(os.environ.get("LINKS_FAIL", "true"))
    fail_if_empty = _truthy(os.environ.get("LINKS_FAIL_IF_EMPTY", "false"))

    if not exit_raw.strip().isdigit():
        print(f"::error::lychee exit code is missing or not a number: {exit_raw!r}")
        return 2
    lychee_exit = int(exit_raw)
    if lychee_exit not in (0, 2):
        print(f"::error::lychee exited {lychee_exit}, a tool or configuration "
              "error rather than a link failure; see the lychee step's log.")
        return 1 if fail else 0
    try:
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"::error::cannot read lychee's JSON report {report_path!r}: {exc}. "
              "Remove any --format or --output from lychee-args.")
        return 2

    if base_ref == "all":
        added: Optional[Dict[str, Set[int]]] = None
    elif base_ref == "":
        added = {}
    else:
        try:
            added = added_lines(base_ref)
        except (subprocess.CalledProcessError, OSError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            print(f"::warning::cannot diff against base-ref {base_ref!r} "
                  f"({detail.strip()}); every 5xx blocks this run.")
            added = None

    blocking, demoted = classify(report, added)
    for path, entry in demoted:
        print(_annotate("warning", path, entry,
                        " (server error on a line this change does not add; not failing the check)"))
    for path, entry in blocking:
        print(_annotate("error", path, entry))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(_summary(blocking, demoted))

    total = report.get("total")
    print(f"lychee checked {total} link(s): {len(blocking)} blocking failure(s), "
          f"{len(demoted)} demoted 5xx warning(s).")

    if lychee_exit == 2 and not blocking and not demoted:
        print("::error::lychee reported link failures but the JSON report lists "
              "none; refusing to call that clean.")
        return 1 if fail else 0
    if fail_if_empty and total == 0:
        print("::error::No links were found. This usually indicates a configuration error.")
        return 1
    if blocking and fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
