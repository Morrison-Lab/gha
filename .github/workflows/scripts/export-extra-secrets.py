#!/usr/bin/env python3
"""Export caller secrets to $GITHUB_ENV for agent/review workflows (gha#618).

Validates secret names against naming conventions and protected environment
variables, registers masks for values, and appends them to $GITHUB_ENV.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys

NAME_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")

PROTECTED_NAMES = frozenset({
    "CI",
    "GITHUB_ACTION",
    "GITHUB_ACTIONS",
    "GITHUB_ACTOR",
    "GITHUB_ACTION_PATH",
    "GITHUB_ACTION_REPOSITORY",
    "GITHUB_API_URL",
    "GITHUB_BASE_REF",
    "GITHUB_ENV",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_GRAPHQL_URL",
    "GITHUB_HEAD_REF",
    "GITHUB_JOB",
    "GITHUB_OUTPUT",
    "GITHUB_PATH",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REF_PROTECTED",
    "GITHUB_REF_TYPE",
    "GITHUB_REPOSITORY",
    "GITHUB_REPOSITORY_ID",
    "GITHUB_REPOSITORY_OWNER",
    "GITHUB_REPOSITORY_OWNER_ID",
    "GITHUB_RETENTION_DAYS",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TOKEN",
    "GITHUB_TRIGGERING_ACTOR",
    "GITHUB_WORKFLOW",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_WORKSPACE",
    "HOME",
    "PATH",
    "SHELL",
    "USER",
    "RUNNER_ARCH",
    "RUNNER_DEBUG",
    "RUNNER_NAME",
    "RUNNER_OS",
    "RUNNER_TEMP",
    "RUNNER_TOOL_CACHE",
    "RUNNER_WORKSPACE",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "OPENCODE_API_KEY",
    "WORKFLOW_TOKEN",
    "SUBMODULES_TOKEN",
})


def parse_secret_names(raw_input: str) -> list[str]:
    """Parse comma-, space-, or newline-separated secret names."""
    if not raw_input:
        return []
    tokens = re.split(r"[, \t\r\n]+", raw_input.strip())
    return [t for t in tokens if t]


def export_secrets(
    raw_names: str,
    secrets_json: str,
    github_env_path: str | None = None,
) -> int:
    """Validate and export requested secrets to $GITHUB_ENV."""
    names = parse_secret_names(raw_names)
    if not names:
        return 0

    try:
        secrets_map = json.loads(secrets_json) if secrets_json else {}
    except Exception as exc:
        print(f"::error::Failed to parse secrets context as JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(secrets_map, dict):
        print("::error::Secrets context is not a key-value mapping.", file=sys.stderr)
        return 1

    # Validate names first before exporting anything
    invalid_names: list[str] = []
    protected_names: list[str] = []

    for name in names:
        if not NAME_PATTERN.match(name):
            invalid_names.append(name)
        elif name in PROTECTED_NAMES:
            protected_names.append(name)

    if invalid_names:
        print(
            f"::error::Invalid secret name(s) in extra-secret-names: {', '.join(invalid_names)}. "
            "Secret names must match [A-Z_][A-Z0-9_]*.",
            file=sys.stderr,
        )
        return 1

    if protected_names:
        print(
            f"::error::Cannot export protected environment variable(s) via extra-secret-names: {', '.join(protected_names)}.",
            file=sys.stderr,
        )
        return 1

    env_file = github_env_path or os.environ.get("GITHUB_ENV")
    exported: list[str] = []
    missing: list[str] = []

    for name in names:
        if name not in secrets_map:
            missing.append(name)
            continue

        val = str(secrets_map[name])
        # Register mask with GitHub Actions runner
        if val:
            print(f"::add-mask::{val}")

        if env_file:
            delimiter = f"ghasecret_{secrets.token_hex(16)}"
            with open(env_file, "a", encoding="utf-8") as f:
                f.write(f"{name}<<{delimiter}\n{val}\n{delimiter}\n")

        exported.append(name)

    if missing:
        for m in missing:
            print(
                f"::warning::Secret '{m}' requested via extra-secret-names was not found in the inherited secrets context."
            )

    if exported:
        print(f"Exported {len(exported)} extra secret(s) to environment: {', '.join(exported)}")

    return 0


def main() -> None:
    raw_names = os.environ.get("EXTRA_SECRET_NAMES", "")
    secrets_json = os.environ.get("SECRETS_JSON", "{}")
    sys.exit(export_secrets(raw_names, secrets_json))


if __name__ == "__main__":
    main()
