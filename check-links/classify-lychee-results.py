#!/usr/bin/env python3
"""Decide the check-links verdict from lychee's JSON report (gha#1052).

lychee fails on every rejected link, including a 5xx from a host that is
briefly down. A github.com outage then fails every PR in every consumer,
for links in files the PR never touched. With a diff base, this script
demotes such a 5xx to a warning unless the link sits on a line the PR adds.
Every other failure (a 404, a network error, a timeout) still blocks.

Environment:
  LYCHEE_JSON      path to lychee's ``--format json`` report (required)
  LYCHEE_EXIT      lychee's exit code (required): 0 clean, 2 link failures,
                   anything else a tool or configuration error
  LINKS_BASE_REF   which 5xx block: ``all`` (the composite's default) means
                   every 5xx does, as lychee itself decides; empty means none
                   do (no line is known to be added, as on a push); anything
                   else is a git ref, and a 5xx blocks only when it is on a
                   line added since the merge base of that ref and HEAD
  LINKS_FAIL       ``true`` (default) exits 1 on a blocking failure
  LINKS_FAIL_IF_EMPTY  ``true`` exits 1 when lychee found no links

Exit status: 0 pass, 1 blocking failure, 2 unusable input.
"""

import json
import os
import re
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Set, Tuple

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_MAPS = ("error_map", "timeout_map")


class UnusableReport(Exception):
    """The report cannot be trusted to describe the run."""


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def _normalize_path(path: str) -> str:
    # Strip a `./` prefix only; lstrip("./") would eat the dot of `.github/`.
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        check=True, capture_output=True, text=True,
    ).stdout


def added_lines(base_ref: str) -> Dict[str, Set[int]]:
    """{repo-root-relative file: {new-file line numbers}} added since the
    merge base of base_ref and HEAD.

    Raises subprocess.CalledProcessError when git cannot compute the diff.
    The header parsing follows check-quarto-prose's _added_line_numbers.
    """
    diff = _git("diff", "--unified=0", "--no-color", f"{base_ref}...HEAD")
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


def repo_path(path: str, root: str, cwd: str) -> Optional[str]:
    """A report key as a path relative to the repository root, or None.

    lychee keys its report by each input as given: relative to the
    directory it ran in, or absolute. git's diff paths are relative to
    the repository root, so both must be brought to that form to compare.
    """
    full = path if os.path.isabs(path) else os.path.join(cwd, path)
    rel = os.path.relpath(os.path.realpath(full), os.path.realpath(root))
    if rel == ".." or rel.startswith(".." + os.sep) or os.path.isabs(rel):
        return None
    return _normalize_path(rel)


class DiffScope:
    """Blocks a 5xx only on a line the diff adds, or in a file git cannot place."""

    def __init__(self, added: Dict[str, Set[int]], tracked: Set[str], root: str, cwd: str):
        self.added, self.tracked, self.root, self.cwd = added, tracked, root, cwd

    @classmethod
    def from_git(cls, base_ref: str) -> "DiffScope":
        root = _git("rev-parse", "--show-toplevel").strip()
        tracked = {
            _normalize_path(p)
            for p in _git("-C", root, "ls-files", "-z").split("\0") if p
        }
        return cls(added_lines(base_ref), tracked, root, os.getcwd())

    def blocks(self, path: str, entry: dict) -> bool:
        rel = repo_path(path, self.root, self.cwd)
        if rel is None or rel not in self.tracked:
            # A file git does not know cannot be shown untouched, so it blocks.
            return True
        lines = self.added.get(rel, set())
        line = (entry.get("span") or {}).get("line")
        if isinstance(line, int):
            return line in lines
        # No span: treat the link as added if the file has any added line.
        return bool(lines)


def _status_code(entry: dict) -> Optional[int]:
    code = (entry.get("status") or {}).get("code")
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _int(report: dict, key: str) -> int:
    value = report.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise UnusableReport(f"its '{key}' count is missing or not an integer ({value!r})")
    return value


def failures(report: dict) -> List[Tuple[str, str, dict]]:
    """Every listed failure as (map, path, entry), checked against the report's counts."""
    listed: List[Tuple[str, str, dict]] = []
    for key in _MAPS:
        section = report.get(key, {})
        if not isinstance(section, dict) or not all(isinstance(v, list) for v in section.values()):
            raise UnusableReport(f"its '{key}' is not a mapping of file to list")
        listed += [(key, path, e) for path, entries in section.items() for e in entries]
    counted = _int(report, "errors") + _int(report, "timeouts")
    if counted != len(listed):
        raise UnusableReport(
            f"it counts {counted} error(s) and timeout(s) but lists {len(listed)}"
        )
    return listed


def classify(
    listed: List[Tuple[str, str, dict]], blocks_5xx: Callable[[str, dict], bool]
) -> Tuple[List[Tuple[str, dict]], List[Tuple[str, dict]]]:
    """Split failures into (blocking, demoted); only an error_map 5xx can be demoted."""
    blocking: List[Tuple[str, dict]] = []
    demoted: List[Tuple[str, dict]] = []
    for key, path, entry in listed:
        code = _status_code(entry)
        transient = key == "error_map" and code is not None and 500 <= code <= 599
        if transient and not blocks_5xx(path, entry):
            demoted.append((path, entry))
        else:
            blocking.append((path, entry))
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


def _scope(base_ref: str) -> Callable[[str, dict], bool]:
    if base_ref == "all":
        return lambda path, entry: True
    if base_ref == "":
        return lambda path, entry: False
    try:
        return DiffScope.from_git(base_ref).blocks
    except (subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        print(f"::warning::cannot diff against base-ref {base_ref!r} "
              f"({detail.strip()}); every 5xx blocks this run.")
        return lambda path, entry: True


def main() -> int:
    report_path = os.environ.get("LYCHEE_JSON", "")
    exit_raw = os.environ.get("LYCHEE_EXIT", "")
    base_ref = os.environ.get("LINKS_BASE_REF", "all").strip()
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
    try:
        if not isinstance(report, dict):
            raise UnusableReport("it is not a JSON object")
        total = _int(report, "total")
        listed = failures(report)
        if (lychee_exit == 2) != bool(listed):
            raise UnusableReport(
                f"lychee exited {lychee_exit} but the report lists {len(listed)} failure(s)"
            )
    except UnusableReport as exc:
        print(f"::error::lychee's JSON report is unusable: {exc}; "
              "refusing to call the run clean.")
        return 2

    blocking, demoted = classify(listed, _scope(base_ref))
    for path, entry in demoted:
        print(_annotate("warning", path, entry,
                        " (server error on a line this change does not add; not failing the check)"))
    for path, entry in blocking:
        print(_annotate("error", path, entry))

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(_summary(blocking, demoted))
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(f"blocking={len(blocking)}\ndemoted={len(demoted)}\n")

    print(f"lychee checked {total} link(s): {len(blocking)} blocking failure(s), "
          f"{len(demoted)} demoted 5xx warning(s).")

    if fail_if_empty and total == 0:
        print("::error::No links were found. This usually indicates a configuration error.")
        return 1
    if blocking and fail:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
