"""Decide which bundled checks run and which of them block.

The check-notes-plan composite runs this for check-notes.yml (gha#1367).
DEFAULTS maps each bundled check to its composite's own `fail` default.
SKIP, FAIL_CHECKS, and WARN_CHECKS are the caller's lists, separated by
commas, spaces or newlines; `all` in FAIL_CHECKS or WARN_CHECKS names
every check. A name the bundle does not run is an error, so a typo
cannot silently leave a check on or off.
"""

import json
import os
import re
import sys


def split_names(text):
    return [name for name in re.split(r"[\s,]+", text or "") if name]


def expand(names, known):
    if "all" in names:
        return list(known)
    return names


def plan(defaults, skip, fail_checks, warn_checks):
    """Return (skip list, {check: "true"/"false"}) or raise ValueError."""
    known = list(defaults)
    errors = []
    for label, names in (("skip", skip), ("fail-checks", fail_checks),
                         ("warn-checks", warn_checks)):
        unknown = [n for n in names if n != "all" and n not in defaults]
        if unknown:
            errors.append(f"{label} names checks this bundle does not run: "
                          + ", ".join(unknown))
    if "all" in skip:
        errors.append("skip does not take `all`; leave the bundle out instead")
    fail_set = set(expand(fail_checks, known))
    warn_set = set(expand(warn_checks, known))
    both = sorted(fail_set & warn_set)
    if both:
        errors.append("named in both fail-checks and warn-checks: "
                      + ", ".join(both))
    if errors:
        raise ValueError("; ".join(errors))
    fail = {}
    for name in known:
        blocking = defaults[name]
        if name in fail_set:
            blocking = True
        if name in warn_set:
            blocking = False
        fail[name] = "true" if blocking else "false"
    return sorted(set(skip)), fail


def main():
    defaults = json.loads(os.environ["DEFAULTS"])
    try:
        skip, fail = plan(defaults, split_names(os.environ.get("SKIP")),
                          split_names(os.environ.get("FAIL_CHECKS")),
                          split_names(os.environ.get("WARN_CHECKS")))
    except ValueError as err:
        print(f"::error::{err}")
        return 2
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        out.write(f"skip={json.dumps(skip)}\n")
        out.write(f"fail={json.dumps(fail)}\n")
    blocking = sorted(n for n, v in fail.items() if v == "true" and n not in skip)
    warning = sorted(n for n, v in fail.items() if v == "false" and n not in skip)
    print(f"Running {len(fail) - len(skip)} of {len(fail)} checks.")
    print("Blocking: " + (", ".join(blocking) or "none"))
    print("Warn-only: " + (", ".join(warning) or "none"))
    print("Skipped: " + (", ".join(skip) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
