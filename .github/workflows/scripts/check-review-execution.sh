#!/usr/bin/env bash
# Shared logic for claude-code-review.yml's "Fail the check if the review did
# not complete" step, extracted to a standalone script so it can be exercised
# offline against canned execution-output fixtures (see
# .github/workflows/scripts/tests/), without a live Claude API call (#174).
#
# Usage: check-review-execution.sh <execution-file>
#
# Reads a claude-code-action execution-output file (NDJSON stream or a single
# JSON array of stream-json messages), and:
#   - fails if the file is missing, has no `result` object, or the result is
#     an error that isn't a quota/auth pre-processing rejection;
#   - writes quota_exhausted=true to $GITHUB_OUTPUT (if set) and exits 0 on a
#     zero-cost, single-turn error result (quota exhaustion / auth failure);
#   - passes a run whose result object is self-contradictory --
#     is_error:true alongside subtype:"success" -- when the transcript
#     already carries a genuine, complete verdict (gha#391). subtype:"success"
#     means the SDK's own turn loop believed it finished normally; is_error
#     being set anyway is an unexplained anomaly (root cause unestablished --
#     see gha#391), not a named SDK failure, and failing the check regardless
#     hides a completed review from every reader (gha#391's #984/#985: both
#     merged with the verdict unread). A genuine error subtype
#     (error_during_execution, error_max_turns, ...) names a specific way the
#     run broke and keeps failing unconditionally, whatever text happens to be
#     in the transcript.
#   - fails if the run's assistant text is empty/whitespace-only, or states no
#     verdict anywhere (no `### Verdict` heading, `**Verdict:**` label, or
#     `Verdict:` line in any assistant block — catches stub/placeholder
#     reviews, gha#173, Lacaedemon/sparta#590). When this ALSO has a low
#     permission_denials_count (<= STUB_RETRY_MAX_DENIALS, default 5), it
#     writes stub_review=true to $GITHUB_OUTPUT, so a caller can distinguish
#     this specific, retryable signature from other failures (a hard SDK
#     error, genuinely empty output, or a no-verdict result with a HIGH
#     denial count) and retry once — re-running has been observed to recover
#     cleanly for the low-denial case (gha#185). The denial-count cutoff
#     matters: gha#185's reproductions all had permission_denials_count 1,
#     while gha#198's separate, much-larger no-verdict pattern (a different
#     root cause, still unresolved as of this writing) had 17-35 — retrying
#     that pattern has repeatedly NOT recovered per #198's own findings, so
#     stub_review must NOT fire for it (an earlier version of this fix
#     claimed this exclusion without actually implementing it — caught in
#     review on gha#201);
#   - otherwise writes review_text_file=<path> (the verdict-bearing assistant
#     block, falling back to the final block) to $GITHUB_OUTPUT and exits 0.
#   - whenever a result object is found (success, quota-skip, stub, or hard
#     error alike), also writes total_cost_usd=<value> to $GITHUB_OUTPUT —
#     the run incurs cost regardless of how it concluded, and the caller
#     (claude-code-review.yml) surfaces it in a PR comment (gha#219).
#
# $GITHUB_OUTPUT is optional so this can run standalone in a test harness;
# when unset, output assignments are silently dropped.
set -euo pipefail

EXECUTION_FILE="${1:?usage: check-review-execution.sh <execution-file>}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"

if [[ ! -f "$EXECUTION_FILE" ]]; then
  echo "::error::Claude review produced no execution output — treating as a failed review."
  exit 1
fi
# Handles NDJSON stream or a single JSON array; grabs the last result object.
result="$(jq -s 'flatten | map(select(.type=="result")) | last // empty' "$EXECUTION_FILE")"
if [[ -z "$result" || "$result" == "null" ]]; then
  echo "::error::No result object in execution output — review did not finish."
  exit 1
fi
total_cost_usd="$(jq -r '.total_cost_usd // empty' <<< "$result")"
if [[ -n "$total_cost_usd" ]]; then
  echo "total_cost_usd=$total_cost_usd" >> "$GITHUB_OUTPUT"
