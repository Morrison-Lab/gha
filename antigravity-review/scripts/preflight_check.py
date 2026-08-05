#!/usr/bin/env python3
"""Preflight checker for Antigravity Action and repo conventions."""

import glob
import os
import sys
import yaml


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
                first_line = f.readline().strip()
                if first_line and not first_line.startswith("- "):
                    print(f"❌ Preflight error: {file_path} line 1 must start with '- '", file=sys.stderr)
                    passed = False
        except Exception as err:
            print(f"❌ Error reading {file_path}: {err}", file=sys.stderr)
            passed = False
    return passed


def check_action_docs_sync() -> bool:
    """Ensure inputs in action.yml are documented in website/reference/antigravity-code-review.qmd."""
    passed = True
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    action_path = os.path.join(repo_root, "antigravity-review", "action.yml")
    doc_path = os.path.join(repo_root, "website", "reference", "antigravity-code-review.qmd")

    if not os.path.isfile(action_path) or not os.path.isfile(doc_path):
        return True

    try:
        with open(action_path, "r", encoding="utf-8") as f:
            action_data = yaml.safe_load(f)
        inputs = action_data.get("inputs", {})

        with open(doc_path, "r", encoding="utf-8") as f:
            doc_content = f.read()

        for input_name in inputs:
            if f"`{input_name}`" not in doc_content:
                print(f"❌ Preflight error: input `{input_name}` from action.yml is missing in {doc_path}", file=sys.stderr)
                passed = False
    except Exception as err:
                print(f"❌ Error checking action docs sync: {err}", file=sys.stderr)
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
