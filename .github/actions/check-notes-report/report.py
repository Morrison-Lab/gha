"""Report each bundled check's outcome and fail when a check step failed or has no outcome.

The check-notes-report composite runs this as the last step of
check-notes.yml (gha#1367). Every check step runs with
continue-on-error, so one finding does not stop the rest; this reads
each step's `outcome`, which continue-on-error leaves as `failure`,
from STEPS (the job's `toJSON(steps)`) and CHECKS (the JSON list of
bundled checks). A check whose step is missing from STEPS
is an error, since then nothing says whether it ran. The `result`
output (`passed`, `failed` or `missing`) tells those apart.
"""

import json
import os
import sys


def summarize(steps, checks):
    """Return (rows of (check, outcome), failed checks, missing checks)."""
    rows, failed, missing = [], [], []
    for name in checks:
        step = steps.get(name)
        if step is None:
            missing.append(name)
            continue
        outcome = step.get("outcome") or "unknown"
        rows.append((name, outcome))
        if outcome != "success" and outcome != "skipped":
            failed.append(name)
    return rows, failed, missing


def write_result(result):
    """Write the `result` step output, when GitHub Actions provides one."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as out:
            out.write(f"result={result}\n")


def main():
    steps = json.loads(os.environ["STEPS"])
    checks = json.loads(os.environ["CHECKS"])
    rows, failed, missing = summarize(steps, checks)
    lines = ["| Check | Outcome |", "| --- | --- |"]
    lines += [f"| `{name}` | {outcome} |" for name, outcome in rows]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as out:
            out.write("## Bundled content checks\n\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))
    if missing:
        write_result("missing")
        print("::error::No step outcome for: " + ", ".join(missing))
        return 2
    if failed:
        write_result("failed")
        print("::error::Check steps failed (a blocking finding or an error): " + ", ".join(failed))
        return 1
    write_result("passed")
    print(f"All {len(rows)} check steps passed or were skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