fi
is_error="$(jq -r '.is_error // false' <<< "$result")"
subtype="$(jq -r '.subtype // ""' <<< "$result")"
# A verdict line: optional leading blockquote / list / heading / bold
# markers, then "verdict" (case-insensitive). Matches `### Verdict`,
# `**Verdict:**`, `Verdict:`, `> Verdict`, `- Verdict:`; a stub
# ("waiting for background agents…", "needs your approval") has none.
# Shared by the gha#391 is_error/subtype=="success" check below and the
# ordinary no-verdict check further down, so the two never drift apart.
has_verdict() {
  grep -qiE '^[[:space:]>*_#-]*verdict\b' "$1"
}
if [[ "$is_error" == "true" || "$subtype" == error_* ]]; then
  # total_cost_usd==0 with num_turns==1 means the API rejected the
  # request before any real processing — quota exhaustion, auth
  # failure, or an immediate network error. Skip gracefully. This has to
  # run before any content extraction below, and applies whether or not
  # subtype=="success" (the quota/auth rejection shape observed so far is
  # always a genuine error_* subtype, e.g. quota-exhausted.json).
  total_cost="$(jq -r '.total_cost_usd // 1' <<< "$result")"
  num_turns="$(jq -r '.num_turns // 0' <<< "$result")"
  if [[ "$total_cost" == "0" && "$num_turns" == "1" ]]; then
    echo "quota_exhausted=true" >> "$GITHUB_OUTPUT"
    echo "::warning::Claude review skipped — CLAUDE_CODE_OAUTH_TOKEN quota or auth error (zero cost, turn 1). Re-trigger the review once the quota resets."
    exit 0
  fi
