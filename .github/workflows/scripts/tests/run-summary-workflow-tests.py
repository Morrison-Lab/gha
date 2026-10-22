#!/usr/bin/env python3
"""Offline contract checks for the reusable issue-summary workflow."""

import argparse
import contextlib
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Optional, Tuple


# tests/ -> scripts/ -> workflows/ -> .github/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "summary.yml"
ACTION = (
    "anthropics/claude-code-action@6b6870e649b5ff408753befeaee5fc7989d4e6a9"
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
    """Replace every occurrence of an anchor only within the named step."""
    bounds = step_span(text, name)
    if bounds is None:
        return None
    body = text[bounds[0] : bounds[1]]
    if old not in body:
        return None
    return text[: bounds[0]] + body.replace(old, new) + text[bounds[1] :]


def token_step_available(token: str, model: str, has_token: str = "true") -> str:
    """Run the token step's script and return its `available` output."""
    match = re.search(r"^        run: \|\n((?:          .*\n|\n)+)", token, re.M)
    if match is None:
        return "no-script"
    script = "\n".join(
        line[10:] for line in match.group(1).splitlines()
    )
    with tempfile.TemporaryDirectory() as temporary_dir:
        output = Path(temporary_dir) / "output"
        summary = Path(temporary_dir) / "summary"
        environment = {
            "HAS_TOKEN": has_token,
            "MODEL": model,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
            "PATH": "/usr/bin:/bin",
        }
        subprocess.run(
            ["bash", "-e", "-c", script], env=environment, check=True
        )
        found = re.findall(r"^available=(.*)$", output.read_text(), re.M)
    return found[-1] if found else "unset"


def model_validation_behaves(token: str) -> bool:
    """Valid models pass; multi-line and shell-looking models are refused."""
    accepted = ["", "claude-haiku-5-5", "anthropic/claude-x:1.0"]
    refused = ["a\n--x", "a b", "a;b", "$(id)", "a\n"]
    return all(
        token_step_available(token, model) == "true" for model in accepted
    ) and all(
        token_step_available(token, model) == "false" for model in refused
    )


def check(workflow: Path) -> int:
    text = workflow.read_text(encoding="utf-8")
    token = step(text, "Check for the Claude token")
    claude = step(text, "Run Claude summary")
    extract = step(text, "Extract the summary")
    unavailable = step(text, "Log an unavailable summary")
    comment = step(text, "Comment with the summary")
    summarize_job, _, comment_job = text.partition("\n  comment:\n")
    checks = {
        "finds all summary steps": all(
            (token, claude, extract, unavailable, comment)
        ),
        "names the Claude step": re.search(
            r"^\s+id: claude$", claude, re.M
        ) is not None,
        "pins the claude-code-action SHA": ACTION in claude,
        "passes the subscription token, not an API key": (
            "claude_code_oauth_token: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"
            in claude
            and "anthropic_api_key" not in text
        ),
        "forwards the job token to skip the App-token exchange": (
            "github_token: ${{ github.token }}" in claude
        ),
        "allows the model only the Read tool": (
            '--allowedTools "Read"' in claude
            and "Bash" not in claude
        ),
        "allows Claude failure": "continue-on-error: true" in claude,
        "skips without the token": (
            "if: steps.token.outputs.available == 'true'" in claude
        ),
        "keeps the model job read-only": (
            "contents: read" in summarize_job
            and "issues: write" not in summarize_job
            and "id-token" not in text
        ),
        "gives only the comment job issues: write": (
            "issues: write" in comment_job
        ),
        "never emits an annotation": (
            "::warning" not in text and "::notice" not in text
            and "::error" not in text
        ),
        "logs a skip to the job summary": (
            'GITHUB_STEP_SUMMARY' in token
            and 'GITHUB_STEP_SUMMARY' in unavailable
        ),
        "extracts the result with a delimited output": (
            '"summary<<$delimiter"' in extract
        ),
        "validates the model input before use": (
            "MODEL: ${{ inputs.model }}" in token
            and model_validation_behaves(token)
        ),
        "comments only when a summary exists": (
            "if: needs.summarize.outputs.summary != ''" in comment_job
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
        "claude id removed": ("Run Claude summary", "        id: claude\n", ""),
        "action SHA removed": (
            "Run Claude summary",
            ACTION,
            "anthropics/claude-code-action@main",
        ),
        "oauth token removed": (
            "Run Claude summary",
            "claude_code_oauth_token:",
            "removed_token:",
        ),
        "API key added": (
            "Run Claude summary",
            "          classify_inline_comments:",
            "          anthropic_api_key: x\n          classify_inline_comments:",
        ),
        "job token override removed": (
            "Run Claude summary",
            "github_token: ${{ github.token }}",
            "github_token: x",
        ),
        "tool allowlist widened": (
            "Run Claude summary",
            '--allowedTools "Read"',
            '--allowedTools "Read,Bash"',
        ),
        "failure tolerance removed": (
            "Run Claude summary",
            "        continue-on-error: true\n",
            "",
        ),
        "token guard removed": (
            "Run Claude summary",
            "        if: steps.token.outputs.available == 'true'\n",
            "",
        ),
        "annotation added": (
            "Log an unavailable summary",
            'echo "Issue summary skipped,',
            'echo "::warning::Issue summary skipped,',
        ),
        "step summary removed": (
            "Check for the Claude token",
            '>> "$GITHUB_STEP_SUMMARY"',
            "",
        ),
        "model validation removed": (
            "Check for the Claude token",
            "A-Za-z0-9._:/-",
            "A-Za-z0-9",
        ),
        "multiline delimiter removed": (
            "Extract the summary",
            '"summary<<$delimiter"',
            '"summary=x"',
        ),
    }
    job_mutations = {
        "write grant on the model job": (
            "    permissions:\n      contents: read\n",
            "    permissions:\n      contents: read\n      issues: write\n",
        ),
        "comment permission removed": (
            "    permissions:\n      issues: write\n",
            "    permissions:\n      contents: read\n",
        ),
        "comment guard removed from the job": (
            "    if: needs.summarize.outputs.summary != ''\n",
            "",
        ),
    }

    failures = 0
    with tempfile.TemporaryDirectory() as temporary_dir:
        path = Path(temporary_dir) / "summary.yml"
        cases = {
            label: mutate_step(baseline, name, old, new)
            for label, (name, old, new) in mutations.items()
        }
        for label, (old, new) in job_mutations.items():
            cases[label] = (
                baseline.replace(old, new, 1) if old in baseline else None
            )
        for label, mutated in cases.items():
            if mutated is None or mutated == baseline:
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

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from workflow_discovery import skip_if_restored

    if skip_if_restored(args.workflow.parent, "summary workflow tests"):
        return 0

    return check(args.workflow)


if __name__ == "__main__":
    raise SystemExit(main())
