#!/usr/bin/env bash
# Classify a failed `google-github-actions/run-gemini-cli` call from its
# `error` output, and say what to do about it.
#
# gemini.yml and gemini-code-review.yml both call run-gemini-cli with no
# error handling at all: a failed call (quota exhaustion, an auth rejection,
# a suspended project) just red-X's the job with the raw error in the log --
# no PR-visible explanation, and indistinguishable from a genuine bug. This
# script turns that output into a named failure kind plus advice a human can
# act on, so the calling composite action can report a quota/auth failure as
# a graceful skip instead of a bare failure, and a genuine failure as a real
# one.
#
# Deliberately narrower than classify-push-failure.sh: there is no patch to
# withhold and no credential to redact here, since run-gemini-cli's error
# output is API error text, not a git push log. This script does not embed
# the raw error output itself -- that's left to the calling composite
# action, the same way classify-push-failure.sh leaves the raw log to
# report-push-failure -- since safely fencing arbitrary text (which can
# itself contain backticks, e.g. a JSON error blob) needs the same
# longest-backtick-run logic report-push-failure already has, and
# duplicating it here would be a second copy to keep in sync.
#
# Usage: bash classify-gemini-failure.sh <error-output-file>
#        bash classify-gemini-failure.sh -               # read stdin
#
# Output (stdout), in this exact shape so the caller can split it:
#
#   line 1  kind=<quota-or-auth|other>
#   line 2  headline=<single-line summary, safe for ::error:: / ::warning::>
#   line 3  (blank)
#   line 4+ Markdown advice (does NOT include the raw error output)
#
# The advice is Markdown because its other destination is a PR/issue comment.
set -euo pipefail

source_arg="${1:--}"
if [[ "$source_arg" == "-" ]]; then
  err="$(cat)"
else
  err="$(cat "$source_arg")"
fi

# One class to graceful-skip: quota, rate-limit, auth, and suspension all
# look the same from the caller's side -- the key currently cannot be used --
# and all share the same correct response: don't retry, tell a human. Anything
# else (a malformed prompt, a network blip, a genuine bug) must NOT match
# here, or a real failure would be silently swallowed as a graceful skip.
#
# Every alternative below must be a marker distinctive to a quota/auth/
# suspension rejection, not a generic word or bare status code -- `error`
# here is run-gemini-cli's raw stderr whenever stderr isn't valid JSON
# (confirmed against google-github-actions/run-gemini-cli's action.yml at the
# pinned SHA: it falls back to `cat "${TEMP_STDERR}"`), so this runs against
# realistic multi-line stack traces, not just the clean JSON envelopes the
# test fixtures use. A bare `429`/`401`/`403` matches a Node stack trace's
# line:column numbers (e.g. `index.js:4291:17`); bare `disabled`/`billing`
# match unrelated MCP log lines (e.g. "tool X disabled by includeTools
# filter"); bare `quota` matches prose that merely mentions the word. Each of
# those was dropped or anchored to actual error context instead: a numeric
# code only counts next to a `"code":` JSON key or an `HTTP` status line, and
# `quota`/`suspended` only count paired with the word that makes them an
# error rather than incidental prose.
if grep -qiE 'RESOURCE_EXHAUSTED|PERMISSION_DENIED|UNAUTHENTICATED|API_KEY_INVALID|api key not valid|has been suspended|too.?many.?requests|rate.?limit|quota.{0,20}(exceeded|exhausted)|"code"[[:space:]]*:[[:space:]]*"?(401|403|429)|\bhttp[^a-z0-9]{0,10}(401|403|429)\b' <<<"$err"; then
  kind=quota-or-auth
  headline='Gemini review skipped: the API key is rate-limited, unauthorized, or the project is suspended.'
  advice=$(
    cat <<'EOF'
The Gemini API rejected this request -- a quota/rate-limit error, an
authentication failure, or the project behind `GEMINI_API_KEY` has been
suspended. This is **not retried automatically**: retrying against a
suspended or rate-limited key wastes CI time and can look like continued
automated abuse to Google, which is the opposite of what should happen here.

If this persists, check the Google Cloud / AI Studio project status for the
associated API key. A suspended project has to be resolved with Google
directly (via an appeal), not by re-running this workflow.
EOF
  )
else
  kind=other
  headline='Gemini CLI failed for a reason other than quota/auth/suspension.'
  advice=$(
    cat <<'EOF'
The Gemini CLI run failed for a reason this workflow does not recognize as a
quota, authentication, or suspension error. The raw error output is included
below -- read it first; common causes are a malformed prompt, a transient
network error, or a genuine bug in this workflow.
EOF
  )
fi

printf 'kind=%s\n' "$kind"
printf 'headline=%s\n' "$headline"
printf '\n'
printf '%s\n' "$advice"
