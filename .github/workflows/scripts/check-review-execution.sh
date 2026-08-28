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
#   - a no-verdict run whose transcript carries an EXECUTED (not denied)
#     background Agent/Task spawn -- a tool_use block whose input's
#     run_in_background is absent or true, with no matching entry in
#     permission_denials -- is classified `background-agent` instead of
#     `stub`, and stub_review is NOT written: gha#392's failure shape ends
#     the turn waiting on completion notifications a headless CI run never
#     delivers, and a same-prompt retry of it has a poor recovery record
#     (gha#536: 8 stub attempts across 3 PRs, 2 recoveries; gha#551).
#   - on every path that exits 1, first writes failure_kind=<kind> to
#     $GITHUB_OUTPUT: `short-circuit`, `hard-error`, `no-output`, `stub`,
#     `high-denial`, `background-agent`, or `deferred`. This script is the
#     thing that KNOWS which
#     one happened, so it says so, rather than leaving claude-code-review.yml
#     to re-derive it from the other outputs -- a second copy of one
#     classification, free to drift out of step with this one, which is the
#     problem detect-review-request.sh records at pattern scale. The kinds are
#     per-ATTEMPT, like stub_review and action_short_circuit beside them; which
#     attempt's kind stands is the caller's decision (gha#543).
#   - whenever the denial count is readable, also writes denied_tools=<note>
#     to $GITHUB_OUTPUT: the same single-line summary gha#544 added to the log
#     ("Taskx6 Bashx3 (sample: ...)"), or one of the two wordings that mean the
#     names could not be recovered. Empty means EITHER zero denials or a
#     short-circuit exit that returned before anything was counted -- see the
#     comment at the write site. claude-code-review.yml's review-failure comment
#     carries it to the PR, so a recurrence of gha#198's signature names its
#     denied tools on the thread rather than only in a downloaded execution
#     artifact (gha#543).
#
# $GITHUB_OUTPUT is optional so this can run standalone in a test harness;
# when unset, output assignments are silently dropped.
set -euo pipefail

EXECUTION_FILE="${1:?usage: check-review-execution.sh <execution-file>}"
GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"

if [[ ! -f "$EXECUTION_FILE" ]]; then
  echo "action_short_circuit=true" >> "$GITHUB_OUTPUT"
  echo "no_execution_file=true" >> "$GITHUB_OUTPUT"
  echo "failure_kind=short-circuit" >> "$GITHUB_OUTPUT"
  echo "::error::Claude review produced no execution output (action short-circuit / setup failure; gha#368) — treating as a failed review."
  exit 1
