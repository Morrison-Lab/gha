#!/usr/bin/env python3
"""Regression tests for triage-backlog.py.

The load-bearing property is coverage: every input issue yields exactly one
plan row, so the summary's examined count equals the input count.  The
per-bucket cases are negative controls in the fail-fast sense -- each bucket
is shown to be reachable on a synthetic fixture, so a zero in that bucket
against the real backlog is a measurement rather than an unrun rule.
"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "tb", Path(__file__).parent.parent / "triage-backlog.py"
)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)

passes = 0
failures = 0


def check(name, condition):
    global passes, failures
    if condition:
        print(f"PASS: {name}")
        passes += 1
    else:
        print(f"FAIL: {name}")
        failures += 1


FIXTURE = [
    {"number": 1, "title": "test", "labels": []},
    {"number": 2, "title": "no-foo.py blocks every push after a retraction", "labels": []},
    {"number": 3, "title": "question everything", "labels": []},
    {"number": 4, "title": "review https://example.com/some-repo", "labels": []},
    {"number": 5, "title": "should gia always be a conductor session?", "labels": []},
    {"number": 6, "title": "check-thing.py reports a breach but never an approach", "labels": []},
    {"number": 7, "title": "run oppo", "labels": []},
    {"number": 8, "title": "run oppo", "labels": [{"name": "enhancement"}]},
    {"number": 9, "title": "sync-nlb-checker.py runs the sync on --help", "labels": ["bug"]},
    {"number": 10, "title": "Revisit adding a project .mcp.json", "labels": ["low-priority"]},
    {"number": 11, "title": "already triaged item", "labels": ["P2"]},
    {"number": 12, "title": "Fix bug", "labels": []},
    {"number": 13, "title": "no sacred cows", "labels": []},
    {"number": 14, "title": "ping", "labels": ["P1"]},
    {"number": 15, "title": "Fix bug", "labels": ["P3"]},
]

plan = tb.classify(FIXTURE, {})
by = {r["number"]: r for r in plan}

check("one row per input issue", len(plan) == len(FIXTURE))
check("junk title is not-planned", by[1]["disposition"] == "not-planned")
check("severe phrase is P1", by[2]["disposition"] == "P1")
check("bare aphorism is P3", by[3]["disposition"] == "P3")
check("reading assignment URL is P3", by[4]["disposition"] == "P3")
check("question is P3", by[5]["disposition"] == "P3")
check("ordinary defect defaults to P2", by[6]["disposition"] == "P2")
check("older of two same-title issues keeps its disposition", by[7]["disposition"] == "P3")
check("newer same-title issue is duplicate of the older", by[8]["disposition"] == "duplicate" and by[8]["duplicate_of"] == 7)
check("bug label without severe phrase is P2", by[9]["disposition"] == "P2")
check("low-priority label is P3", by[10]["disposition"] == "P3")
check("existing priority label is kept", by[11]["disposition"] == "P2" and "already" in by[11]["reason"])
check("short title with an action verb is P2", by[12]["disposition"] == "P2")
check("short title with no action verb is P3", by[13]["disposition"] == "P3")
check("junk title with an existing priority label keeps the label", by[14]["disposition"] == "P1")

plan2 = tb.classify(FIXTURE, {3: "P1", 8: "P3"})
by2 = {r["number"]: r for r in plan2}
check("override replaces heuristic", by2[3]["disposition"] == "P1")
check("override clears duplicate marking", by2[8]["disposition"] == "P3" and by2[8]["duplicate_of"] is None)

# --apply --dry-run: every non-skipped row yields exactly one gh call, and a
# row already carrying its label yields none.
import contextlib
import io

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    calls = tb.apply_plan(plan, None, dry_run=True)
check("dry-run call count skips the already-labelled rows", calls == len(plan) - 2)
check("a labelled issue with an older title twin is still a duplicate",
      by[15]["disposition"] == "duplicate" and by[15]["labels"] == ["P3"])
check("not-planned close carries a reason comment",
      "close 1 --reason not planned --comment Closed by the triage pass: junk title." in buf.getvalue())

# --labels-only: the close rows are skipped, neither closed nor labelled, and
# every label row still runs.
buf_lo = io.StringIO()
with contextlib.redirect_stdout(buf_lo):
    calls_lo = tb.apply_plan(plan, None, dry_run=True, labels_only=True)
closes = sum(1 for r in plan if r["disposition"] in tb.CLOSE_DISPOSITIONS)
check("the fixture holds both kinds of close row", closes == 3)
check("labels-only drops exactly the close rows", calls_lo == calls - closes)
check("labels-only issues no close command", " close " not in buf_lo.getvalue())
close_numbers = [r["number"] for r in plan if r["disposition"] in tb.CLOSE_DISPOSITIONS]
lo_lines = buf_lo.getvalue().splitlines()
check("labels-only issues no command for a close row, labelled or not",
      not any(f" issue edit {n} " in line or f" issue close {n} " in line
              for n in close_numbers for line in lo_lines))
check("labels-only still labels", "edit 2 --add-label P1" in buf_lo.getvalue())

check("ceiling report over",
      tb.ceiling_report(889, 600)
      == "open issues at the start of this run: 889, over the ceiling of 600 by 289")
check("ceiling report at the ceiling is within it",
      tb.ceiling_report(600, 600)
      == "open issues at the start of this run: 600, within the ceiling of 600")
check("a ceiling of zero is over as soon as one issue is open",
      "over the ceiling of 0 by 1" in tb.ceiling_report(1, 0))

# A fetch that fills its limit may be truncated, and must not pass as a count.
try:
    tb.check_not_truncated(1000, 1000)
    check("a fetch that fills its limit is refused", False)
except tb.TruncatedFetch:
    check("a fetch that fills its limit is refused", True)
try:
    tb.check_not_truncated(999, 1000)
    check("a fetch under its limit passes", True)
except tb.TruncatedFetch:
    check("a fetch under its limit passes", False)

# The command line: --labels-only without --apply is refused, and --ceiling
# reports on stderr without changing the exit status.
import json
import subprocess
import tempfile

SCRIPT = str(Path(__file__).parent.parent / "triage-backlog.py")
with tempfile.TemporaryDirectory() as tmp:
    fixture_path = str(Path(tmp) / "open.json")
    with open(fixture_path, "w", encoding="utf-8") as fh:
        json.dump(FIXTURE, fh)
    run = subprocess.run(
        [sys.executable, SCRIPT, "--input", fixture_path, "--labels-only"],
        capture_output=True, text=True, timeout=30,
    )
    check("--labels-only without --apply is a usage error", run.returncode == 2)
    run = subprocess.run(
        [sys.executable, SCRIPT, "--input", fixture_path, "--ceiling", "5"],
        capture_output=True, text=True, timeout=30,
    )
    check("--ceiling over the bound still exits 0", run.returncode == 0)
    check("--ceiling reports the count on stderr",
          f"this run: {len(FIXTURE)}, over the ceiling of 5 by {len(FIXTURE) - 5}" in run.stderr)
    run = subprocess.run(
        [sys.executable, SCRIPT, "--input", fixture_path, "--ceiling", "-1"],
        capture_output=True, text=True, timeout=30,
    )
    check("a negative --ceiling is a usage error", run.returncode == 2)
    run = subprocess.run(
        [sys.executable, SCRIPT, "--input", fixture_path, "--limit", "0"],
        capture_output=True, text=True, timeout=30,
    )
    check("a --limit below 1 is a usage error", run.returncode == 2)
    run = subprocess.run(
        [sys.executable, SCRIPT, "--input", fixture_path,
         "--apply", "--dry-run", "--labels-only"],
        capture_output=True, text=True, timeout=30,
    )
    check("--apply --dry-run --labels-only exits 0", run.returncode == 0)
    check("it says how many closes it held back",
          "left 3 proposed closes for the attended pass" in run.stderr)
    check("and prints no close command", " close " not in run.stdout)

check("comment count reads ints", tb.comment_count(3) == 3)
check("comment count reads lists", tb.comment_count([{}, {}]) == 2)
check("comment count reads gh totalCount objects", tb.comment_count({"totalCount": 4}) == 4)

try:
    tb.parse_override("5=P9")
    check("bad override disposition is rejected", False)
except Exception:
    check("bad override disposition is rejected", True)

print(f"\n{passes} passed, {failures} failed")
sys.exit(1 if failures else 0)
