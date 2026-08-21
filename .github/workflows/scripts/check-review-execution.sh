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
#   - fails if the file is missing or has no `result` object, writing
#     action_short_circuit=true alongside no_execution_file=true or no_result=true
#     to $GITHUB_OUTPUT (gha#368);
#   - fails if the result is an error that isn't a quota/auth pre-processing rejection;
#   - writes quota_exhausted=true to $GITHUB_OUTPUT (if set) and exits 0 on a
#     zero-cost, single-turn error result (quota exhaustion / auth failure),
#     and likewise on an error result carrying api_error_status:429, which is
#     the same exhaustion reached part-way through a review rather than at the
#     door (gha#520) -- that one has real turns and real cost behind it, so the
#     zero-cost test cannot see it;
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
  echo "action_short_circuit=true" >> "$GITHUB_OUTPUT"
  echo "no_execution_file=true" >> "$GITHUB_OUTPUT"
  echo "::error::Claude review produced no execution output (action short-circuit / setup failure; gha#368) — treating as a failed review."
  exit 1
fi
# Handles NDJSON stream or a single JSON array; grabs the last result object.
result="$(jq -s 'flatten | map(select(.type=="result")) | last // empty' "$EXECUTION_FILE")"
if [[ -z "$result" || "$result" == "null" ]]; then
  echo "action_short_circuit=true" >> "$GITHUB_OUTPUT"
  echo "no_result=true" >> "$GITHUB_OUTPUT"
  echo "::error::No result object in execution output — review did not finish (action short-circuit; gha#368)."
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
max_denials="${STUB_RETRY_MAX_DENIALS:-5}"
# `.permission_denials_count` is the scalar this script has always read, but a
# real production run (gha#531) carried NO such key -- only `permission_denials`,
# an array of per-denial detail objects, with the scalar count nowhere in the
# saved execution file. (`claude-code-action` prints a formatted
# "permission_denials_count": N line to the job log in that case, but that's a
# display value it computes itself, not a field literally present in the JSON
# it writes to disk.) Falling straight to the MISSING sentinel there forces
# denials=999999, which wrongly excludes a run from the gha#185 stub-retry
# even when the real count is well within max_denials. Fall back to the
# array's length before giving up -- .permission_denials_count is tried
# first so every existing (scalar-only) fixture is unaffected.
raw_denials="$(jq -r '
  .permission_denials_count
  // (if (.permission_denials | type) == "array" then (.permission_denials | length) else null end)
  // "MISSING"
' <<< "$result")"
# `denials` alone cannot answer "were there denials?", because the 999999
# sentinel below means UNKNOWN rather than "a great many". That conflation is
# safe for the two gates it was designed for (both want unknown to read as
# unsafe), and unsafe for any statement ABOUT the denials -- so the reporting
# added for gha#540 tracks knownness separately rather than re-deriving it
# from a magic number (gha#544 review).
denials_known=true
if [[ "$raw_denials" =~ ^[0-9]+$ ]]; then
  denials="$raw_denials"
else
  echo "::warning::permission_denials_count could not be parsed from execution result (got '$raw_denials'); defaulting to sentinel 999999 (gha#370)."
  denials=999999
  denials_known=false