fi
# Handles NDJSON stream or a single JSON array; grabs the last result object.
result="$(jq -s 'flatten | map(select(.type=="result")) | last // empty' "$EXECUTION_FILE")"
if [[ -z "$result" || "$result" == "null" ]]; then
  echo "action_short_circuit=true" >> "$GITHUB_OUTPUT"
  echo "no_result=true" >> "$GITHUB_OUTPUT"
  echo "failure_kind=short-circuit" >> "$GITHUB_OUTPUT"
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
if [[ "$subtype" == error_* ]]; then
  # total_cost_usd==0 with num_turns==1 and an error_* subtype means the API
  # rejected the request before any real processing --- quota exhaustion, auth
  # failure, or an immediate network error. Skip gracefully. This has to
  # run before any content extraction below.
  #
  # If subtype is "success" (or not error_*), an is_error:true result with zero
  # cost at turn 1 is an execution/runtime failure rather than an API quota
  # rejection (gha#561). Do NOT treat that as quota exhaustion; let it fall
  # through to the error/verdict checks below and fail as a hard-error.
  total_cost="$(jq -r '.total_cost_usd // 1' <<< "$result")"
  num_turns="$(jq -r '.num_turns // 0' <<< "$result")"
  if [[ "$total_cost" == "0" && "$num_turns" == "1" ]]; then
    echo "quota_exhausted=true" >> "$GITHUB_OUTPUT"
    echo "::warning::Claude review skipped -- CLAUDE_CODE_OAUTH_TOKEN quota or auth error (zero cost, turn 1). Re-trigger the review once the quota resets."
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
# gha#550 review finding 1: the stub-retry gate far below treats every denial
# as evidence the reviewer was STARVED of tools it needed -- its own comment
# says gha#198's pattern "has repeatedly NOT recovered", which is why crossing
# the threshold withholds the retry. A denial produced by a rule this repo
# added ON PURPOSE is not evidence for that. `Agent(run_in_background:true)`
# and its `Task` alias are denied deliberately (gha#532), so a run that fans
# out and is correctly stopped generates denials by design.
#
# That interaction is not hypothetical at the sizes actually observed: the
# incidents motivating the deny rules were a 4-spawn (ai-config#1744) and an
# 8-spawn (ai-config#986) fan-out, and the second alone exceeds the default
# threshold of 5 before any genuinely-starved call is counted. It would flip a
# retryable gha#185 stub into a hard-failed gha#198 classification -- losing
# the retry in precisely the scenario the deny rules exist to serve.
#
# So the GATE reads a count with the intended denials removed, while every
# REPORTING path keeps the true total: a PR comment saying the reviewer was
# denied nothing when it was denied eight times would be a lie, and the
# denied-tools summary is what a triager acts on.
#
# The subtraction needs the array, since that is what names tools. When only
# the scalar count is present (the gha#531 shape) no subtraction is possible,
# and the gate falls back to the raw count -- classifying such a run exactly as
# it is classified today. That direction is deliberate: assuming some unnamed
# denials were ours would weaken the gha#198 gate on evidence we do not have.
intended_denials=0
if [[ "$denials_known" == "true" ]]; then
  # Every lookup `?`-suppressed for the same reason the summary block below
  # gives: a denial entry whose `tool_input` is a string rather than an object
  # must not abort the script under `set -e` and take down the classification
  # it exists to refine. Pinned by permission-denials-malformed-entries.json.
  intended_denials="$(jq -r '
    [ .permission_denials[]?
      | select(((.tool_name? // "") | tostring) == "Agent"
               or ((.tool_name? // "") | tostring) == "Task")
      | select((.tool_input?.run_in_background?) == true)
    ] | length
  ' <<< "$result" 2>/dev/null || echo 0)"
  [[ "$intended_denials" =~ ^[0-9]+$ ]] || intended_denials=0
fi
starvation_denials="$denials"
if (( intended_denials > 0 )) && (( denials >= intended_denials )); then
  starvation_denials=$(( denials - intended_denials ))
  echo "Excluding $intended_denials deliberate background-spawn denial(s) from the stub-retry gate (gha#550); starvation-relevant count is $starvation_denials of $denials."
fi
# gha#551: a no-verdict run whose transcript shows an EXECUTED background
# Agent/Task spawn is gha#392's failure shape -- the turn ended waiting on
# completion notifications a headless CI run never delivers -- and gha#536's
# tally (8 stub attempts across 3 PRs, 2 recoveries) makes a same-prompt
# retry of it a poor bet. The no-verdict branch below classifies it as its
# own non-retryable failure_kind rather than a retryable gha#185 stub.
#
# Detection keys on the structured tool_use field, never on the final
# message's prose (classify-gemini-failure.sh's rule, gha#380 finding 1).
# Confirmed against the real run-32347489886 execution artifact
# (Morrison-Lab/ai-config#1744): backgrounded spawns appear as
# assistant-event tool_use blocks carrying run_in_background true,
# synchronous ones carry false, and the parameter can also be omitted (the
# tool's default is true, and an omitted parameter is exactly what the
# gha#550 deny rule cannot match) -- so both scans test
# run_in_background != false rather than == true.
#
# The subtraction mirrors gha#550's with the opposite sign: a spawn that was
# DENIED never backgrounded anything, so only spawns with no matching denial
# count as executed. Both scans require an object-typed input and are
# ?-suppressed, so a malformed entry neither aborts the script (the
# permission-denials-malformed-entries.json lesson) nor counts as evidence
# -- an unreadable spawn errs toward keeping the retry, the same direction
# gha#550 chose for unnamed denials. A jq // default is avoided on the
# run_in_background reads because // treats JSON false as empty (the
# gha#511 lesson); the direct == false comparison handles absent (null),
# true, and false correctly.
bg_spawn_uses="$(jq -s '
  [ flatten | .[]?
    | select(type == "object" and .type == "assistant")
    | .message.content? // [] | .[]?
    | select(type == "object" and .type == "tool_use")
    | select(((.name? // "") | tostring) == "Agent"
             or ((.name? // "") | tostring) == "Task")
    | select((.input? | type) == "object")
    | select((.input.run_in_background? == false) | not)
  ] | length
' "$EXECUTION_FILE" 2>/dev/null || echo 0)"
[[ "$bg_spawn_uses" =~ ^[0-9]+$ ]] || bg_spawn_uses=0
bg_spawn_denials="$(jq -r '
  [ .permission_denials[]?
    | select(((.tool_name? // "") | tostring) == "Agent"
             or ((.tool_name? // "") | tostring) == "Task")
    | select((.tool_input? | type) == "object")
    | select((.tool_input.run_in_background? == false) | not)
  ] | length
' <<< "$result" 2>/dev/null || echo 0)"
[[ "$bg_spawn_denials" =~ ^[0-9]+$ ]] || bg_spawn_denials=0
executed_bg_spawns=$(( bg_spawn_uses > bg_spawn_denials ? bg_spawn_uses - bg_spawn_denials : 0 ))
if (( executed_bg_spawns > 0 )); then
  echo "executed_background_spawns=$executed_bg_spawns (tool_use with run_in_background != false: $bg_spawn_uses; denied: $bg_spawn_denials)"
fi
# The threshold is emitted rather than left for a caller to restate. It is
# overridable via STUB_RETRY_MAX_DENIALS, so a caller hard-coding "5" to quote
# it in a report would be right only while nobody overrides it -- the
# two-declarations-of-one-default problem gha#303 pinned a test against. Here
# the fix is cheaper than a test: emit the value, and there is only one.
echo "max_denials=$max_denials" >> "$GITHUB_OUTPUT"
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
                 # Userinfo credentials first, because they are the one shape
                 # reachable through the `.tool_input?.url?` fallback above
                 # rather than through a command string, and nothing
                 # downstream redacts -- the composer only fences and
                 # truncates. `[^/@[:space:]]+` cannot cross a path separator,
                 # so an ordinary URL carrying an `@` later in its path (a
                 # `...@v2` action ref, a raw.githubusercontent path) is left
                 # alone; verified against both directions rather than assumed.
                 | gsub("://[^/@[:space:]]+@"; "://***@")
                 | gsub("gh[pousr]_[A-Za-z0-9_]{16,}"; "***")
                 | gsub("github_pat_[A-Za-z0-9_]{16,}"; "***")
                 # The two patterns above were scoped for this string reaching
                 # a run LOG, where Actions masking is a backstop. gha#543
                 # changed the destination: it is now also posted to a PR
                 # comment, which is not masked at all. So the shapes this very
                 # job holds have to be covered too -- it carries
                 # CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY, and a reviewer
                 # attempting `curl -H "Authorization: Bearer sk-ant-..."` would
                 # otherwise publish one verbatim (gha#548 review, finding 6).
                 | gsub("sk-ant-[A-Za-z0-9_-]{16,}"; "***")
                 # A generic backstop for a credential shape not enumerated
                 # above, keyed on the header rather than on any vendor prefix.
                 # Deliberately narrow -- an Authorization value specifically,
                 # not any long token-ish string -- because over-redacting the
                 # denied command destroys the diagnostic this line exists to
                 # carry. Erring toward publishing a redaction marker is
                 # cheap; erring toward publishing a live credential is not.
                 #
                 # The "i" flag is load-bearing, not tidiness. HTTP header
                 # names and auth schemes are both case-insensitive (RFC 9110
                 # / 7235), and the first draft wrote `[Aa]uthorization` with a
                 # case-SENSITIVE `(Bearer|Basic)` -- which tolerated exactly
                 # one letter of variation and leaked on `authorization:
                 # bearer` and on `AUTHORIZATION:`. Measured, both before and
                 # after (gha#548 review, round 2).
                 #
                 # `token` is in the alternation because it is the standard
                 # GitHub PAT header form. The `gh[pousr]_` pattern above
                 # already covers a modern PAT wherever it appears, so what
                 # this adds is the LEGACY 40-hex PAT, which carries no prefix
                 # for any vendor pattern to key on.
                 | gsub("(?<h>authorization: *(bearer|basic|token) +)[A-Za-z0-9._~+/=-]{16,}"; "\(.h)***"; "i")
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
# The same note, handed to the CALLER rather than only to the log. gha#544 put
# the tool names in the job log and in the over-threshold `::warning::`; both
# are places you have to open the run to reach. gha#543 is the case where that
# is not enough: a no-verdict review posts nothing to the PR at all, so from
# the thread there is no way to tell a reviewer that failed from one that has
# not run yet. claude-code-review.yml's review-failure comment carries this
# string, which is what makes the next recurrence answerable from the PR page
# instead of from a downloaded execution artifact.
#
# Written unconditionally once the result has been parsed, which puts it before
# every exit that reports on a review -- including the two that matter most
# here, the no-verdict branch and the hard-error branch.
#
# NOT before every exit in the file, and the difference is worth stating rather
# than rounding off. The two short-circuit exits at the top (no execution file,
# no result object) return before the denial count exists at all, so they leave
# this unset. That is correct: nothing about the run was parsed, so there is no
# denial data to report -- but it does mean an empty value carries TWO
# readings, "zero denials" and "never counted", where the "unknown" / "names
# unavailable" wordings above carry a third, "denials occurred and could not be
# named". A caller separates the first two by reading `denials`, which is `0`
# in one and absent in the other; compose-review-failure-report.sh does exactly
# that. (An earlier version of this comment claimed every exit path carries it,
# which was false for those two -- gha#548 review, finding 8.)
#
# Single-line by construction: every branch feeding $denied_note either is a
# literal above or comes out of the jq program, which gsubs newlines out of
# both fields for exactly this reason. A multi-line value here would corrupt
# $GITHUB_OUTPUT rather than merely look wrong.
echo "denied_tools=$denied_note" >> "$GITHUB_OUTPUT"
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
  echo "failure_kind=hard-error" >> "$GITHUB_OUTPUT"
  echo "::error::Claude review ended in an error state (is_error=$is_error, subtype=$subtype)."
  jq '.' <<< "$result" || true
  exit 1
fi
if [[ -z "$(tr -d '[:space:]' < "$all_text_file")" ]]; then
  echo "failure_kind=no-output" >> "$GITHUB_OUTPUT"
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
  echo "permission_denials_count=$denials (stub-retry max_denials=$max_denials, starvation-relevant=$starvation_denials)"
  # gha#551: the executed-background-spawn test runs FIRST, because it names
  # the mechanism that ended the run (the turn parked behind spawns that will
  # never notify) rather than a count correlated with it -- and because the
  # low-denial arm below would otherwise mark this shape retryable, which is
  # the misclassification the kind exists to remove. stub_review is
  # deliberately NOT written, so claude-code-review.yml's retry gate
  # (keyed on stub_review == 'true') never fires for it.
  if (( executed_bg_spawns > 0 )); then
    echo "failure_kind=background-agent" >> "$GITHUB_OUTPUT"
    echo "::warning::Claude review produced no verdict after $executed_bg_spawns executed background Agent/Task spawn(s) (run_in_background absent or true, no matching denial) -- the turn ended waiting on completion notifications a headless CI run never delivers (gha#392). Not marking as retryable: a same-prompt retry of a run that ignored the synchronous-only instruction has a poor recovery record (gha#536: 8 stub attempts, 2 recoveries; gha#551)."
  elif [[ "$starvation_denials" -le "$max_denials" ]]; then
    echo "stub_review=true" >> "$GITHUB_OUTPUT"
    echo "failure_kind=stub" >> "$GITHUB_OUTPUT"
    echo "Claude review produced no verdict with low permission_denials_count ($starvation_denials <= $max_denials, excluding $intended_denials deliberate spawn denial(s)) — marking as a retryable stub review (gha#185)."
  else
    echo "failure_kind=high-denial" >> "$GITHUB_OUTPUT"
    # The names ride along in the annotation itself, not just the log:
    # this is the one line a person triaging a red check reads without
    # opening the job log, and the count alone is what sent two readers to
    # the wrong cause (gha#540). Both strings are newline-free by
    # construction above, so the annotation cannot be split.
    # The starvation-relevant count is what the gate compared, so it is what
    # the annotation must quote -- naming only the raw total would send a
    # triager looking for eight starved calls when three crossed the line.
    # Both are printed when they differ, since the total is what the denied
    # tools list below is counted from.
    denial_figure="$starvation_denials"
    if (( intended_denials > 0 )); then
      denial_figure="$starvation_denials of $denials, after excluding $intended_denials deliberate background-spawn denial(s)"
    fi
    echo "::warning::permission_denials_count=$denial_figure exceeds the stub-retry threshold ($max_denials) — this looks like gha#198's pattern, not gha#185's; not marking as retryable. Denied tools: ${denied_note:-none reported}"
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
  echo "failure_kind=deferred" >> "$GITHUB_OUTPUT"
  echo "::error::Claude review deferred because of a session-lock claim comment — claim comments block parallel pushes, not automated review (gha#527)."
  exit 1
fi
echo "review_text_file=$review_text_file" >> "$GITHUB_OUTPUT"
echo "Claude review completed cleanly (subtype=$subtype)."
