#!/usr/bin/env python3
# check-one-function-per-file: allow-multiple
"""Assign a priority to every open issue, and name the ones to close.

The backlog grew from 15 to 410 open issues between 2026-07-20 and
2026-09-03 (ai-config#3134) with no triage step anywhere in the corpus:
nothing filed was ever declined, and 67% of open issues had never been
commented on.  This instrument is the deterministic half of the weekly
triage pass in shared/workflow/triage-backlog.md.  It reads the open issues,
assigns each one of P1 / P2 / P3 / not-planned / duplicate from the title
and existing labels, and prints the plan.  With --apply it performs the
label and close operations through gh.

The rules are keyword heuristics, so the plan is a proposal for a reader to
correct with --override, not a verdict.  What the instrument guarantees is
coverage: every open issue gets exactly one disposition, and the summary
reports how many were examined, so a zero in any bucket is visible as a
zero rather than as an unrun check.

Usage:
    python3 scripts/triage-backlog.py                   # fetch via gh, print plan
    python3 scripts/triage-backlog.py --input open.json # offline plan
    python3 scripts/triage-backlog.py --override 2937=P3 --override 3099=P1
    python3 scripts/triage-backlog.py --json > plan.json
    python3 scripts/triage-backlog.py --apply           # label and close via gh
    python3 scripts/triage-backlog.py --apply --labels-only   # label, never close
    python3 scripts/triage-backlog.py --ceiling 600     # report the count against a ceiling

--labels-only is the mode for an unattended, scheduled run (ai-config#3147).
A wrong priority costs one label edit, so the heuristics may apply it with
nobody reading; a close stays behind the read-every-close-row step in
skills/triage/SKILL.md.  A row the plan would close is left exactly as it
is, so the attended pass proposes the same close again.

--ceiling N reports the open count against N, the bound the backlog is meant
to stay under (ai-config#5306).  It has no default: the number is the
maintainer's to choose.  Over the ceiling the run still exits 0, because the
count is a measurement for a reader and labelling must not stop on it.  The
count is taken when the issues are read, before this run closes any.

The fetch asks gh for at most --limit issues (default 1000) and stops with an
error when it gets exactly that many, because gh truncates silently and a
truncated list would make the examined count and the ceiling report a floor.

Input JSON is a list of objects carrying at least `number` and `title`;
`labels` (a list of names or of {name} objects), `created_at`/`createdAt`,
and `comments` (an int or a list) are read when present.  That is the shape
`gh issue list --json number,title,labels,createdAt,comments` emits, and
the shape the GitHub REST and MCP search endpoints emit.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter

PRIORITY_LABELS = ("P1", "P2", "P3")

# A title that is only a test of the filing mechanism.
JUNK_TITLES = {"test", "probe", "testing", "ping"}

# Severe: blocks work, merges bad state, or hides a failure.  Any one of these
# in the title is P1.  Each alternative is anchored on a phrase a defect report
# uses rather than on a topic word, so that a discussion *about* deadlocks is
# not itself P1.
RX_SEVERE = re.compile(
    r"merged over|merged with|unaddressed .* merged|deadlock"
    r"|blocks? (?:every|all|each|the push|a push|retraction)"
    r"|den(?:y|ies) every|is inert|are inert|never (?:reach|fires|runs|discharges)"
    r"|red on main|turned .* red|corrupts?\b|silently (?:discard|los[et]|drop)"
    r"|secret|credential|bypass(?:es|ed)?\b|not in force"
    r"|no mechanical enforcement|fail-open|fails? open|undischargeable"
    r"|cannot (?:classify|see|resolve|load)|every (?:tool call|run|round|open PR)",
    re.I,
)

# Low: a directive with no acceptance criterion, a question, a reading
# assignment, or a nice-to-have.  Checked after severe, so a severe defect
# phrased as a question still lands at P1.
RX_LOW_START = re.compile(
    r"^(?:review|study|examine|assimilate|read|incorporate|consider|should|is it"
    r"|what can we|turn this|rename|run oppo|help me|question everything"
    r"|less is more|always|never|any time|when you|when |if |as part of"
    r"|implement best|write down|get under|import content|compose|prefer|suggest"
    r"|add a (?:skill|command|shortcut|workflow that)|build a semantic|ums philosophy)\b",
    re.I,
)
RX_LOW_ANY = re.compile(r"https?://|\?\s*$", re.I)

# An imperative that names concrete work.  A short title carrying one of these
# is an ordinary task ("Fix bug", "Update README"), not a bare directive.
RX_ACTION_VERB = re.compile(
    r"\b(?:fix|add|update|remove|delete|rename|split|extract|document|implement"
    r"|support|handle|refactor|improve|move|check|warn|detect|guard|record|bank"
    r"|promote|migrate|pin|bump|drop|replace|restore|install|register|sync)\b",
    re.I,
)


def label_names(labels) -> list[str]:
    out = []
    for lab in labels or []:
        name = lab.get("name") if isinstance(lab, dict) else lab
        if name:
            out.append(str(name))
    return out


def comment_count(value) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return int(value.get("totalCount", 0))
    return int(value or 0)


def norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def classify_one(title: str, labels: list[str]) -> tuple[str, str]:
    """Return (disposition, reason) for a single issue, ignoring duplicates."""
    for p in PRIORITY_LABELS:
        if p in labels:
            return p, f"already labelled {p}"
    t = norm_title(title)
    if t in JUNK_TITLES:
        return "not-planned", "junk title"
    m = RX_SEVERE.search(title)
    if m:
        return "P1", f"severe phrase: {m.group(0)!r}"
    if "bug" in labels:
        return "P2", "labelled bug"
    if "low-priority" in labels:
        return "P3", "labelled low-priority"
    m = RX_LOW_START.match(title) or RX_LOW_ANY.search(title)
    if m:
        return "P3", f"directive/question/reading: {m.group(0)!r}"
    words = title.split()
    if (
        len(words) <= 5
        and not re.search(r"[:/.]", title)
        and not RX_ACTION_VERB.search(title)
    ):
        return "P3", "bare directive (short title, no referent, no action verb)"
    return "P2", "default: actionable defect or improvement"


def classify(issues: list[dict], overrides: dict[int, str]) -> list[dict]:
    """Return one plan row per issue.  Every input issue yields exactly one row."""
    by_title: dict[str, list[dict]] = {}
    for iss in issues:
        by_title.setdefault(norm_title(iss["title"]), []).append(iss)
    plan = []
    for iss in issues:
        num = int(iss["number"])
        labels = label_names(iss.get("labels"))
        disp, reason = classify_one(iss["title"], labels)
        dup_of = None
        siblings = by_title[norm_title(iss["title"])]
        if len(siblings) > 1 and disp != "not-planned":
            oldest = min(int(s["number"]) for s in siblings)
            if num != oldest:
                disp, reason, dup_of = "duplicate", f"same title as #{oldest}", oldest
        if num in overrides:
            disp, reason = overrides[num], "override"
            dup_of = None
        plan.append(
            {
                "number": num,
                "title": iss["title"],
                "labels": labels,
                "comments": comment_count(iss.get("comments")),
                "created": iss.get("created_at") or iss.get("createdAt") or "",
                "disposition": disp,
                "reason": reason,
                "duplicate_of": dup_of,
            }
        )
    return plan


DEFAULT_FETCH_LIMIT = 1000


class TruncatedFetch(RuntimeError):
    """gh returned as many issues as the limit, so more may exist."""


def check_not_truncated(count: int, limit: int) -> None:
    """Raise when a fetch filled its limit: gh truncates without saying so."""
    if count >= limit:
        raise TruncatedFetch(
            f"gh returned {count} open issues, the --limit of {limit}; "
            "the list may be truncated, so raise --limit and run again"
        )


def fetch_open_issues(repo: str | None, limit: int = DEFAULT_FETCH_LIMIT) -> list[dict]:
    cmd = [
        "gh", "issue", "list", "--state", "open", "--limit", str(limit),
        "--json", "number,title,labels,createdAt,comments",
    ]
    if repo:
        cmd += ["-R", repo]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    issues = json.loads(out.stdout)
    check_not_truncated(len(issues), limit)
    return issues


CLOSE_DISPOSITIONS = ("not-planned", "duplicate")


def ceiling_report(open_count: int, ceiling: int) -> str:
    """One line stating the open count, as read before any close, against the
    ceiling."""
    if open_count > ceiling:
        return (
            f"open issues at the start of this run: {open_count}, "
            f"over the ceiling of {ceiling} by {open_count - ceiling}"
        )
    return f"open issues at the start of this run: {open_count}, within the ceiling of {ceiling}"


def apply_plan(
    plan: list[dict],
    repo: str | None,
    dry_run: bool,
    labels_only: bool = False,
) -> int:
    """Perform the label and close operations.  Returns the count of gh calls.

    With `labels_only`, a row the plan would close is skipped: it is not closed
    and its labels are not changed."""
    base = ["gh", "issue"]
    tail = ["-R", repo] if repo else []
    calls = 0
    for row in plan:
        n = str(row["number"])
        disp = row["disposition"]
        if labels_only and disp in CLOSE_DISPOSITIONS:
            continue
        if disp in PRIORITY_LABELS:
            if disp in row["labels"]:
                continue
            remove = [p for p in PRIORITY_LABELS if p in row["labels"] and p != disp]
            cmd = base + ["edit", n, "--add-label", disp] + tail
            for old in remove:
                cmd += ["--remove-label", old]
        elif disp == "not-planned":
            cmd = base + ["close", n, "--reason", "not planned", "--comment",
                          f"Closed by the triage pass: {row['reason']}."] + tail
        elif disp == "duplicate":
            cmd = base + ["close", n, "--reason", "not planned", "--comment",
                          f"Duplicate of #{row['duplicate_of']}."] + tail
        else:
            raise ValueError(f"unknown disposition {disp!r} on #{n}")
        calls += 1
        if dry_run:
            print("DRY-RUN:", " ".join(cmd))
        else:
            subprocess.run(cmd, check=True)
    return calls


def parse_override(text: str) -> tuple[int, str]:
    num, _, disp = text.partition("=")
    if disp not in PRIORITY_LABELS + ("not-planned",):
        raise argparse.ArgumentTypeError(
            f"override disposition must be one of P1, P2, P3, not-planned; got {disp!r}"
        )
    return int(num), disp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", help="JSON file of open issues (default: fetch via gh)")
    ap.add_argument("-R", "--repo", help="owner/repo for gh (default: current)")
    ap.add_argument("--override", action="append", default=[], type=parse_override,
                    metavar="N=P", help="force issue N to disposition P")
    ap.add_argument("--json", action="store_true", help="emit the plan as JSON")
    ap.add_argument("--apply", action="store_true", help="perform the plan via gh")
    ap.add_argument("--dry-run", action="store_true", help="with --apply, print commands only")
    ap.add_argument("--labels-only", action="store_true",
                    help="with --apply, add priority labels and close nothing")
    ap.add_argument("--limit", type=int, default=DEFAULT_FETCH_LIMIT, metavar="N",
                    help="most issues to fetch via gh; the run stops if gh returns this many")
    ap.add_argument("--ceiling", type=int, metavar="N",
                    help="report the open count against a ceiling of N")
    args = ap.parse_args(argv)
    if args.labels_only and not args.apply:
        ap.error("--labels-only changes what --apply does; pass --apply with it")
    if args.ceiling is not None and args.ceiling < 0:
        ap.error("--ceiling must not be negative")
    if args.limit < 1:
        ap.error("--limit must be at least 1")

    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            issues = json.load(fh)
    else:
        try:
            issues = fetch_open_issues(args.repo, args.limit)
        except TruncatedFetch as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    plan = classify(issues, dict(args.override))

    if args.json:
        json.dump(plan, sys.stdout, indent=1)
        print()
    else:
        for row in sorted(plan, key=lambda r: (r["disposition"], r["number"])):
            extra = f" (dup of #{row['duplicate_of']})" if row["duplicate_of"] else ""
            print(f"{row['disposition']:<11} #{row['number']:<5} {row['title'][:90]}{extra}")
            print(f"{'':11} {'':6} reason: {row['reason']}")
    counts = Counter(r["disposition"] for r in plan)
    print(f"\nexamined {len(plan)} open issues:", dict(sorted(counts.items())), file=sys.stderr)
    if len(plan) != len(issues):
        print("ERROR: plan row count differs from input count", file=sys.stderr)
        return 2

    if args.apply:
        n = apply_plan(plan, args.repo, args.dry_run, args.labels_only)
        print(f"{'planned' if args.dry_run else 'performed'} {n} gh operations", file=sys.stderr)
        if args.labels_only:
            held = sum(1 for r in plan if r["disposition"] in CLOSE_DISPOSITIONS)
            print(f"left {held} proposed closes for the attended pass", file=sys.stderr)
    if args.ceiling is not None:
        print(ceiling_report(len(plan), args.ceiling), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
