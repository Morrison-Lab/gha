#!/usr/bin/env python3
"""Offline unit tests for audit_slide_readiness.py.

Cases:
- all green or skipped passes
- a pending, queued, failed or cancelled run blocks
- the Dependabot updater run is exempt, pending or not (the 2026-10-28 rule)
- a similarly named run is not exempt
- a caller-named exemption (the slide job itself) is honoured
- a listing shorter than total_count fails closed, as does an empty one
- paging reads every page

Usage::

    python3 run-audit-slide-readiness-tests.py
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import audit_slide_readiness as readiness  # noqa: E402

failures = 0
cases = 0


def check(name: str, got, want) -> None:
    global failures, cases
    cases += 1
    if got != want:
        failures += 1
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def run(name: str, status: str = "completed", conclusion: str | None = "success") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion}


def pager(runs: list[dict], total: int | None = None):
    """A fake fetch that serves `runs` in pages of the script's page size."""
    size = readiness.PAGE_SIZE

    def fetch(url: str) -> dict:
        page = int(url.rsplit("page=", 1)[1])
        chunk = runs[(page - 1) * size : page * size]
        return {"total_count": len(runs) if total is None else total, "check_runs": chunk}

    return fetch


def audit(runs: list[dict], exempt=("Dependabot",), total: int | None = None) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return readiness.audit("o/r", "abc", set(exempt), pager(runs, total))


green = [run("test"), run("lint", conclusion="skipped"), run("docs", conclusion="neutral")]
check("all green or skipped passes", audit(green), 0)
check("in-progress blocks", audit(green + [run("build", "in_progress", None)]), 1)
check("queued blocks", audit(green + [run("build", "queued", None)]), 1)
check("failure blocks", audit(green + [run("build", conclusion="failure")]), 1)
check("cancelled blocks", audit(green + [run("build", conclusion="cancelled")]), 1)
check(
    "Dependabot pending is exempt",
    audit(green + [run("Dependabot", "in_progress", None)]),
    0,
)
check(
    "similarly named run is not exempt",
    audit(green + [run("Dependabot / check", "in_progress", None)]),
    1,
)
check(
    "caller-named exemption is honoured",
    audit(green + [run("slide", "in_progress", None)], exempt=("Dependabot", "slide")),
    0,
)
check("a short listing fails closed", audit(green, total=len(green) + 1), 2)
check("no runs fails closed", audit([]), 2)

many = [run(f"job-{i}") for i in range(250)]
fetched, total = readiness.list_check_runs("o/r", "abc", pager(many))
check("paging reads every page", (len(fetched), total), (250, 250))
check("a blocker on the last page is found", audit(many + [run("late", "in_progress", None)]), 1)

print(f"{cases - failures} of {cases} cases passed")
sys.exit(1 if failures else 0)
