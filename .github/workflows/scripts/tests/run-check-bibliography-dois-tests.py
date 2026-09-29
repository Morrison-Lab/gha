#!/usr/bin/env python3
"""Offline unit and integration tests for check-bibliography-dois (gha#982).

Validates:
- check-bibliography-dois.R contains retry logic for 5xx/429 and downgrades persistent 5xx to warning
- check-bibliography-dois.R guards top-level execution with sys.nframe() == 0L
- check-bibliography-dois/action.yml is valid composite action
- Reusable workflow .github/workflows/check-bibliography-dois.yml is valid workflow_call
- Executes R unit tests via Rscript if Rscript is available on PATH
"""

import shutil
import subprocess
import sys
from pathlib import Path
try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

REPO_ROOT = Path(__file__).resolve().parents[4]


def test_r_script_structure():
    failures = []
    r_script_path = REPO_ROOT / "check-bibliography-dois" / "check-bibliography-dois.R"
    if not r_script_path.exists():
        return [f"Missing R script: {r_script_path}"]

    content = r_script_path.read_text(encoding="utf-8")

    # Check for exponential backoff and retry on 5xx and 429
    required_patterns = [
        ("max_attempts", "Function parameter or loop variable max_attempts missing"),
        ("backoff_base_sec", "Exponential backoff parameter backoff_base_sec missing"),
        ("code >= 500 && code <= 599", "5xx range check missing"),
        ("code == 429", "429 rate limit check missing"),
        ("resolver unavailable, not verified", "Warning message for persistent 5xx missing"),
        ("sys.nframe() == 0L", "Guard against executing main on source missing"),
        ("check_bibliography_dois.testing", "Testing option override check missing"),
        ("warnings_count", "Tracking warnings_count missing"),
    ]

    for pattern, msg in required_patterns:
        if pattern not in content:
            failures.append(f"{pattern} not found: {msg}")

    return failures


def test_action_and_workflow_structure():
    failures = []
    action_path = REPO_ROOT / "check-bibliography-dois" / "action.yml"
    if not action_path.exists():
        return [f"Missing composite action: {action_path}"]

    if HAVE_YAML:
        with open(action_path, "r", encoding="utf-8") as f:
            action_data = yaml.safe_load(f)
        if not action_data or action_data.get("runs", {}).get("using") != "composite":
            failures.append("check-bibliography-dois/action.yml is not a composite action")
    else:
        text = action_path.read_text(encoding="utf-8")
        if "using: composite" not in text and "using: 'composite'" not in text:
            failures.append("check-bibliography-dois/action.yml does not declare using: composite")

    wf_path = REPO_ROOT / ".github" / "workflows" / "check-bibliography-dois.yml"
    if not wf_path.exists():
        return [f"Missing reusable workflow: {wf_path}"]

    if HAVE_YAML:
        with open(wf_path, "r", encoding="utf-8") as f:
            wf_data = yaml.safe_load(f)
        on_data = (wf_data.get("on") or wf_data.get(True) or {}) if wf_data else {}
        if not wf_data or "workflow_call" not in on_data:
            failures.append("check-bibliography-dois.yml is not a workflow_call workflow")
    else:
        text = wf_path.read_text(encoding="utf-8")
        if "workflow_call:" not in text and "workflow_call" not in text:
            failures.append("check-bibliography-dois.yml does not declare workflow_call")

    return failures


def test_r_unit_tests():
    rscript = shutil.which("Rscript")
    if not rscript:
        print("Rscript not found on PATH; skipping live R test execution.")
        return []

    test_file = REPO_ROOT / "check-bibliography-dois" / "tests" / "test-check-bibliography-dois.R"
    if not test_file.exists():
        return [f"Missing R test file: {test_file}"]

    proc = subprocess.run(
        [rscript, str(test_file)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [
            f"R unit tests failed (exit code {proc.returncode}):\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        ]

    print("Live R unit tests passed:\n" + proc.stdout.strip())
    return []


def main():
    all_failures = []
    all_failures.extend(test_r_script_structure())
    all_failures.extend(test_action_and_workflow_structure())
    all_failures.extend(test_r_unit_tests())

    if all_failures:
        print(f"FAILED ({len(all_failures)} failure(s)):", file=sys.stderr)
        for fail in all_failures:
            print(f"  - {fail}", file=sys.stderr)
        sys.exit(1)

    print("All check-bibliography-dois offline tests passed.")


if __name__ == "__main__":
    main()
