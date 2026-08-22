#!/usr/bin/env bash
# Classify an opencode review run's outcome from its structured facts
# (gha#586): the CLI's exit code and the byte count of its stdout.
#
# Unlike classify-gemini-failure.sh, this script does not read raw error
# text -- opencode is invoked directly by our workflow, so its exit code
# and output size are already deterministic facts rather than prose that
# needs pattern-matching. The stderr text itself is rendered into the PR
# comment by report-opencode-run (truncated there), never embedded here,
# for the same reason classify-gemini-failure.sh keeps advice free of the
# raw error (gha#380 review finding 1).
#
# Usage: classify-opencode-run.sh <exit-code> <stdout-bytes>
#
# Output contract, consumed by report-opencode-run by fixed line offset
# (the same four-part shape run-classify-gemini-failure-tests.sh pins):
#
#   kind=<review|failed>
#   headline=<single line>
#   <blank line>
#   advice lines...
#
# The failure headline always begins "OpenCode review failed:" --
# classify-review-delivery.sh keys on that exact phrase to recognize a
# failed run as not-delivered, so rewording it here silently breaks the
# ai-code-review fallback loop.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <exit-code> <stdout-bytes>" >&2
  exit 2
fi

exit_code=$1
stdout_bytes=$2
for value in "$exit_code" "$stdout_bytes"; do
  if [[ ! $value =~ ^[0-9]+$ ]]; then
    echo "$0: expected non-negative integers, got '$value'" >&2
    exit 2
  fi
done

if [[ "$exit_code" -eq 0 ]]; then
  if [[ "$stdout_bytes" -gt 0 ]]; then
    echo 'kind=review'
    echo 'headline=OpenCode review completed.'
    echo
    cat <<'EOF'
Post the review text verbatim; it is the agent's full output. A run that
completed with output is a delivered review even when it reports no findings.
EOF
    exit 0
  fi
  echo 'kind=failed'
  echo 'headline=OpenCode review failed: the agent exited successfully but produced no review.'
  echo
  cat <<'EOF'
Common causes: the model returned an empty response, or a prompt-addendum
instructed it to stay silent. Check the job log for the model's stderr,
re-run, and check https://opencode.ai/docs/zen/ for service status before
treating this as a workflow bug.
EOF
  exit 0
fi

echo "kind=failed"
echo "headline=OpenCode review failed: the CLI exited ${exit_code} without completing the review."
echo
cat <<'EOF'
A non-zero exit means the run did not complete (auth rejection, quota or
credits exhausted, transport failure). Check the raw output below and the
job log; do not retry blindly against an auth or credits failure.
EOF
