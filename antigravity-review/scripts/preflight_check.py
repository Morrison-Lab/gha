#!/usr/bin/env python3
"""Preflight checker for Antigravity Action and repo conventions."""

import glob
import os
import re
import sys


def check_changelog_fragments() -> bool:
    """Ensure all changelog fragment files in changelog.d/ start with '- '."""
    passed = True
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    fragment_pattern = os.path.join(repo_root, "changelog.d", "*.md")
    for file_path in glob.glob(fragment_pattern):
        basename = os.path.basename(file_path)
        if basename == "README.md":
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
                if not lines or not lines[0].startswith("- "):
                    print(f"❌ Preflight error: {file_path} must start with a '- ' bullet point", file=sys.stderr)
                    passed = False
        except Exception as err:
            print(f"❌ Error reading {file_path}: {err}", file=sys.stderr)
            passed = False
    return passed


def extract_workflow_inputs(workflow_path: str) -> list[str]:
    """Extract input names under 'inputs:' from workflow YAML.

    Parses line-by-line tracking indentation level so parsing stops
    when indentation returns to or drops below ``inputs:``, preventing
    capture of sibling blocks like ``secrets:``.
    """
    inputs: list[str] = []
    in_inputs = False
    inputs_indent: int | None = None
    target_indent: int | None = None

    with open(workflow_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            indent = len(line) - len(line.lstrip())

            if stripped == "inputs:":
                in_inputs = True
                inputs_indent = indent
                target_indent = None
                continue

            if in_inputs:
                if indent <= inputs_indent:
                    in_inputs = False
                    continue

                if target_indent is None:
                    target_indent = indent

                if indent == target_indent and ":" in stripped:
                    key = stripped.split(":", 1)[0].strip()
                    if key:
                        inputs.append(key)

    return inputs


def check_action_docs_sync() -> bool:
    """Ensure inputs in .github/workflows/antigravity-code-review.yml are documented in website/reference/antigravity-code-review.qmd."""
    passed = True
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    workflow_path = os.path.join(repo_root, ".github", "workflows", "antigravity-code-review.yml")
    doc_path = os.path.join(repo_root, "website", "reference", "antigravity-code-review.qmd")

    if not os.path.isfile(workflow_path) or not os.path.isfile(doc_path):
        print(f"❌ Preflight error: Expected files missing: {workflow_path} or {doc_path}", file=sys.stderr)
        return False

    try:
        inputs = extract_workflow_inputs(workflow_path)
        with open(doc_path, "r", encoding="utf-8") as f:
            doc_content = f.read()

        for input_name in inputs:
            if f"`{input_name}`" not in doc_content:
                print(f"❌ Preflight error: input `{input_name}` from workflow is missing in {doc_path}", file=sys.stderr)
                passed = False
    except Exception as err:
        print(f"❌ Error checking workflow docs sync: {err}", file=sys.stderr)
        passed = False

    return passed


def main():
    print("🔍 Running Antigravity Action Preflight Checks...")
    c1 = check_changelog_fragments()
    c2 = check_action_docs_sync()
    if c1 and c2:
        print("✅ All preflight checks passed!")
        sys.exit(0)
    else:
        print("❌ Preflight checks failed. Please resolve errors above.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
