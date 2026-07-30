#!/usr/bin/env bash
#
# Scan a repository's git history for committed credentials, and report
# findings without ever printing the values themselves.
#
# Two independent measures keep values out of the log, because one of them
# failing silently is exactly the outcome this check exists to prevent:
#
#  1. gitleaks runs without --verbose, so it prints only a count. Verified
#     against gitleaks 8.30.1: dropping --verbose suppresses the finding
#     blocks entirely, even with redaction off.
#  2. gitleaks runs with --redact, so the value is replaced by "REDACTED"
#     wherever it would otherwise appear, in the JSON report included.
#
# The annotations below are then built only from RuleID, file, line, and
# commit -- never from the report's Match, Secret, or Message fields, so a
# regression in either measure above still cannot leak a value through them.
set -euo pipefail

: "${GITLEAKS_BIN_DIR:?GITLEAKS_BIN_DIR is required}"
: "${SECRETS_GENERATED_CONFIG:?SECRETS_GENERATED_CONFIG is required}"
: "${SECRETS_TARGET:?SECRETS_TARGET is required}"

log_opts="${SECRETS_LOG_OPTS:-}"
report="${SECRETS_REPORT_PATH:-${RUNNER_TEMP:-/tmp}/check-secrets-report.json}"

# Fail closed, and normalize before deciding: only an explicit "false" opts out.
# check-phi does the same (`PHI_FAIL...strip().lower() != "false"`), and for the
# one check here designed to block, matching an exact "true" would have made
# `fail: 'True'`, `fail: 'yes'`, or a trailing space silently downgrade a
# security gate to advisory while the job still reported green (gha#385 review).
fail_raw="${SECRETS_FAIL:-true}"
fail_normalized="$(printf '%s' "$fail_raw" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
if [ "$fail_normalized" = "false" ]; then
  fail=false
else
  fail=true
fi

# A shallow clone silently limits the scan to whatever commits were fetched, so
# a clean result would be a false all-clear over the history this check exists
# to cover. Refuse to gate on a partial scan; warn when only advising.
if [ "$(git -C "$SECRETS_TARGET" rev-parse --is-shallow-repository)" = "true" ]; then
  message="check-secrets: '$SECRETS_TARGET' is a shallow clone, so most of its history is unavailable to scan. Check out with fetch-depth: 0."
  if [ "$fail" = "true" ]; then
    echo "::error::$message"
    exit 1
  fi
  echo "::warning::$message"
fi

scan_args=(
  git
  --no-banner
  --redact
  # Report leaks through the JSON report rather than through the exit status,
  # so a non-zero exit means gitleaks itself failed (a malformed config, an
  # uncompilable allowlist regex) and always fails the step, whatever `fail`
  # says. Verified against gitleaks 8.30.1: with --exit-code 0, findings exit
  # 0, a bad config exits 1, and an invalid allowlist regex exits 2.
  --exit-code 0
  --config "$SECRETS_GENERATED_CONFIG"
  --gitleaks-ignore-path "$SECRETS_TARGET"
  --report-format json
  --report-path "$report"
)
if [ -n "$log_opts" ]; then
  scan_args+=(--log-opts "$log_opts")
fi
scan_args+=("$SECRETS_TARGET")

"$GITLEAKS_BIN_DIR/gitleaks" "${scan_args[@]}"

# gitleaks has already printed its own "N commits scanned" line above, which is
# the authoritative record of how much history was examined -- and it is the
# thing that distinguishes "found nothing" from "examined nothing". Don't
# restate it from `rev-list --count HEAD`: that counts unique commits reachable
# from HEAD, gitleaks counts what it walked, and on a PR merge ref the two
# genuinely differ (383 against 630 on this repo's own selftest run), so a
# second number here reads as a contradiction rather than a corroboration.
finding_count="$(jq 'length' "$report")"

echo "$finding_count finding(s); see the commit count gitleaks reported above."

if [ "$finding_count" -eq 0 ]; then
  echo "No secrets found."
  exit 0
fi

# Annotate at the level the run actually gates at, so a warn-only run does not
# paint the diff with red annotations it will not block on.
if [ "$fail" = "true" ]; then
  annotation_level=error
else
  annotation_level=warning
fi

jq -r --arg level "$annotation_level" '
  .[]
  | "::\($level) file=\(.File),line=\(.StartLine)::check-secrets: possible secret (\(.RuleID)) in commit \(.Commit[0:12]) -- value withheld; see the run summary for how to respond"
' "$report"

{
  echo "### check-secrets"
  echo ""
  echo "$finding_count possible secret(s) found in git history."
  echo "Values are withheld deliberately -- a credential in a CI log is still a credential."
  echo ""
  echo "| Rule | File | Line | Commit |"
  echo "| --- | --- | --- | --- |"
  jq -r '.[] | "| \(.RuleID) | `\(.File)` | \(.StartLine) | `\(.Commit[0:12])` |"' "$report"
  echo ""
  echo "**Rotate any credential this names before anything else.**"
  echo "Rewriting history does not un-expose it: an orphaned commit stays"
  echo "fetchable through the GitHub API until the repository is"
  echo "garbage-collected, so the value must be assumed compromised."
  echo ""
  echo "A false positive -- a fixture, a documented example -- is suppressed"
  echo "by the \`paths-ignore\` or \`allowlist-file\` input, by a"
  echo "\`gitleaks:allow\` comment on the line, or by its fingerprint in a"
  echo "\`.gitleaksignore\` file."
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

if [ "$fail" = "true" ]; then
  echo "::error::check-secrets: $finding_count possible secret(s) found in git history."
  exit 1
fi

echo "::warning::check-secrets: $finding_count possible secret(s) found in git history (fail: false, so not blocking)."
