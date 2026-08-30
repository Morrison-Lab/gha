#!/usr/bin/env python3
"""Offline contract checks for the reusable issue-summary workflow."""

import argparse
import contextlib
import io
from pathlib import Path
import re
import sys
import tempfile
from typing import Optional, Tuple


# tests/ -> scripts/ -> workflows/ -> .github/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "summary.yml"
COMPATIBLE_ACTION = (
    "actions/ai-inference@a7805884c80886efc241e94a5351df715968a0ad # v2"
)


def step_span(text: str, name: str) -> Optional[Tuple[int, int]]:
    """Return one named workflow step's bounds."""
    marker = f"      - name: {name}"
    start = text.find(marker)
    if start == -1:
        return None
    following = re.search(r"^      - [A-Za-z_][A-Za-z0-9_-]*:", text[start + 1 :], re.M)
    end = len(text) if following is None else start + 1 + following.start()
    return start, end


def step(text: str, name: str) -> str:
    """Return one named workflow step, bounded by the next step."""
    bounds = step_span(text, name)
    return "" if bounds is None else text[bounds[0] : bounds[1]]


def mutate_step(text: str, name: str, old: str, new: str) -> Optional[str]:
    """Replace one anchor only within the named step."""
    bounds = step_span(text, name)
    if bounds is None:
        return None
    body = text[bounds[0] : bounds[1]]
    if old not in body:
        return None
    return text[: bounds[0]] + body.replace(old, new, 1) + text[bounds[1] :]


def check(workflow: Path) -> int:
    text = workflow.read_text(encoding="utf-8")
    inference = step(text, "Run AI inference")
    unavailable = step(text, "Report unavailable inference")
    comment = step(text, "Comment with AI summary")
    checks = {
        "finds all summary steps": all((inference, unavailable, comment)),
        "names the inference step": re.search(
            r"^\s+id: inference$", inference, re.M
        ) is not None,
        "pins the tested endpoint-compatible action SHA": (
            COMPATIBLE_ACTION in inference
        ),
        "passes the endpoint input": re.search(
            r"^\s+endpoint: \$\{\{ inputs\.endpoint", inference, re.M
        ) is not None,
        "passes the model input": re.search(
            r"^\s+model: \$\{\{ inputs\.model", inference, re.M
        ) is not None,
        "passes the complete API token fallback": (
            "token: ${{ secrets.API_KEY || secrets.OPENAI_API_KEY || "
            "github.token }}" in inference
        ),
        "allows inference failure": "continue-on-error: true" in inference,
        "reports inference failure": (
            "steps.inference.outcome == 'failure'" in unavailable
            and "::warning::Issue summary inference is unavailable" in unavailable
        ),
        "reports an empty successful response": (
            "steps.inference.outcome == 'success'" in unavailable
            and "steps.inference.outputs.response == ''" in unavailable
        ),
        "comments only after successful inference": (
            "if: steps.inference.outcome == 'success' && "
            "steps.inference.outputs.response != ''" in comment
        ),
    }

    failures = 0
    for label, passed in checks.items():
        if passed:
            print(f"OK   {label}")
        else:
            print(f"::error::{label}", file=sys.stderr)
            failures += 1
    return int(failures > 0)


def run_self_test(workflow: Path) -> int:
    """Prove each load-bearing contract fails when removed."""
    baseline = workflow.read_text(encoding="utf-8")
    mutations = {
        "inference id removed": ("Run AI inference", "        id: inference\n", ""),
        "compatible action removed": (
            "Run AI inference",
            COMPATIBLE_ACTION,
            "actions/ai-inference@bad",
        ),
        "endpoint removed": (
            "Run AI inference",
            "          endpoint:",
            "          removed-endpoint:",
        ),
        "model removed": (
            "Run AI inference",
            "          model:",
            "          removed-model:",
        ),
        "token fallback removed": (
            "Run AI inference",
            "secrets.API_KEY || secrets.OPENAI_API_KEY || github.token",
            "secrets.API_KEY",
        ),
        "failure tolerance removed": (
            "Run AI inference",
            "        continue-on-error: true\n",
            "",
        ),
        "warning step removed": (
            "Report unavailable inference",
            step(baseline, "Report unavailable inference"),
            "",
        ),
        "warning guard removed": (
            "Report unavailable inference",
            "steps.inference.outcome == 'failure'",
            "false",
        ),
        "empty response warning removed": (
            "Report unavailable inference",
            "steps.inference.outputs.response == ''",
            "false",
        ),
        "success guard removed": (
            "Comment with AI summary",
            "        if: steps.inference.outcome == 'success' && ",
            "        if: ",
        ),
        "empty response guard removed": (
            "Comment with AI summary",
            "steps.inference.outputs.response != ''",
            "true",
        ),
    }

    failures = 0
    with tempfile.TemporaryDirectory() as temporary_dir:
        path = Path(temporary_dir) / "summary.yml"
        for label, (name, old, new) in mutations.items():
            mutated = mutate_step(baseline, name, old, new)
            if mutated is None:
                print(
                    f"::error::self-test '{label}' anchor not found",
                    file=sys.stderr,
                )
                failures += 1
                continue
            path.write_text(mutated, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                mutation_passed = check(path) == 0
            if mutation_passed:
                print(
                    f"::error::self-test '{label}' was not caught",
                    file=sys.stderr,
                )
                failures += 1
            else:
                print(f"OK   self-test '{label}' is caught")
    return int(failures > 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", type=Path, default=WORKFLOW)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return run_self_test(args.workflow)
    return check(args.workflow)


if __name__ == "__main__":
    raise SystemExit(main())
