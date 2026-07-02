#!/usr/bin/env bash
# Parses a workflow-ref string (owner/repo/.github/workflows/<file>@ref --
# the shape of both github.workflow_ref and github.job_workflow_ref) into its
# repo, path, and ref parts. Shared by every claude-code-review.yml /
# claude-review.yml step that needs to pick one of these strings apart
# (selfmod, the review-guard-script resolver, and the review-comment collapse
# step) instead of three independent inline `sed` copies (gha#191 review).
#
# Usage: bash parse-workflow-ref.sh <owner/repo/.github/workflows/file@ref>
# Prints `repo=...`, `path=...`, `ref=...` to stdout (GITHUB_OUTPUT format).
set -euo pipefail

workflow_ref="${1:?usage: parse-workflow-ref.sh <owner/repo/.github/workflows/file@ref>}"

printf 'repo=%s\n' "$(printf '%s' "$workflow_ref" | sed -E 's#^([^/]+/[^/]+)/.*#\1#')"
printf 'path=%s\n' "$(printf '%s' "$workflow_ref" | sed -E 's#^[^/]+/[^/]+/(\.github/workflows/[^@]+)@.*#\1#')"
printf 'ref=%s\n' "$(printf '%s' "$workflow_ref" | sed -E 's#.*@##')"