fi
# Guard against a run that reports is_error:false but never actually
# produced a review — e.g. it exits after posting only an orchestration
# placeholder ("waiting for background agents...", "needs your
# approval") instead of finished findings. subtype/is_error can't catch
# this because the SDK call itself succeeded; only the content reveals
# the review never finished (gha#173, Lacaedemon/sparta#590).
#
# A *finished* review states a verdict; a stub is pure narration and
# never does. So require a verdict line — but match it leniently on two
# axes, because requiring the exact "### Verdict" heading in only the
# final block false-failed *complete* reviews (gha#172 was too strict —
# every push-triggered review red-X'd, gha#175):
#   1. Form: the code-review plugin writes the verdict as a "Verdict:"
#      label, not the "### Verdict" heading the prompt requests, so
#      accept any heading/label/bold form (`### Verdict`, `**Verdict:**`,
#      `Verdict:`).
#   2. Location: in agent mode the verdict may land in an earlier
#      assistant message, so scan ALL assistant text, not just the last
#      block.
# The text POSTED to the PR is the verdict-bearing block (below).
#
# POSTING text: the review summary is the LAST assistant block that
# carries a verdict line — not necessarily the final block, since a
# short wrap-up ("I've posted my findings") can follow it in agent mode
# (gha#173, sparta#590/#594). Fall back to the final block when no block
# carries a verdict (the check below then fails the run regardless).
#
# denials is computed here (not just at its original use site further
# below) because it also gates one of the "blocks" candidates next: a
# Bash `gh pr comment`/`gh api .../comments` call. `gh pr comment` is now
# explicitly DENIED in run-claude-review-attempt's `--disallowedTools`
# (and the reviewer prompt tells the agent to OUTPUT its review rather
# than post it), and `gh api` was never on its allowlist -- so any such
# call in the transcript was necessarily DENIED, and each denial
# increments this counter. Trusting that call's argument text as evidence
# of a posted verdict is only safe when denials is exactly zero (i.e. no
# such call was attempted) -- otherwise a denied attempt (which never
# actually posted anything) could be mistaken for a genuine review and
# skip the stub/retry safety net entirely (gha#218 review, finding 1).
# With `gh pr comment` denied this branch is now largely defensive: the
# agent is instructed not to post, and the workflow's "Post review
# comment" step publishes review_text_file itself.
#
# permission_denials_count can be JSON null, not just a genuine 0 --
# observed in real gha#391 evidence, e.g. the is-error-success-with-verdict.json
# fixture below carries permission_denials_count:null. Coalescing null to 0
# would satisfy BOTH this line's ($denials == 0) Bash-trust gate and the
# stub-retry (denials <= max_denials) gate further down, treating an UNKNOWN
# denial count as a CONFIRMED zero -- which a denied `gh pr comment` attempt
# (never actually posted) can then exploit to fake a "posted" verdict
# (confirmed empirically; gha#446 review finding 1). Coalesce to a sentinel
# far above any real denial count instead, so unknown denials read as unsafe
# on both gates rather than as zero.
denials="$(jq -r '.permission_denials_count // 999999' <<< "$result")"
# review_text_file (posted to the PR) and all_text_file (the pass/fail scan
# below) must draw from the exact same candidate blocks, or a verdict this
# script recognizes as "posted" can differ from what the PR actually shows
# (gha#218 review, finding 2). Candidates are plain assistant "text", plus
# GitHub-posting tool_use calls whose arguments can carry a verdict a plain
# text block never restates: the inline-comment MCP tool's `body` (always
# trusted; it's actually granted) and the gated Bash case above. Restricted
# to these specific posting tools so an unrelated tool_use (Read, Grep,
# WebFetch...) that merely happens to contain the word "verdict" in
# something it read can't produce a false *pass* in the other direction.
blocks_file="$(mktemp)"
jq -s --argjson denials "$denials" '
  # A gated Bash candidate is a POST command, e.g.
  #   gh pr comment N --body "$(cat <<EOF ... EOF)"
  # Its verdict-bearing text is the heredoc *body*, not the whole command
  # string. This block feeds review_text_file below, which is POSTED verbatim
  # to the PR, so using the raw command republishes a shell invocation instead
  # of the review (the "Claude finished review" comment then shows a literal
  # `gh pr comment ... <<EOF ...` block). Unwrap the heredoc body; fall back to
  # the command unchanged when there is no heredoc (a --body/-f/--body-file
  # form the pass/fail scan can still read a verdict out of). \x27 is a single
  # quote, kept as a hex escape so this jq program carries no literal quote to
  # collide with the surrounding shell single-quoting. capture yields *empty*
  # (not null) on no match, which would annihilate the pipeline, so wrap it in
  # an array and take first. review_text_file and all_text_file both derive
  # from this same unwrapped block, preserving the gha#218 (finding 2)
  # invariant that the posted text and the scanned text never diverge.
  #
  # The regex finds only the *opener*; the terminator is then located
  # line-by-line, because bash ends a heredoc on a line equal to the tag and
  # nothing else. A regex terminator loose enough to be written inline (a
  # word-boundary or leading-whitespace-tolerant \k<tag>) also matches body
  # lines that merely start with the tag, and a lazy body then stops at the
  # first of those -- silently truncating the review that gets posted (gha#318
  # review, finding 1). Comparing whole lines removes that failure mode
  # outright rather than patching anchors onto it. <<- strips leading TABS
  # from the body and terminator, so mirror that too; without the dash, the
  # terminator must sit at column 0.
  def unwrap_posted_body:
    . as $c
    | ( [ $c | capture("<<(?<dash>-?)\\x27?(?<tag>[A-Za-z0-9_]+)\\x27?[^\n]*\n(?<body>[\\s\\S]*)") ] | first ) as $h
    | if $h == null then $c
      else
        # rtrimstr strips a CRLF transcript\x27s trailing \r before BOTH the
        # terminator comparison and the slice that gets posted -- normalizing
        # only for the comparison would still leave stray \r in the review
        # body (gha#318 review round 2).
        ( $h.body | split("\n")
          | map(rtrimstr("\r")
                | if $h.dash == "-" then sub("^\t+"; "") else . end) ) as $lines
        | ( $lines | index($h.tag) ) as $end
        # No terminator (a transcript truncated mid-command): fall back to the
        # raw command rather than guess where the body ended. Posting a
        # shell-looking comment is the bug this unwrapping fixes, but dropping
        # review text is worse.
        | if $end == null then $c else $lines[0:$end] | join("\n") end
      end;
  flatten
  | [ .[] | select(.type == "assistant") | .message.content[]?
      | if .type == "text" then .text
        elif .type == "tool_use" and .name == "mcp__github_inline_comment__create_inline_comment"
          then (.input.body // "")
        elif .type == "tool_use" and .name == "Bash" and ($denials == 0)
          and ((.input.command // "") | test("gh (pr comment|api [^\n]*(pulls|issues)/[^\n]*comments)"))
          then ((.input.command // "") | unwrap_posted_body)
        else empty
        end ]
' "$EXECUTION_FILE" > "$blocks_file" 2>/dev/null || echo '[]' > "$blocks_file"
review_text_file="$(mktemp)"
jq -r '
  . as $blocks
  | ( [ $blocks[] | select(test("(?im)^[\\s>*_#-]*verdict\\b")) ] | last )
    // ( $blocks | last )
    // ""
' "$blocks_file" > "$review_text_file" 2>/dev/null || true
all_text_file="$(mktemp)"
jq -r '.[]' "$blocks_file" > "$all_text_file" 2>/dev/null || true
if [[ "$is_error" == "true" || "$subtype" == error_* ]]; then
  # gha#391: only the self-contradictory is_error:true + subtype:"success"
  # combination gets a second look, and only when the transcript we just
  # extracted already carries a genuine, complete verdict -- see the header
  # comment above for why. Anything else in this branch (a real error
  # subtype, or subtype:"success" with no verdict posted) is left exactly as
  # risky as it was before this fix: fail loudly, and don't guess at
  # retryability for a shape nobody has evidence about.
  if [[ "$subtype" == "success" ]] && has_verdict "$all_text_file"; then
    echo "::warning::Claude review reported is_error=true with subtype=success, but a complete verdict was already posted -- treating as a completed review rather than failing the check (gha#391; the is_error cause is unestablished)."
    echo "review_text_file=$review_text_file" >> "$GITHUB_OUTPUT"
    echo "Claude review completed with an anomalous is_error flag (subtype=success); a verdict was posted."
    exit 0
  fi
  echo "::error::Claude review ended in an error state (is_error=$is_error, subtype=$subtype)."
  jq '.' <<< "$result" || true
  exit 1
fi
if [[ -z "$(tr -d '[:space:]' < "$all_text_file")" ]]; then
  echo "::error::Claude review produced no review text — treating as a failed review."
  exit 1
fi
if ! has_verdict "$all_text_file"; then
  # gha#185 (low denial count, e.g. 1) vs gha#198 (high denial count,
  # 17-35) are the same textual shape — real text, is_error:false, no
  # verdict — and are only distinguishable by permission_denials_count.
  # Only the low-count case has been observed to recover on a same-prompt
  # retry; #198's pattern has repeatedly NOT recovered, so exclude it here
  # rather than let a caller retry (and re-spend $2-4/attempt) on a known
  # non-recovering pattern. (denials was already computed above, where it
  # also gates the Bash-tool-use blocks candidate.)
  max_denials="${STUB_RETRY_MAX_DENIALS:-5}"
  echo "permission_denials_count=$denials (stub-retry max_denials=$max_denials)"
  if [[ "$denials" -le "$max_denials" ]]; then
    echo "stub_review=true" >> "$GITHUB_OUTPUT"
    echo "Claude review produced no verdict with low permission_denials_count ($denials <= $max_denials) — marking as a retryable stub review (gha#185)."
  else
    echo "::warning::permission_denials_count=$denials exceeds the stub-retry threshold ($max_denials) — this looks like gha#198's pattern, not gha#185's; not marking as retryable."
  fi
  echo "::error::Claude review states no verdict (no '### Verdict' heading or 'Verdict:' line anywhere in its output) — looks like an incomplete/stub review, not a finished one (gha#173, Lacaedemon/sparta#590)."
  exit 1
fi
echo "review_text_file=$review_text_file" >> "$GITHUB_OUTPUT"
echo "Claude review completed cleanly (subtype=$subtype)."