fi
echo "denials=$denials" >> "$GITHUB_OUTPUT"
echo "permission_denials_count=$denials (max_denials=$max_denials)"
# gha#540: the count on its own is not actionable. Two readers of the same
# `permission_denials_count=24` warning reached a wrong cause for the failure
# because the log never named which tools were denied
# (Morrison-Lab/ai-config#1773), and a later 12-denial run on
# Morrison-Lab/wai#83 left a hypothesis (sub-agent spawns? file reads?) that
# one line of log would have settled. The names are already in the execution
# file -- `permission_denials` is an array of per-denial objects carrying
# `tool_name` and `tool_input` -- so summarize them beside the count.
#
# Emitted HERE, next to the count, rather than only inside the
# over-threshold branch far below. The low-count (gha#185) case is retried
# and can stub a second time, and "what was denied, both times" is the same
# diagnostic question; keeping one extraction site also stops the two jq
# filters drifting apart the way `detect-review-request`'s two copies of one
# pattern did.
#
# The array can be ABSENT even when the scalar count is present --
# stub-gha198-high-denial-count.json is a real-shaped example (count 20, no
# array), the exact mirror of the gha#531 case that motivated the
# array-length fallback above. Say "names unavailable" there rather than
# printing an empty list, which would read as "nothing was denied" and is the
# same fail-open shape this script's null-coalescing comments guard against.
denied_summary=""
denied_sample=""
if [[ "$denials_known" == "true" && "$denials" != "0" ]]; then
  # ONE jq pass emitting two lines: the summary, then the sample. They share
  # the grouping and the ordering, so computing them separately meant two
  # traversals of the same array and two copies of `group_by | sort_by` that
  # could drift into disagreeing about which tool leads -- the same DRY
  # reasoning this repo applies to composite actions, at expression scale
  # (gha#544 review).
  #
  # Line-oriented rather than @tsv because @tsv escapes a literal tab into a
  # visible `\t`; both fields are already newline-free (see below), so a line
  # split is unambiguous.
  denied_lines="$(jq -r '
    [ .permission_denials[]?
      # Newlines are stripped from both fields because each reaches a
      # single-line `::warning::` annotation below, which an embedded newline
      # would truncate (the same reason `api_error_message` is flattened), and
      # because the two output lines are split on newlines here.
      | { tool: ((.tool_name? // "unknown") | tostring | gsub("[\n\r]"; " ")),
          # One field per tool shape, most specific first: a Bash denial is its
          # command, a Task denial its description. Falling all the way back to
          # the tool name just restates the summary, so it is the last resort.
          #
          # Every lookup is `?`-suppressed, and that is load-bearing rather
          # than defensive habit: a denial entry whose `tool_input` is a string
          # rather than an object makes a bare `.tool_input.command` raise
          # "Cannot index string with string", which under `set -e` aborts the
          # WHOLE script at exit 5 -- before it classifies the review at all,
          # so the check goes red with a jq error in place of whatever verdict
          # the review actually reached. A diagnostic must not be able to take
          # down the thing it is diagnosing -- the same failure shape as the
          # oversized-body E2BIG in detect-review-request, which reddened a
          # calling job over an optional nicety. Confirmed by reproduction,
          # and pinned by permission-denials-malformed-entries.json.
          #
          # Actions masks configured `secrets.*` values in a run log, but not a
          # credential the agent happened to construct itself, so token-shaped
          # literals are redacted before they are printed. Truncation bounds
          # the rest: a denied command can be arbitrarily long, and this is a
          # diagnostic hint rather than a transcript.
          arg: ( ( .tool_input?.command? // .tool_input?.file_path? // .tool_input?.url?
                   // .tool_input?.pattern? // .tool_input?.description?
                   // (.tool_name? // "unknown") )
                 | tostring
                 | gsub("[\n\r]"; " ")
                 | gsub("gh[pousr]_[A-Za-z0-9_]{16,}"; "***")
                 | gsub("github_pat_[A-Za-z0-9_]{16,}"; "***")
                 | if (. | length) > 120 then (.[0:117] + "...") else . end ) }
    ]
    | group_by(.tool)
    | map({tool: .[0].tool, n: length, arg: .[0].arg})
    # Commonest first, then alphabetically, so the ordering is stable across
    # runs rather than dependent on transcript order.
    | sort_by(-.n, .tool)
    | if length == 0 then ["", ""]
      else [ ( map("\(.tool)x\(.n)") | join(" ") ),
             # A bare tool name answers nothing when every denial is `Bash`
             # (12x Bash was exactly the wai#83 case), so carry one argument
             # string per tool as well.
             #
             # One sample per tool group, ordered like the summary and capped
             # at the leading THREE groups, rather than the first three
             # distinct arguments overall: a globally-unique list is ordered
             # by the argument text, so a tool whose arguments happen to sort
             # late drops out of the sample entirely even when it is the
             # commonest denial. The first draft did exactly that -- six
             # `Task` denials were summarized and then absent from their own
             # sample. The summary above stays complete; only the sample is
             # capped, so a fourth tool is still counted, just not quoted.
             ( .[0:3] | map("\(.tool): \(.arg)") | join("; ") ) ]
      end
    | .[]
  ' <<< "$result")"
  denied_summary="$(sed -n 1p <<< "$denied_lines")"
  denied_sample="$(sed -n 2p <<< "$denied_lines")"
fi
# One note, computed once, so the log line below and the over-threshold
# annotation further down cannot describe the same run differently.
#
# The unknown case gets its OWN wording rather than borrowing the
# no-array wording. They are different facts: "the count is positive and the
# names are missing" is a statement about a run that had denials, whereas
# an unparseable count says nothing about whether any occurred. Reporting
# the second as the first asserted denials on a CLEAN PASS -- observed on
# is-error-success-with-verdict.json, whose `permission_denials_count` is
# JSON null (gha#544 review).
denied_note=""
if [[ "$denials_known" != "true" ]]; then
  # Deliberately silent at this call site: the sentinel `::warning::` above
  # already reports the unparseable count, and repeating it here as a
  # denial-shaped line is what made it read as a finding.
  denied_note="unknown -- the denial count itself could not be parsed (see the warning above)"
elif [[ "$denials" != "0" ]]; then
  if [[ -n "$denied_summary" ]]; then
    denied_note="$denied_summary (sample: ${denied_sample:-none})"
  else
    denied_note="names unavailable -- the execution result carries no permission_denials array (gha#540)"
  fi
  echo "Denied tools: $denied_note"
fi
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
  # gha#520: the account can run OUT of quota part-way through a review, which
  # the zero-cost/turn-1 branch above cannot see -- that one only recognizes a
  # request rejected before any work, and this shape has real turns and real
  # cost behind it (13 turns / $4.10 when first observed). It is still quota
  # exhaustion rather than a defect in the PR under review, so skip gracefully
  # here exactly as that branch does, instead of reddening the check over an
  # account condition the author cannot act on.
  #
  # Key on the structured `api_error_status` field, never on the free-text
  # `result` message: that message is ordinary prose ("You've hit your weekly
  # limit ..."), and matching prose against a transcript is how
  # classify-gemini-failure.sh misclassified genuine failures as graceful skips
  # (gha#380 finding 1).
  #
  # This sits AFTER the gha#391 verdict check on purpose. A run that stated its
  # verdict and only then hit the limit did its job, so it must still pass; only
  # a run that died without one skips.
  api_error_status="$(jq -r '.api_error_status // empty' <<< "$result")"
  if [[ "$api_error_status" == "429" ]]; then
    # Single-line, so the annotation can't be broken up by an embedded newline.
    api_error_message="$(jq -r '(.result // "") | tostring | gsub("[\n\r]"; " ")' <<< "$result")"
    echo "quota_exhausted=true" >> "$GITHUB_OUTPUT"
    echo "::warning::Claude review skipped -- the API returned 429 part-way through the review (quota or rate limit exhausted mid-run; gha#520). Re-trigger the review once the quota resets. API message: ${api_error_message:-<none>}"
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
  echo "permission_denials_count=$denials (stub-retry max_denials=$max_denials)"
  if [[ "$denials" -le "$max_denials" ]]; then
    echo "stub_review=true" >> "$GITHUB_OUTPUT"
    echo "Claude review produced no verdict with low permission_denials_count ($denials <= $max_denials) — marking as a retryable stub review (gha#185)."
  else
    # The names ride along in the annotation itself, not just the log:
    # this is the one line a person triaging a red check reads without
    # opening the job log, and the count alone is what sent two readers to
    # the wrong cause (gha#540). Both strings are newline-free by
    # construction above, so the annotation cannot be split.
    echo "::warning::permission_denials_count=$denials exceeds the stub-retry threshold ($max_denials) — this looks like gha#198's pattern, not gha#185's; not marking as retryable. Denied tools: ${denied_note:-none reported}"
  fi
  echo "::error::Claude review states no verdict (no '### Verdict' heading or 'Verdict:' line anywhere in its output) — looks like an incomplete/stub review, not a finished one (gha#173, Lacaedemon/sparta#590)."
  exit 1
fi
# gha#527: a session-lock claim comment blocks parallel *write* sessions, not
# read-only automated review. A verdict that defers because of "back off" /
# "paws off" / "hold off" language is an incomplete review, not a clean pass.
# Scan only from the verdict marker onward so a substantive review that quotes
# these phrases in its findings does not false-positive (gha#528 review).
verdict_section_file="$(mktemp)"
awk 'BEGIN{found=0} tolower($0) ~ /^[[:space:]>*_#-]*verdict/ {found=1} found' \
  "$review_text_file" > "$verdict_section_file"
if grep -qiE 'deferred.{0,40}hold off|honoring that request and stopping here without conducting|without conducting the review' "$verdict_section_file"; then
  echo "::error::Claude review deferred because of a session-lock claim comment — claim comments block parallel pushes, not automated review (gha#527)."
  exit 1
fi
echo "review_text_file=$review_text_file" >> "$GITHUB_OUTPUT"
echo "Claude review completed cleanly (subtype=$subtype)."
