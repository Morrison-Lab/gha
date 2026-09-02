#!/usr/bin/env bash
# Builds the markdown notice claude-code-review.yml posts on a PR when the
# review was skipped for a credential or quota condition (gha#396, gha#520).
#
# The job log already tells three cases apart -- no secret configured, the
# API rejecting the first request at zero cost, and a 429 part-way through a
# review that had already spent real turns -- but the PR notice used to state
# one disjunction for all of them ("No secret is configured, or quota is
# exhausted"). After a mid-run 429 that sentence's first branch is false, and
# it sends a triager who has just repaired a secret back to the repository
# settings when the right remedy was to wait for the reset time the API had
# already named (gha#804). So the notice branches on QUOTA_REASON and quotes
# the API message when one was captured.
#
# Inputs arrive through the environment, never argv: QUOTA_MESSAGE is text the
# API returned, so it is free text rather than a fixed vocabulary.
#
#   QUOTA_REASON   missing-secret | rejected-at-door | midrun-429
#                  Anything else (including empty) renders the pre-gha#804
#                  wording, so a guard at an older tag still gets a notice
#                  rather than an error.
#   RUN_URL        required; the collapse step matches comments by this URL.
#   QUOTA_MESSAGE  optional; the API's own message, quoted verbatim.
#
# The headline always begins "Claude review skipped" because
# classify-review-delivery.sh keys on that phrase. It is joined to the
# cause by an ASCII `---`, per the no-non-ASCII-punctuation rule for source
# files; the classifier's own tests pin that both spellings match.
set -euo pipefail

if [[ -z "${RUN_URL:-}" ]]; then
  echo "::error::RUN_URL is required." >&2
  exit 1
fi

case "${QUOTA_REASON:-}" in
  missing-secret|rejected-at-door|midrun-429) reason="$QUOTA_REASON" ;;
  *) reason=unknown ;;
esac

# Single-line, so a message carrying a newline cannot escape the blockquote
# and render as an unquoted paragraph the collapse step would not fold.
message="$(printf '%s' "${QUOTA_MESSAGE:-}" | tr '\n\r' '  ')"

printf '> [!WARNING]\n'
case "$reason" in
  missing-secret)
    printf '> **Claude review skipped --- no API credential is configured.** Neither `CLAUDE_CODE_OAUTH_TOKEN` nor `ANTHROPIC_API_KEY` is set as a secret for this workflow, so no request was sent. Configure one, then re-trigger the review by pushing a new commit or re-running the workflow.\n'
    ;;
  rejected-at-door)
    printf '> **Claude review skipped --- the API rejected the first request.** A credential is configured, but the API refused the request before any work was done (zero cost, one turn): either the account quota is exhausted or the credential was not accepted. Check the run log for the cause, then re-trigger the review once the quota resets or the credential is repaired.\n'
    ;;
  midrun-429)
    printf '> **Claude review skipped --- the API returned 429 part-way through the review.** The credential is configured and was accepted; the account hit a quota or rate limit mid-run ([gha#520](https://github.com/Morrison-Lab/gha/issues/520)). Wait for the reset, then re-trigger the review by pushing a new commit or re-running the workflow.\n'
    ;;
  unknown)
    printf '> **Claude review skipped --- API credential or quota unavailable.** No `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` secret is configured, or account API quota is exhausted. Re-trigger the review by pushing a new commit or re-running the workflow once configured/reset.\n'
    ;;
esac
if [[ -n "$message" ]]; then
  printf '>\n'
  printf '> API message: %s\n' "$message"
fi
printf '>\n'
printf '> [View run](%s)\n' "$RUN_URL"
