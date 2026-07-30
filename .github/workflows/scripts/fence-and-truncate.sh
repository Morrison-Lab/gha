#!/usr/bin/env bash
# Shared helpers for composing a PR/issue comment body from arbitrary,
# untrusted text. Sourced (not executed) by report-push-failure/action.yml
# and report-gemini-failure/action.yml, which both need to fence a block of
# text that may itself contain backticks, and truncate it to a byte budget
# without tripping SIGPIPE. Extracted here so a fix to either function only
# has to happen once, per CLAUDE.md's "factor shared logic into reusable
# units rather than copying it between files" (gha#380 review finding 3).
#
# Usage: source "<script-dir>/fence-and-truncate.sh"
# (callers resolve <script-dir> via github.action_path, the same mechanism
# CLASSIFY_SCRIPT already uses in both composite actions above.)

# Fence a block of arbitrary text: count the longest backtick run it
# contains and open with one more, since a fence is closed by a run of
# equal length. A patch that touches a Markdown file carries ``` lines of
# its own, which a fixed three-backtick fence would end early.
#
# `|| true` is load-bearing under `pipefail`: grep exits 1 when the text
# holds no backticks at all -- the ordinary case for a network or auth
# failure -- which makes the pipeline fail and, under `set -e`, would abort
# the whole report.
#
# Without it, whether that happens depends on the call site: a command
# substitution's subshell does not inherit `errexit` by default, so
# `x="$(fence_for ...)"` swallows it while calling this as a plain statement
# aborts. That default is not a guarantee -- `shopt -s inherit_errexit` makes
# even the substitution form abort -- so state the tolerance here rather
# than relying on either.
fence_for() {
  local longest
  longest="$( { grep -oE '`+' <<<"$1" || true; } | awk '{ if (length($0) > m) m = length($0) } END { print m + 0 }')"
  if [[ "$longest" -lt 3 ]]; then longest=2; fi
  printf '`%.0s' $(seq $((longest + 1)))
}

# Cut a string to a byte budget without a pipe on the producer side.
# `head -c` stops reading once it has its bytes, so `printf ... | head -c`
# leaves printf writing to a closed pipe for any payload past the pipe
# buffer: SIGPIPE, which pipefail and set -e turn into an aborted report.
# Going through a file removes the producer entirely. `iconv -c` drops the
# partial multibyte character a byte-wise cut can leave at the end.
#
# The caller determines whether truncation actually happened by comparing
# byte counts (e.g. `wc -c` of the input vs the output), not by comparing
# strings: this function's output goes through a command substitution at
# the call site, which strips trailing newlines, while an input read from a
# plain variable (rather than another command substitution) may still carry
# one -- a string comparison would then report a spurious truncation on
# complete input (gha#380 review finding 5).
truncate_to_bytes() {
  local text="$1" max="$2" tmp
  tmp="$(mktemp)"
  printf '%s' "$text" > "$tmp"
  if [[ "$(wc -c < "$tmp")" -le "$max" ]]; then
    printf '%s' "$text"
  else
    head -c "$max" "$tmp" | iconv -f UTF-8 -t UTF-8 -c
  fi
}
