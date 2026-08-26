# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Memory storage policy

- Persist standing notes and memories only in repo-tracked files
  (via commits/PRs); do not save them to non-repo local paths.

## Standing merge policy (`mwc`)

- **Standing `mwc` is active by default in `Morrison-Lab/gha`**: AI agent
  sessions working in this repository have standing permission to squash-merge
  pull requests once they reach **fully clean** (all CI checks green and zero
  outstanding review findings), unless explicitly instructed otherwise for a
  specific PR or session.

## About this repo

Central, reusable GitHub Actions for `d-morrison` / `UCD-SERG` / `ucdavis` R-package
and Quarto repositories (see [`README.md`](README.md)). Each capability ships as a
composite action plus a `workflow_call` reusable workflow. Consumers pin the
major tag each capability's own reference page documents (`@v1` for most,
`@v2` for `preview`, `preview-deploy`, `cleanup-pr-previews`, `quarto-publish`,
`test-coverage`, `check-equation-renders`, `check-bibliography-dois`,
`check-phi`, `check-junk-files`, `check-links`,
`check-non-standard-chars`, `claude`,
`claude-code-review`, `update-snapshots`, `lint-yaml`, `lint-markdown`,
`lint-qmd`, `lint-changed-lines`, `check-new-line-breaks`, `check-secrets`,
`request-dependabot-review`, `sync-upstream`, `check-news`,
`altdoc-multiversion-docs`, `report-failure`, `gemini`,
`gemini-code-review`, `antigravity-code-review`, `cursor-code-review`, `ai-code-review`, `opencode-code-review`, `bump-dev-version`, `version-check`,
`small-model-agent`, `check-ai-tells`, `lint-workflows`, and `spellcheck` -- see
the Versioning section
of `README.md`).
`@v1` was frozen at the pre-`2.0.0` snapshot and has picked up no fixes since,
which is why the capabilities above moved to `@v2`.

### Layout

- Per-capability composite-action directories at the repo root, each with an
  `action.yml` and, for R/Python capabilities, a language-specific helper
  script -- e.g. `check-bibliography-dois/` (R), `check-non-standard-chars/`,
  `check-phi/`, and `check-new-line-breaks/` (Python; the last mirrors
  `check-phi`'s diff-scoped-by-`base-ref` pattern, but skips the check
  entirely rather than falling back to a whole-tree scan when the diff can't
  be computed, since a whole-tree scan here would reflag a corpus's
  pre-existing long-line drift, which is exactly what the diff-scoping
  exists to avoid).
  `check-junk-files/` (shell) is a third scoping: it scans neither the diff nor
  the history but the **index** (`git ls-files -i -c -X`), for tracked
  operating-system and editor detritus.
  Diff-scoping is wrong here for the
  opposite reason it is right for `check-new-line-breaks`: a `.DS_Store`
  committed long ago is still a live defect rather than pre-existing drift to
  tolerate, and clearing it costs one command.
  It passes no
  `--exclude-standard`, so a file the caller force-added despite its own
  `.gitignore` is not second-guessed, and its `paths-ignore` becomes git
  **pathspec** exclusions rather than gitignore `!` lines -- negation is
  matched per pattern against the full path, so `!vendor/` re-includes
  `vendor/.DS_Store` not at all and would exempt nothing silently (verified
  against git 2.50.1, both directions).
  Its `patterns` default is deliberately
  the set `usethis::git_vaccinate()` writes (read from `r-lib/usethis`'s own
  `git_ignore_lines`, not from the rendered reference page), plus `._*`,
  `Thumbs.db`, and `desktop.ini`, which vaccination does not cover -- so the
  remedy the failure recommends is never narrower than the check's own scope,
  and the gap is stated rather than left silent.
  `check-secrets/` (shell) is the deliberate counter-example to that pattern:
  it is the one check that scans **history** rather than a diff,
  because a secret committed and later removed stays fetchable through the
  API,
  so diff-scoping would miss the case the capability exists for.
  It refuses a shallow clone rather than reporting a partial scan clean,
  and it wraps the MIT gitleaks CLI rather than
  `gitleaks/gitleaks-action`,
  which is proprietary and needs a paid licence for organization accounts.
  `check-links/` bundles `lychee.default.toml`;
  `preview/`, `quarto-publish/`, `open-sync-pr/`, and `resolve-pr-info/` are action-only (the last
  two are shared internal helpers: `open-sync-pr` for push-and-open-PR used by `bump-submodule`,
  `sync-shared-fragments`, and `sync-upstream`; `resolve-pr-info` for PR branch/head-repo/fork lookup used by `ai-code-review`, `gemini`, and `dispatch-review`).
- `.github/workflows/` -- the `workflow_call` reusable workflows that wrap the
  composites (one per consumer-facing capability -- the shared internal
  `open-sync-pr` composite has no wrapper), plus the `claude.yml` and
  `claude-code-review.yml` reusable wrappers, and `_selftest.yml`, which
  exercises composites on every PR -- local `./` refs for pre-release
  capabilities, and `@v1` through the reusable-workflow wrappers for stable ones.
  `claude-bot.yml` and `claude-review.yml` are event-triggered workflows that run
  the Claude bot in this repo, not `workflow_call` wrappers.
- Several workflows have no corresponding root composite: `check-news.yml`,
  `summary.yml`, and `preview-deploy.yml` are `workflow_call` reusable workflows
  that wrap external actions; `cleanup-pr-previews.yml` is a self-contained
  `workflow_call` reusable workflow (inline shell logic, no external
  composite); `altdoc-multiversion-docs.yml` is also self-contained but pairs
  inline shell logic with the three internal composites below --
  `generate-altdoc-version-dropdown`, `generate-altdoc-landing-page`, and
  `resolve-altdoc-base-url` -- no
  top-level render/deploy composite of their own (the render+deploy sequence
  is inherently stateful/ordered, so splitting it into a separate composite
  the way `quarto-publish`/`preview` do would add indirection without reuse
  value, per the one-genuine-consumer-pattern reasoning in
  `shared/principles/README.md`'s "How the principles relate" section of
  `Morrison-Lab/ai-config`);
  `bump-submodule.yml`, `sync-shared-fragments.yml`, and `sync-upstream.yml`
  are `workflow_call` reusable workflows that call the shared internal
  `open-sync-pr` composite (`sync-upstream` merges an upstream repo's branch
  into a fork via `git merge --squash` -- which stays out of a `MERGE_HEAD`
  state so `open-sync-pr`'s `git switch -C` works -- then lets `open-sync-pr`
  commit the merge and open the PR);
  `request-dependabot-review.yml` similarly calls the internal
  `build-reviewer-args` composite (see below) for its reviewer-list
  split/trim logic; `slide-major-tag.yml` is dispatch-triggered and runs
  only in this repo.
- `.github/actions/checkout-submodules/` -- a small shared composite reused by the
  reusable workflows.
- `.github/actions/parse-workflow-ref/` -- a small composite action that parses a
  `github.workflow_ref`/`github.job_workflow_ref`-shaped string
  (`owner/repo/.github/workflows/<file>@ref`) into its `repo`/`path`/`ref` parts,
  shared by every `claude-code-review.yml` and `claude-review.yml` step that
  needs to pick one of these strings apart instead of duplicating the `sed`
  logic inline. It has to be a composite action rather than a plain checked-out
  script (like `check-review-execution.sh` below) because some call sites run
  before any checkout has happened -- a composite action's own files are
  available via `uses:` regardless of checkout state, which a bare script path
  is not.
- `.github/actions/run-review-guard/` -- a thin composite-action wrapper around
  `check-review-execution.sh` (below), invoked from `claude-code-review.yml`'s
  "Fail the check if the review did not complete (attempt 1)" step (and again
  from its retry counterpart -- see `run-claude-review-attempt` below). #191
  tried to locate that script by resolving Morrison-Lab/gha's own repo/ref from
  `github.job_workflow_ref` and checking it out into a side directory, but
  that context var came back empty at runtime on real consumer runs even
  though the calling step passed it correctly (gha#196) -- the #191 fix was
  only unit-tested via the sed-parsing logic in isolation, never exercised
  end-to-end. `github.action_path` doesn't have that failure mode: a composite
  action's own files are always reachable through it regardless of how the
  calling reusable workflow was invoked, the same reasoning `parse-workflow-ref`
  itself relies on.
- `.github/actions/run-claude-review-attempt/` -- wraps the single
  `anthropics/claude-code-action` call `claude-code-review.yml` uses to review
  a PR (allowedTools/disallowedTools, the review prompt). Extracted into a
  composite action so `claude-code-review.yml` can invoke it a second time,
  unchanged, as a same-prompt retry when the first attempt completes without
  an SDK error but never states a verdict -- the "stub review" signature
  (gha#185): `check-review-execution.sh` surfaces this specific case via a
  `stub_review` output (through `run-review-guard`), and the workflow retries
  once before failing the check for real. Keeping the `claude-code-action`
  call itself in one place (rather than duplicating its ~100-line `with:`
  block between two near-identical steps) follows this file's own DRY
  guidance below. `claude-code-review.yml`'s "Resolve final review outcome"
  step is the single point that decides which attempt's output to use and the
  only step that actually fails the job when neither attempt produces a
  usable review -- both "Fail the check" steps are `continue-on-error: true`
  so a recovered retry doesn't leave the job red.
- `.github/actions/upload-review-execution/` -- resolves claude-code-action's
  `execution_file` output (with its temp-path fallback) and uploads it as a
  workflow artifact, in one composite action shared between attempt 1 and the
  `run-claude-review-attempt` retry above -- the same DRY rationale that
  motivated extracting that (much larger) composite action, just at a
  smaller scale (gha#201 review).
- `.github/actions/extract-total-cost/` -- wraps
  `scripts/extract-total-cost.sh`, which extracts `total_cost_usd` from a
  claude-code-action execution-output file's last `result` event. `claude.yml`
  calls it once, right after "Run Claude Code", and both its
  comment-posting steps ("Post Claude's response if no code was committed"
  and "Finalize PR for issue trigger") read the shared
  `steps.cost.outputs.cost` -- a single extraction instead of duplicating the
  jq filter at both call sites (gha#219 review finding 1).
- `.github/actions/sum-costs/` -- wraps `scripts/sum-costs.sh`, which sums two
  (each optionally empty) `total_cost_usd` values. `claude-code-review.yml`'s
  "Sum attempt costs" step calls it once, combining the initial attempt's
  cost with the gha#185 stub-retry attempt's cost when one ran, so the
  arithmetic has offline test coverage instead of being an inline `awk`
  one-liner only exercised by a live two-attempt review run (gha#219 review
  finding 5).
- `.github/actions/detect-review-request/` -- wraps
  `scripts/detect-review-request.sh`, which decides whether a comment/review
  body is an explicit `@claude review` request.
  `claude.yml` calls it twice: once on the trigger comment, and once (via its
  `bodies-file` input) on every comment posted after the trigger, for the
  late-arrival rescan.
  Those two paths previously each carried their own copy of the pattern -- one a bash
  regex, one a `jq` `test()` -- which is how they drifted apart, and how a
  consumer ended up adding a local dispatch job that double-dispatched every
  plain `@claude review`
  ([UCD-SERG/serodynamics#277](https://github.com/UCD-SERG/serodynamics/issues/277)).
  Two things to know before widening the pattern: a **false positive is the
  expensive error**, because `match == 'true'` suppresses `claude.yml`'s "Post
  Claude's response if no code was committed" step, so a misfire swallows the
  answer to a question the user actually asked -- which is why the lead-ins
  between `@claude` and `review` are a closed set of function words
  (`please`, `can/could/would/will you`, `kindly`, `pls`/`plz`) rather than "any few
  words".
  **Both sides of `review` need that closed set, not just the lead-in.**
  gha#341 constrained only what may precede the keyword, which left
  `@claude can you review this and fix the failing test?` matching: the object
  of `review` names a topic to examine, so the comment is a question for the
  agent, and dispatching it suppressed the answer.
  So a second closed set governs what may follow -- deictic references to the
  PR under discussion (`this`, `the latest changes`, `again`) and trailing
  politeness -- and the request must then end its line (gha#346).
  That is also what keeps `review` a whole word, so the older
  `[^[:alnum:]]|$` guard against `@claude reviewer` is gone rather than
  duplicated.
  The trade is that a pure review request with an unlisted object
  (`@claude review the changes I just pushed`) now self-reviews instead of
  dispatching, which is the cheap error by the same asymmetry.
  Both known cases are pinned in the test table, so widening `TAIL_WORD` to
  recover them stays a deliberate decision.
  A third portability note sits alongside the jq one below: the script
  normalizes CRLF with `tr -d '\r'` because GitHub delivers comment bodies
  with CRLF and the pattern anchors on a bare newline.
  The `sed 's/\r$//'` it replaced only worked under GNU sed -- BSD/macOS sed
  reads `\r` as a literal `r` -- and the composite probes `base64 -d` vs `-D`
  for the same reason.
  And `bodies-file` takes **base64-encoded lines**, not raw or
  NUL-separated ones: comment bodies are multi-line, and `jq --raw-output0`
  needs jq 1.7 while `runs-on` is a consumer-settable input, so a runner with
  jq 1.6 would have failed into the `|| :` fallback and silently reported "no
  late review".
  The composite decodes those lines into a **pipe**, NUL-separated, and the
  script reads stdin -- never argv.
  Linux caps a single argument at `MAX_ARG_STRLEN` (131072 bytes)
  independently of the far larger aggregate `ARG_MAX`, while GitHub allows
  65536-*character* comments, which in mostly-4-byte UTF-8 is 256 KiB.
  So one emoji-heavy comment from any non-bot commenter fails `execve` with
  E2BIG, and under the composite's `set -euo pipefail` that reddens the whole
  calling job over an optional late-dispatch nicety (caught in gha#341's
  review; the test table's oversized-body case is the regression guard).
  Finally, the script does not match the raw body: it pipes each one through
  `scripts/strip-non-invoking-markup.sh` first, which removes blockquote
  lines, fenced code blocks, indented code blocks, and inline code spans.
  All four are standard Markdown for "this is a literal string, not
  something I mean", and treating them as text meant a comment *documenting*
  the accepted phrasings dispatched a review by quoting them (gha#344).
  It tracks CommonMark closely rather than approximately, because the two
  directions of error land on different callers: under-stripping dispatches a
  review off quoted text, while over-stripping drops a genuine request in the
  mention gate that shares the script (gha#342).
  Four things constrain any change to that stripper.
  A code span becomes the placeholder word `elided` rather than being
  deleted, because deleting it lets its neighbours close up into a request
  the author never wrote: a span sitting between the mention and the keyword
  would collapse into a dispatch.
  The placeholder also has to be letters that no caller's pattern accepts,
  which rules out the obvious `[code]` -- `code` is one of the `TAIL_WORD`
  alternatives, so the placeholder itself would have completed a match.
  And a code span is closed by a backtick run of *equal* length, so the scan
  measures runs rather than matching `` `[^`]*` `` -- that pattern matches the
  empty span between the two opening backticks of a ```` ``...`` ```` span
  and leaks the contents through, the same bug the Tests section records for
  `check-new-line-breaks`'s `strip_inline_markup`.
  Third, the span scan runs over the **whole body at once**, not per line,
  because a span may contain a line break -- CommonMark closes it on the next
  run of matching length wherever that appears.
  That is also why indentation limits matter rather than being tidied away:
  a fence is capped at three spaces of indentation at both ends, so trimming
  indentation wholesale before the close test let a 4-space-indented
  delimiter (which is fence *content*) close the block early, and four
  columns after a blank line opens an indented code block in the first place.
  The blank-line precondition on that last one is load-bearing: without it an
  indented list continuation would be stripped, which drops a genuine
  request.
  Fourth, **never write an interval expression (`{m,n}`) into that awk.**
  `mawk` is Debian's and Ubuntu's *default* `awk`, selected through the `awk`
  alternatives link, so any image that has not installed and selected another
  implementation resolves `awk` to it.
  `mawk 1.3.4 20240123` aborts the whole process on an interval ---
  `REcompile() - panic: values still on machine stack` --- rather than
  returning a verdict, so the abort is absorbed into a `false` for every
  input and a genuine review request is silently never dispatched.
  This defect was fixed in gha#457 (formerly tracked by gha#448 and gha#451):
  `strip-non-invoking-markup.sh` previously read
  `if (bare ~ /^#{1,6}([ \t]|$)/) return 1`.
  Always express the CommonMark 1-6 heading limit as `^#+([ \t]|$)` plus a length
  check (or `^##?#?#?#?#?([ \t]|$)`) rather than using interval quantifiers like `{1,6}`.
  Two things make this regression risk easy to miss.
  `_selftest.yml` is green on `main` throughout, so whatever awk the
  `ubuntu-latest` runner provides does not hit the panic --- which is not a
  claim about *which* awk that is, since `actions/runner-images`'
  `Ubuntu2404-Readme.md` names neither `mawk` nor `gawk`, and a container's
  own `readlink -f /usr/bin/awk` reports only that container.
  The guarantee stops at that runner either way: `runs-on` is a
  consumer-settable input, so a consumer whose runner resolves `awk` to
  `mawk` would get the abort if interval quantifiers were reintroduced,
  which is the same portability class as the three notes above.
  And bracketing the braces (the fix for a *literal* `{}` that mawk misreads
  as an interval) does not help here: the interval is the thing being asked for,
  so express the limit as a length check or unrolled quantifiers instead.
  Also, `detect-review-request.sh` previously swallowed stripper failures inside
  `if` condition evaluations (gha#451); body normalization now evaluates
  `strip-non-invoking-markup.sh` outside `if` constructs so script failures propagate
  under `set -e`, and `claude.yml` step `Detect @claude review request` carries
  `continue-on-error: true` so workflow runs tolerate stripper/engine failures safely.
  It lives in its own script rather than inline because the same constructs
  gate whether the agent runs at all (gha#342).
- `.github/actions/detect-bot-mention/` -- wraps
  `scripts/detect-bot-mention.sh`, which decides whether a body carries an
  `@claude` mention that is actually addressed to the bot rather than quoted
  while writing about it.
  `claude.yml` calls it from a cheap `mention-filter` job, for all four
  reactive events, and gates the expensive agent job on that job's
  `proceed` output (gha#554).
  It shares `strip-non-invoking-markup.sh` with `detect-review-request`
  (gha#342).
  **Its bias is the opposite of that script's, and the two must not be
  harmonized on this point.**
  There a false positive suppresses the agent's reply to a real question, so
  the matcher is deliberately narrow; here a false negative means a genuine
  request is silently ignored, so the gate answers "run" whenever *any*
  mention survives stripping, and treats an empty result (the step did not
  run, or failed) as "run" too.
  That is also why the matching stays plain-substring and case-insensitive,
  mirroring the `contains()` call it backs: a word-boundary rule would buy
  very little and risk exactly the false negative this bias rules out.
  The caller-side job `if:` and `mention-filter`'s own `if:` still test the
  raw body, because a GitHub expression cannot strip Markdown, so a quoted
  mention still starts the filter job.
  What it no longer starts is the agent job: no caller checkout, no billed
  agent run, no review re-dispatch.
  An allowlisted `issues.assigned` event is exempt from the mention check
  (gha#552) and still proceeds with no mention anywhere in the issue.
- `.github/actions/report-push-failure/` -- wraps
  `scripts/classify-push-failure.sh`, which reads a failed `git push`'s output
  and names the failure kind (`workflows-permission`, `push-protection`,
  `non-fast-forward`, `other`, plus `no-push-attempt` which the composite
  assigns when no log exists) plus advice for it.
  The composite adds what the script deliberately leaves out: it redacts any
  credential git echoed back in the remote URL, emits the `::error::`,
  generates a `git format-patch` of the commits that could not be pushed, and
  comments all of it on the issue or PR.
  `claude.yml` calls it from two steps, one per push site -- "Push PR branch
  if Claude committed" and "Push branch for issue trigger".
  That second one is a step this PR split out of the old combined push-and-
  finalize step, so the push's own outcome can gate the finalize that follows
  it.
  Three things to know before changing it.
  The redaction is not belt-and-braces: Actions masks secrets in a **run log**
  and not in a **comment body**, so without it the push token would be
  published rather than starred out -- which is also why `dry-run` exists, so
  `_selftest.yml` can assert the redaction holds against a real call.
  The classifier keys on the `refusing to allow ... to create or update
  workflow` clause rather than on the trailing scope name, because GitHub
  words that tail differently per credential: a GitHub App is rejected for
  lacking the `workflows` **permission**, a PAT for lacking the `workflow`
  **scope**.
  And the fenced blocks in the comment body measure the longest backtick run
  in their content and open with one more, the same reasoning
  `strip-non-invoking-markup.sh` uses -- a patch that touches a Markdown file
  carries ``` lines of its own, which a fixed three-backtick fence would let
  close the block early.
  Two further behaviours are load-bearing rather than incidental, both found
  by gha#361's review.
  A **missing** push log is reported as the `no-push-attempt` kind rather
  than skipped: the calling step can die before its push (the auto-commit
  sweep, the fork lookup), and since `claude.yml` gates its response-post
  step off on that same failure, standing down here would leave the thread
  with no comment at all -- the exact outcome gha#360 exists to prevent.
  And the patch is truncated by reading a **file**, never a pipe:
  `printf ... | head -c` leaves printf writing to a closed pipe once head has
  its bytes, so any patch past the ~64 KiB pipe buffer raised SIGPIPE, which
  `pipefail` promotes to the pipeline's status and `set -e` turns into an
  aborted report -- losing the comment precisely for the large patches that
  most need preserving.
  Two more, from gha#361's second round.
  A rejection carrying GitHub secret-scanning markers (`GH013` and friends)
  gets its patch **suppressed** rather than posted: those commits carry the
  secret the push was blocked to contain, so rendering them into a public
  comment -- or the run log -- would republish it, and Actions' masking does
  not apply because a scanned secret is commit content rather than a
  configured `secrets.*` value.
  **That suppression is a second output, `withhold-patch`, decided
  independently of `kind` -- do not re-key it on `kind`.**
  `kind` is a first-match chain, so it answers "which explanation does the
  reader get", one rejection and one story.
  Whether the commits may be published is a different question, and tying it
  to `kind` made it answerable only for whichever clause happened to win: a
  push that both edits a workflow file *and* carries a secret matches the
  workflows-permission clause first, so a kind-keyed gate never fired and
  the patch went out with the live credential in it (round 5).
  The markers are therefore tested on their own, before the chain, and the
  composite gates publication on that -- erring toward withholding, since a
  needless withhold costs a re-run while a published credential cannot be
  recalled.
  When the markers fire but another kind wins, the classifier appends the
  no-patch explanation to that kind's advice, so the omission is never
  silent.
  And the byte budget bounds the **whole body**, not just the patch: the log
  gets a fixed slice and the patch takes the remainder, because capping only
  the patch let a verbose rejection carry the total past GitHub's comment
  limit on its own, which 422s the post and drops the report entirely -- the
  silent-thread outcome gha#360 exists to prevent.
- `.github/actions/report-gemini-failure/` -- wraps
  `scripts/classify-gemini-failure.sh`, which reads a failed
  `google-github-actions/run-gemini-cli` call's `error` output and names the
  failure kind (`quota-or-auth` -- rate-limit, auth rejection, or a suspended
  project, all graceful-skip -- or `other`, a genuine failure) plus advice.
  Deliberately simpler than `classify-push-failure.sh`: there is no patch to
  withhold and no credential to redact, since the input is API error text
  rather than a git push log, and the classifier itself does not embed the
  raw error output -- that stays the composite's job. The composite's
  `fence_for()`/`truncate_to_bytes()` helpers live in
  `scripts/fence-and-truncate.sh`, sourced by both this composite and
  `report-push-failure` -- extracted rather than pasted twice, per this
  file's own "factor shared logic into reusable units rather than copying it
  between files" guidance (gha#380 review finding 3).
  `classify-gemini-failure.sh`'s own quota/auth regex only matches
  distinctive markers (`RESOURCE_EXHAUSTED`, `PERMISSION_DENIED`, a `"code"`
  JSON key or `HTTP` status line paired with 401/403/429, etc.), never a bare
  status code or a generic word like `disabled`/`billing` on its own --
  `run-gemini-cli`'s `error` output is raw stderr when stderr isn't valid
  JSON, so an unanchored alternative matches ordinary text in a realistic
  multi-line stack trace (a Node stack trace's own line:column numbers, an
  unrelated MCP log line) and would misclassify a genuine bug as a graceful
  skip -- exactly the failure mode this script's header comment says must
  never happen (gha#380 review finding 1).
  `gemini.yml` and `gemini-code-review.yml` both call it from a step gated on
  `steps.gemini-run.outcome == 'failure'`: a `quota-or-auth` classification
  posts a `> [!WARNING]` comment and stops there, deliberately never
  retried -- retrying a suspended or rate-limited key wastes CI time and can
  look like continued automated abuse to Google, which is the opposite of
  what should happen. An `other` classification still posts (with a
  `> [!CAUTION]` framing) but the calling workflow fails the check for real,
  the same two-tier structure `report-push-failure`'s `kind` decides.
  `gemini-code-review.yml` additionally gates a `require-review` job
  (mirroring `claude-code-review.yml`'s own) on this: it skips gray rather
  than red when the review was a graceful quota/auth skip, or when a
  dispatch-guard block left the underlying `review` job's own result at
  `success` with no review having actually run (`dispatch_guard_blocked`
  output -- unlike `claude-code-review.yml`'s dispatch-guard, which lives in
  a separate job and gates `claude-review`'s job-level `if:` directly,
  `gemini-code-review.yml`'s dispatch-guard is a step inside the same job as
  the review itself, so blocking it only skips downstream steps rather than
  the job as a whole). Consumers gating merges on this workflow should use
  `review / require-review`, not `review / review`, for the same reason
  `claude-code-review.yml`'s own header documents. Its `review` job shares a
  `cancel-in-progress` concurrency group across the automatic `pull_request`
  trigger and `gemini.yml`'s `@gemini review` dispatch, the same race
  CLAUDE.md's "A canceled review skips require-review gracefully" documents for
  `claude-code-review.yml` (gha#585). (Added after the "Default
  Gemini Project" API-key suspension incident, 2026-07-30, gha#379 -- see the
  Tests section below for the offline coverage and the `_selftest.yml`
  end-to-end proof.)

- `.github/actions/report-review-failure/` -- wraps
  `scripts/compose-review-failure-report.sh`, which builds the comment
  `claude-code-review.yml` posts when a review run finishes without a usable
  verdict (gha#543).
  Before it, every posting step in that workflow was gated on
  `steps.resolve-final.outcome == 'success'`, so a no-verdict review skipped
  all four together -- the quota notice, the review comment, the cost comment,
  and the collapse step.
  The run spent real money, reddened `require-review`, and left the PR thread
  silent, which from the thread is indistinguishable from a reviewer that has
  not started yet.
  The same silent-thread class gha#360 fixed for the push path and gha#379 for
  the Gemini path.
  Five things constrain any change to it.
  **The script composes; it does not classify.**
  Its two siblings are handed raw error text and must work out what happened,
  whereas here `check-review-execution.sh` has already decided and
  `Resolve final review outcome` has already picked which attempt's decision
  stands.
  So `failure_kind` is an input, and re-deriving it in the workflow would be a
  second copy of one classification, free to drift out of step with the first.
  The script's only judgment about the kind is to normalize an unrecognized
  value to `unknown`, which is why `kind=` is echoed back rather than dropped:
  the caller reports the kind actually used, so a normalization is visible
  instead of silent.
  **The denied-tool line is three-valued, not two.**
  Names known, a real zero, and no denial data at all are different facts, and
  only the middle one licenses the sentence a reader will act on.
  A short-circuited run exits before the guard ever counts denials, so the
  count arrives empty there -- rendering that as "none" would assert the
  reviewer was not blocked by permissions on a run where nothing about
  permissions is known, and would send a triager to the wrong place.
  This is the same distinction `check-review-execution.sh` draws with its own
  `denials_known` flag.
  **The threshold is passed through, never restated.**
  `STUB_RETRY_MAX_DENIALS` is overridable, so a hard-coded `5` here would be
  right only until someone overrode it -- the two-declarations-of-one-default
  problem gha#303 pinned a test against.
  The guard emits `max_denials`, and an empty value drops the threshold clause
  rather than substituting a number nobody compared against.
  **`denied_tools` reaches the calling script through `env:`, never through
  `${{ }}` in a `run:` body.**
  It is assembled from the commands the reviewer attempted, so it is
  agent-authored free text that routinely carries quotes, `$`, `;`, and
  redirects -- gha#541's whole subject was a reviewer reaching for
  `gh pr diff ... > /tmp/pr.diff`.
  The first draft of `Resolve final review outcome` interpolated it inline
  beside the `outcome` and `stub_review` reads already there, which is safe for
  those two (the runner and the guard constrain them to a fixed vocabulary) and
  is arbitrary command execution for this one: a sample carrying `$(...)` runs
  inside a job holding `CLAUDE_CODE_OAUTH_TOKEN`, and needs no quote-breaking to
  do it, since command substitution happens inside the double-quoted assignment.
  Reproduced directly rather than reasoned about, and closed by an `env:`
  assignment, which the runner substitutes rather than bash parsing it.
  `denials`, `max_denials`, and `failure_kind` ride along under the same rule
  even though none of them needs it, so nobody has to re-derive which member of
  the group was the dangerous one.
  The YAML half cannot be unit-tested, so the composer's suite pins the half
  that can: such a value must render verbatim, neither executed nor mangled.
  **The run URL is load-bearing rather than decoration.**
  `claude-code-review.yml`'s collapse step matches comments by the
  `actions/runs/<id>` link in their body, so without it every failed round
  would leave its own permanent, unfoldable copy on the PR.
  That collapse step is gated on this action's `posted` output rather than on
  the failure itself, mirroring gha#434's own fix: folding the previous run's
  notice after a failed post would leave the PR with no explanation at all,
  which is the outcome this action exists to prevent.

- `.github/actions/trigger-bugbot-review/` -- wraps
  `scripts/trigger-bugbot-review.sh`, which POSTs a PR URL to
  `https://api.cursor.com/bugbot/review` and fails unless the API returns
  `"outcome":"success"` plus a `request_id`.
  `cursor-code-review.yml` calls it so the reusable workflow can queue a
  Cursor Bugbot review without the caller's checkout containing this repo's
  scripts (`github.action_path`, same reason as `build-reviewer-args`).
  Success means queued: Bugbot posts comments and the `Cursor Bugbot` check
  itself, asynchronously.
  The API is Enterprise-scoped (`admin:*`); Team/individual installs enable
  Bugbot in the Cursor dashboard instead.
  A Team-plan key is not "almost Enterprise": the queue step fails with
  `HTTP 401: Invalid Team API Key` (dogfood `cursor-review.yml`, run
  32694255358, 2026-08-24, gha#601).
  That error means the secret reached Cursor and was rejected;
  it is not a missing `secrets:` mapping.
  The key is sent as an `Authorization: Basic` header via curl `--config`,
  not on argv, and the script never prints it.
  `--header` is not enough: it still puts the base64 credential on curl's
  argv (`ps` / `/proc/<pid>/cmdline`).
  jq's `//` treats JSON `false` as empty, so `.dry_run // empty` drops the
  common `"dry_run":false` response and falls back to the locally requested
  value (gha#511); parse with a null check instead.

- `.github/actions/build-reviewer-args/` -- wraps
  `scripts/build-reviewer-args.sh`, which splits a comma-separated reviewers
  list into a JSON array of trimmed, non-empty usernames.
  `request-dependabot-review.yml` calls it once to build its `gh api -f
  reviewers[]=...` arguments, so the split/trim logic has offline test
  coverage instead of only being exercised by a live Dependabot PR (gha#253
  review: a bare `IFS=',' read -ra` doesn't trim whitespace, so `"alice,
  bob"` sent an invalid `reviewers[]= bob` and failed the job).

- `.github/actions/install-gha-scripts/` -- copies named scripts out of
  `.github/workflows/scripts/` into a runner temp directory and outputs that
  directory, so a reusable workflow can call one from inside a `run:` block.
  The deliberate exception to the wrap-and-run shape every other helper here
  uses: `ai-code-review.yml`'s candidate loop makes its decision *inside* a
  shell loop over a dynamic agent list, and a composite cannot be invoked
  mid-loop, so the alternative was inlining the matcher beyond the reach of the
  offline table tests this repo relies on for exactly that class of logic
  (gha#362).
  It resolves via `github.action_path` for the same reason `run-review-guard`
  does.
  Two behaviours are load-bearing: a name carrying a path separator is refused
  rather than sanitized, since every real caller names a bare filename; and a
  missing script is an error rather than a silent no-op, which would leave the
  calling loop invoking a file that is not there.

- `.github/actions/open-failure-issue/` -- wraps two scripts:
  `scripts/select-existing-issue.sh`, which picks the open issue an automated
  failure report should be appended to (exact, case-sensitive title match;
  lowest number wins when duplicates already exist), and
  `scripts/split-csv-list.sh`, which splits and trims the comma-separated
  `labels` input so each name is passed as its own `--label`. That second one
  is the gha#253 bug class again: `gh issue create --label` is a Cobra
  StringSlice, which splits on commas without trimming, so a natural
  `bug, automated` yields a second item beginning with a space, which matches
  no label and fails the whole call. `build-reviewer-args.sh` delegates its
  own split/trim to the same script, so the repo has one CSV splitter rather
  than two. The composite does the
  `gh` calls around it: list open issues, then either comment on the match or
  file a new issue. `report-failure.yml` and `check-links.yml` both call it.
  Two behaviors
  worth knowing before changing it: a label the calling repository does not
  define is dropped with a warning and the issue is filed anyway, since losing
  a failure report over a missing label is the worse outcome; and `dry-run`
  exists so `_selftest.yml` can exercise the action for real without filing an
  issue on every selftest run (the lookup still runs, so it needs only
  `issues: read`).
- `.github/actions/generate-altdoc-version-dropdown/` and
  `.github/actions/generate-altdoc-landing-page/` - Python composites wrapping
  the scripts `altdoc-multiversion-docs.yml` needs (rewrite the navbar
  "Versions" dropdown; generate the root redirect landing page, and -- when
  the `legacy-paths` input is set -- a root `404.html` redirecting retired
  version directories to their replacements, gha#301). Ported from
  `d-morrison/rpt`'s bespoke `.github/scripts/` copies, generalized to derive
  the docs base URL and default branch from the caller's own context instead
  of a hard-coded repo (see `UCD-SERG/serocalculator#504`). Both invoke
  `.github/actions/resolve-altdoc-base-url/resolve_base_url.py` directly via a
  `github.action_path`-relative path (the `build-reviewer-args` idiom
  described above) rather than nesting a `uses: ./...` step -- a relative
  local path inside a composite action resolves against the top-level
  workflow's own checkout, not the repo the enclosing composite was fetched
  from, so a nested `uses:` step would fail to find `action.yml` for any real
  consumer (gha#284 review). Sharing the script this way still gives both
  composites one source of truth for the base-URL derivation instead of each
  carrying its own copy. Within `generate-altdoc-landing-page`, its two
  generator scripts (the landing page and the gha#301 legacy-path `404.html`)
  share `_site_output.py` for the `OUTPUT_DIR`/`DOCS_BASE_URL` plumbing they
  both need -- including the `site-root` default, which has to agree with
  `action.yml`'s own `output-dir` default and is asserted to by a test rather
  than left to a comment (gha#303 review). `generate-altdoc-version-dropdown`
  likewise splits its version-labeling and navbar-rewriting helpers into
  `navbar_version.py` (gha#307): those are pure functions, so they get unit
  tests, while importing the script itself would run its whole top-level flow
  (git lookups, a required `DOCS_BASE_URL`). That module also owns the two
  label suffixes (`" (stable)"`, `" (dev)"`), so the menu's own label is
  built in the same shape as the entries it sits above rather than drifting
  into a second format. The *version* in that label can still differ from
  the `(dev)` entry's, and deliberately does on a PR preview: the label
  comes from the rendered checkout's own `DESCRIPTION` (`local_version`),
  while the `/dev/` entry always names the default branch's version
  (`dev_version`, read from `origin/<default-branch>`). A PR that bumps
  `DESCRIPTION` therefore shows its own version in the navbar while the
  menu still points `/dev/` at what is actually deployed there -- both
  correct, since the reader is looking at the PR's build, not `/dev/`.

- `.github/actions/inject-canonical-urls/` -- wraps
  `inject_canonical_urls.py`, which adds a `<link rel="canonical">` to every
  indexable page of a rendered altdoc/Quarto tree before
  `altdoc-multiversion-docs.yml` deploys it (gha#332).
  That workflow publishes the same site to `/dev/`, `/latest-tag/`,
  `/vX.Y.Z/`, and `/pr-preview/pr-<N>/`, so without this every page exists N
  times with nothing naming the authoritative copy.
  Four things constrain any change to it.
  A canonical is emitted **only when the target exists**: the composite reads
  the pages currently under `/latest-tag/` off the deploy branch
  (`git ls-tree`, the same interrogation the `/latest-tag/` bootstrap step
  already does) and a page with no counterpart there self-canonicalizes,
  because a canonical pointing at a 404 asks the indexer to credit a page that
  is not there -- strictly worse than emitting none.
  PR previews get `noindex` rather than a canonical, since a preview is
  ephemeral and is not the authoritative copy of anything.
  `404.html` is excluded from the indexable set, as canonicalizing the page
  served for missing URLs would point every miss at a real page.
  And the verification pass re-**reads** the files rather than trusting the
  insertion pass's own report, because an off-by-one in the insertion index
  produces a plausible log and a broken page; only a re-read separates them.
  The step is wired in after every `subdir=` assignment and before every
  deploy, which is load-bearing rather than incidental -- placed earlier (the
  obvious spot, right after the sibling "Report an issue" rewrite) `env.subdir`
  is not yet set, so the self-canonical fallback silently receives an empty
  path.

- `.github/actions/bump-dev-version/` and `.github/actions/check-dev-version/`
  -- composite actions wrapping `description-version.R`'s pure
  `read_version`/`versions_equal`/`bump_dev_version` logic via the
  `github.action_path`-relative pattern described above (the
  `build-reviewer-args` idiom), since `bump-dev-version.yml` and
  `version-check.yml` are reusable workflows referencing this repo's own
  scripts and cannot rely on their caller's checkout containing them.
  `bump-dev-version` bumps the dev-version counter (the 4th `.90NN`
  component of `DESCRIPTION`'s `Version:`) and hands off to
  `open-sync-pr@v2`; `check-dev-version` fails a PR whose `DESCRIPTION`
  differs from the base branch's at all, inverting the older
  `RMI-PACTA/actions`-derived `version-check.yaml` copies each repo used to
  carry, so no PR branch ever holds a competing version to conflict on
  (gha#390).

- `.github/actions/check-tag-drift/` -- composite action wrapping
  `check-tag-drift.sh` (which sources shared `resolve-major-tag.sh`, also used by
  `slide-major-tag.yml`) via `github.action_path`, deriving the active major tag from the
  latest semver release tag (`vX.Y.Z`) and emitting a GitHub Actions notice and job summary when
  `main` has unreleased commits ahead of the major tag (gha#309).

- `examples/` -- caller stubs consumers copy into their own repos.
- `README.md`, `CHANGELOG.md` -- top-level project docs;
  `REVDEPS.md` --
  lists registered downstream consumer repos. Every PR that

  changes user-facing behavior should add a **changelog fragment** under
  `changelog.d/` (a `<slug>.<category>.md` file -- see `changelog.d/README.md`)
  rather than editing `CHANGELOG.md` directly, so parallel PRs never conflict on
  the same `## [Unreleased]` lines. `changelog.d/assemble.sh` collates the
  fragments into `CHANGELOG.md` at release time. This is not CI-enforced
  (`require-changelog.yml` was removed).

When editing a consumer-facing capability, change the composite (`<name>/action.yml`,
plus its helper script if one exists) and keep the wrapping reusable workflow and its
`examples/<name>.yml` stub in sync. Internal-only composites (like `open-sync-pr`)
have no wrapper or example stub to update. New `.github/workflows/` changes are
exercised by `_selftest.yml`; because brand-new actions aren't at the `@v1` tag
yet, the selftest runs them via the local `./<name>` ref until release.

**Migrating a consumer's bespoke workflow to a reusable one here needs a
feature-by-feature diff, not just a structural read.** A reusable capability
can look like a superset of the bespoke version it replaces -- more inputs,
more hardening, more edge-case handling -- while still missing one specific
step the bespoke version had, because that step covered something the
reusable capability's original author's own repos never needed. Read the
bespoke workflow line-by-line and confirm each step (not just each job) has
an equivalent in the composite/reusable version before treating the
migration as drop-in; don't infer parity from the reusable version's inputs
table or its being "the canonical, more capable version" in general. When a
gap turns up, file it upstream (here) and defer that one file's migration
rather than silently dropping the feature or hand-duplicating it in the
consumer's stub. ([`UCD-SERG/serocalculator#548`](https://github.com/UCD-SERG/serocalculator/issues/548)/[#549](https://github.com/UCD-SERG/serocalculator/pull/549):
`test-coverage.yml` looked like a straightforward superset of
serocalculator's bespoke `test-coverage.yaml` -- same coverage measurement,
same testthat-output and failure-artifact steps -- but was missing the
JUnit-report upload to Codecov Test Analytics (`codecov/test-results-action`)
the bespoke version also did; gha#234 tracks closing that gap, and the
consumer left that one file unmigrated in the meantime rather than lose the
feature.)

**A new composite action cannot gain its first `@v2` caller in the same PR
that introduces it, and whether that bites depends on whether the caller is
dogfooded here.** A `uses:` ref is resolved when the job is *prepared*, before
any step runs and before any step-level `if:` is evaluated, so a reference to
`Morrison-Lab/gha/.github/actions/<new-action>@v2` fails the whole job with
`Can't find 'action.yml' ... @v2` until `@v2` is advanced past the merge --
even when the step is gated on `failure()` and would never have run.

The Tests section's `build-reviewer-args` paragraph records the same
bootstrapping gap, and treats it as a coverage limitation: that workflow's
own reusable layer cannot be exercised end to end until the tag advances.
That reading is right there, because `request-dependabot-review.yml` only
runs on Dependabot PRs, so nothing goes red in the meantime. When the new caller
is something `_selftest.yml` invokes through a local `./` ref on every PR
(`check-links.yml` is the one that does), the gap stops being a coverage
footnote and becomes a red check on every PR in the repo, with no way to fix
it inside that PR: a relative local path is not a workaround either, since
inside a reusable workflow it resolves against the *caller's* checkout
(gha#284).

So split the work: land the action plus its non-dogfooded callers first, and
migrate a per-PR-dogfooded caller in a follow-up once the tag has moved.
(gha#326: `check-links.yml`'s migration and `website-publish.yml`'s
dogfood job were both cut from that PR for this reason and landed in gha#327,
after `links / link-checker` went red on exactly this.)

**A brand-new capability that ships at a tag newer than `@v1`** (because `@v1`
was frozen before it existed -- see `slide-major-tag.yml` / the Versioning
section of `README.md`) needs its major tag updated at two distinct kinds of
site, not just the obvious one:

1. **Capability-specific refs** -- the new capability's own caller stub
   (`examples/<name>.yml`) and reference-page example
   (`website/reference/<name>.qmd`).
2. **Blanket-rule prose** -- any general "pin every reference to `@v1`"
   statement elsewhere (`README.md`'s Versioning section,
   `website/workflows.qmd`) needs an exception clause, even though it never
   names the new capability.

Grep the repo for `@v1` rather than relying on memory of where it appears.
Missing either kind surfaces as a workflow-not-found error for consumers who
copy that spot literally (gha#148, caught across two review rounds).

**When narrowing an already-fixed blanket claim, re-grep the WHOLE repo after
every edit --
not just the files you already know about.** The same versioning

convention gets restated in multiple, independently-worded spots: not just
once per file, but in separate sections of the *same* file (e.g. `README.md`'s
`## Versioning` section and its nested `### Pinning third-party actions`
subsection both needed the same `@v1`/`@v2` exception clause), and across sibling
pages that all describe the tag scheme (`website/index.qmd`'s nav blurb,
`website/versioning.qmd`, `website/workflows.qmd`, `CLAUDE.md`'s own "About
this repo"). Fixing the first instance you find and moving on invites the
reviewer to find the next one in a later round -- gha#181 took six review
rounds to fully sweep this exact pattern (`@v1`/`@v2` scoping) because each
fix only searched the files already in the diff. Before considering a
versioning-prose fix complete, `grep -rn "@v1\|@v2"` (or whatever pattern is
narrowing) across the **entire** repo, not just the files already touched.

**That rule is not about versioning, and its own wording is what hides
that.**
Every example above names `@v1`/`@v2`, and the closing sentence says
"versioning-prose fix", so a sweep of some *other* repeated string does not
read as covered -- and the identical failure then repeats verbatim.
The `d-morrison/gha` -> `Morrison-Lab/gha` retarget hit it twice: one pass
missed `website/_quarto.yml` entirely, and gha#374's own first pass left five
more live sites, four of them the exact categories that PR was fixing
elsewhere (the generated-consumer-PR-body link, the "not `d-morrison/gha`'s
own tree" comment).
Read it as applying to any repeated string being retargeted -- an owner, a
URL, a tag, a renamed input -- and grep for that string rather than for
`@v1`.

**A completeness claim in a changelog fragment is the one claim neither a
reviewer nor a check can verify from the diff, so it needs the grep before it
ships.**
"The last stale `X` references are gone" is an assertion about the *tree*
rather than about the diff, so a reviewer reading the diff has nothing to
check it against, and no CI job tests it either.
It also reads as settled, which is what stops anyone from re-running the grep
later.
So when a fragment claims a sweep is complete, run the whole-repo grep and
either make the claim true or enumerate the carve-outs explicitly.
gha#374's review caught exactly this, citing the paragraph above as the
governing principle -- which is the evidence that the rule was right and only
its stated scope was too narrow.

**Adding a new `workflow_call` input to an existing reusable workflow** needs
its own doc sync at three sites beyond the workflow file itself, or the input
is invisible to a consumer skimming the docs:

1. **`README.md`**'s per-workflow table row's "Key inputs" cell.
2. **`website/workflows.qmd`**'s equivalent table row -- a separate table, not
   generated from `README.md`, so it drifts independently.
3. **`website/reference/<name>.qmd`**'s Inputs table, plus a commented usage
   line in its `## Example` block.

Grep the repo for the workflow's filename (e.g. `claude-code-review.yml`)
across `README.md`, `website/workflows.qmd`, and `website/reference/` rather
than assuming only one needs the update. Caught across four review rounds on
gha#161 -- the fix for round 2's finding (missing composite) surfaced round
3's finding (docs out of sync), whose fix left one more untouched table row
that round 3 flagged as out-of-scope, fixed anyway before round 4 confirmed
clean.

**Widening a job's trusted-author `if:` gate to admit a new event type needs
a three-way audit across everything that decides something about the new path,
not just the gate itself.**
A productive audit of one direction is not evidence that other directions are
clean (gha#552/#553):

- **Downstream -- steps in the same job** whose `if:`/`env:` read event-shaped
  context (`github.event.issue.number`, `github.event.comment.body`, etc.).
  A step that looks safely scoped -- e.g. gated on a
  `steps.dedup.outputs.skip != 'true'` flag -- can still run and fail under the
  newly-admitted event, because that flag was never set for it either;
  the flag and the missing context are two independent gaps, and fixing the
  top-level `if:` closes neither.
  Grep the same job for every step reading event context and add the same admit
  condition (or an explicit exclusion) to each one.
  (gha#245/#246: widening `claude.yml`'s job `if:` to admit
  `workflow_dispatch`/`schedule` left two post-steps --
  `Acknowledge @claude mention` and `Post Claude's response if no code was
  committed` -- still ungated for those events;
  both ran and attempted `gh issue comment ""` on every unattended run, one
  failing visibly, contrary to the PR's own prompt text claiming no post-step
  would post a reply.
  Caught by review, not by the author's own initial self-check.)

- **Upstream -- the caller-side job `if:`** in `examples/` and in this repo's
  own dogfood caller workflows.
  A reusable workflow is never invoked if the caller's gate doesn't admit the
  event, and the new input is then silently inert for any consumer following the
  docs (gha#552 review: adding `dispatch-on-assignee` left `examples/claude.yml`'s
  gate dropping `issues.assigned` runs before the workflow could see them).

- **Sideways -- sibling branches of conditionals referencing the event**
  predating the new case (prompt text, `format()` ternaries, step names).
  (gha#552 review: the prompt's opening ternary told every assignment run it was
  "triggered by an @claude mention", which for that path does not exist.)

### Tests

`check-phi/tests/test_detectors.py` is a pytest suite pinning each PHI detector's
positive and negative behavior. Run it with `python3 -m pytest check-phi/tests/ -q`;
CI runs it as the `phi-tests` job in `_selftest.yml`. There's no broader unit-test
harness -- most capabilities are validated end-to-end by `_selftest.yml`, running
against this repo itself or small throwaway fixtures (stable capabilities via
`@v1`, pre-release ones from local source).

`check-new-line-breaks/tests/test_check_new_line_breaks.py` is a pytest suite
covering the sentence-splitter/block-detector functions directly and, via
small throwaway git repos (`tmp_path` fixtures, generated at test time --
nothing committed), the diff-scoping behavior itself: a newly-added
multi-sentence line is flagged, a pre-existing one in an untouched line is
not, and a diff that can't be computed skips rather than falling back to a
whole-tree scan. Run it with
`python3 -m pytest check-new-line-breaks/tests/ -q`; CI runs it as the
`new-line-breaks-tests` job in `_selftest.yml`, alongside a `new-line-breaks`
job that exercises the real composite (`base-ref` diff mode) against this
repo's own tree, the same "local composite, not yet the `@v1`-pinned
reusable-workflow chain" precedent `phi` uses above.

**Running that check locally before a push proves nothing about files you have
not committed yet, and it reports them as clean rather than as unchecked.**
`_added_line_numbers` (called from `find_violations`) diffs
`"$base_ref"..."HEAD"`, so its population is the **commit graph** -- a staged
file is invisible to it, and an untracked one doubly so.
Nothing in the output distinguishes "checked, no violations" from "there was
nothing to check", which is what makes it misread rather than merely miss:

```bash
git add -A
NLB_BASE_REF=origin/main python3 check-new-line-breaks/check-new-line-breaks.py
# -> No lines missing semantic breaks.        (it examined zero added lines)
```

So commit first.
The ref itself needs no special care: `A...HEAD` is three-dot, which git
resolves to the merge-base of `A` and `HEAD`, so `NLB_BASE_REF=origin/main`
already means what the `new-line-breaks` job's own merge-base SHA means.
Committing is the whole of the fix.
Measured on gha#544: a local run over a staged changelog fragment reported
clean, and CI flagged three lines in that same file on the very next push.
This is the general verify-the-right-artifact trap in
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/verify-the-right-artifact.md)
wearing local clothes: the working tree is an adjacent artifact to the one the
instrument actually reads, and checking it thoroughly is still checking the
wrong thing.
The same reasoning applies to every diff-scoped check here -- `check-phi` and
`check-new-line-breaks` take a `base-ref`, and `check-secrets` scans history --
so none of them can see an uncommitted change either.

The suite also covers the gha#336 clause check (a long line carrying a
mid-line semicolon, as a proxy for SemBr rule 5), including that it is
**on by default** -- and pins the two defaults that are declared in three
places at once.
`_DEFAULT_CLAUSE_BREAKS`/`_DEFAULT_CLAUSE_MIN_LENGTH` in the script are the
single source, but `action.yml` and
`.github/workflows/check-new-line-breaks.yml` each re-declare them for their
own inputs, so a parametrized test reads both YAML files and asserts they
agree with the script -- the same gha#303 precedent that pinned
`generate-altdoc-landing-page`'s `site-root` default rather than leaving it
to a comment.
The first draft of #336 proved why: `find_violations()` kept a stale `False`
default while `classify_line()` and `main()` had moved to `True`, and only
the test caught the drift.
That test parses the YAML with a line scan rather than a YAML library,
because the `new-line-breaks-tests` job installs only pytest.

**A selftest step that sets no `fail:` cannot prove the input reached the
script, however it is worded.**
`_selftest.yml`'s `new-line-breaks` job does call the composite a second time
with `clause-breaks: 'false'`, and that is worth having as a real `uses:`
exercise -- but `main()` now returns 1 by default when violations are found (NLB_FAIL defaults to true),
so the step fails on findings rather than proving whether a specific input arrived or was dropped.
What actually pins the `env var -> main() -> exit code` path is a set of
pytest cases that set `NLB_FAIL=true` around a real `main()` call on a
throwaway git repo, asserting exit 1 with the clause check on and exit 0 both
with `NLB_CLAUSE_BREAKS=false` and with the length gate raised past the line.
(gha#337 review round 2: the step's original comment, and this paragraph,
both claimed the step proved the plumbing; neither could.)
Round 3 added the converse caveat, since "cannot prove the input arrived" is
not "proves nothing": the step still pins that `action.yml` parses and that
the opt-out code path runs to completion, which is why it stayed rather than
being deleted as dead weight.
Round 5 narrowed that caveat in turn -- it had also claimed the step pins
that the input is *declared*.
Declaration is pinned by the defaults-agreement test instead, which reads each
YAML file for the input's `default:` and fails outright when there is none
(gha#337 review round 5).

**Markup stripping is where this check's false verdicts come from, in both
directions.**
The clause check keys on a semicolon in the *stripped* line, so every pattern
in `strip_inline_markup` decides two things at once: whether a `;` is prose,
and whether the line is long enough to look at.
Both of gha#337's round-3 findings were one pattern each.
A code-span pattern of `` `[^`]*` `` matches the empty span between the two
opening backticks of a ```` ``...`` ```` span, so an N-backtick span kept its
contents and a `;`-separated shell command read as prose -- the exact case
the stripping exists to remove.
And a bare-URL pattern of `https?://\S+` runs to the next whitespace, so a
`;` immediately after a URL was deleted along with it, silencing a genuine
break.
The rule that catches both: a pattern must remove the construct and nothing
adjacent to it, so backreference a delimiter's opening run rather than
matching to the next one, and stop a URL before trailing sentence
punctuation.

**The sentence regex has two independently-breakable halves, and a fix to
one does not touch the other.**
`_SENT_BREAK_RE` is `[.!?]` plus a **closing-character class**, then
whitespace, then a **lookahead** at what starts the next sentence.
Each half fails silently and in the same direction -- a missed boundary means
the line reads as one sentence, so the check passes it clean.
gha#397 was the closing class omitting `*` and `_`, which swallowed every
`**Claim.** Explanation.` line.
Measured on 2026-08-03, adding the two characters took the multi-sentence lines
detected across `Morrison-Lab/ai-config`'s Markdown from 2837 to 3398, and
across this repo's from 719 to 784 --- increases of 19.8% and 9.0% *over the old
counts*.
Stated as a share instead, which is the figure that says how much was hidden:
the 561 lines `ai-config` gained are about one in six of what the fixed check
finds (561/3398 = 16.5%).
Those two denominators are easy to mix up, and only the second answers "how much
was the blind spot hiding".
Note also that at that measurement the lookahead half still missed a whole
class of sentence, so 3398 was itself an undercount and the true hidden share
was lower still --- which is an argument about the size of the number, not
about whether it is worth fixing.
That gap was gha#389: the lookahead required ``[A-Z"'`*\[]`` and so missed a
sentence opening with a bare lowercase identifier (`renv restored the
lockfile.`), the exact shape our prose writes most.
gha#425 closed it with a second branch, `_SENT_BREAK_LOWER_RE`, that accepts a
lowercase follower under two structural guards that share the work rather than
one lookbehind carrying all of it.
Get the division of labour exactly right, because this block is the map future
widenings are read against, and three review rounds on gha#425 corrected earlier
guesses here --- each attribution below is what a mutation test (remove a guard,
see which case starts splitting) actually shows, not what reads plausibly.
The `(?<=[a-z][a-z])` lookbehind requires two lowercase letters immediately
before the terminal punctuation.
It is the guard that refuses a single-letter initial (`U.S.`, the `.` follows
`S`), a dotted abbreviation (`a.m.`, the `.` follows `.m`), a one-letter token
(`option a.`), a digit- or version-ending token (`plan9.`, and `v2.1.` at a
clause end where the `.` does have a following space), *and* the ellipsis
(`wait... foo`): the only dot with a following space is the third, and the two
characters before it are both dots, so the lookbehind fails there.
The branch also has no closing-character class at all, so the terminal `[.!?]`
must be immediately followed by whitespace --- which is what keeps mid-sentence
emphasis (`**critical.** yet`) and a quoted or parenthesized fragment (`he said
"stop." then`) on one line.
Separately from both guards, an *internal* decimal or version dot (the `.` in
`0.9012` or `v2.1` between the digits) never reaches a split attempt at all,
since it has no following space for the `\s+` to match.
A closing class was tried on the lowercase branch and removed.
The uppercase branch safely carries emphasis and quote closers --- #397 *added*
`*`/`_` to its class so a `**bold.**` sentence end is caught rather than
swallowed --- because its uppercase-follower lookahead still refuses a
mid-construct lowercase continuation.
The lowercase branch's follower is lowercase, so any closer would fire on
exactly those mid-construct cases (`"stop." then`, `**critical.** yet`) and
re-introduce an over-split, which is why it has no closing class at all.
So when either branch is widened, ask what the *other* guards now block before
concluding the construction is covered --- and pair the widening with a
negative case, since the guards are each other's backstops.
The lowercase branch also made the pre-existing abbreviation list reachable for
lowercase forms (`3 sec. then`), and getting that right took three review
rounds because the abbreviation protection reaches both branches by default:
`_ABBREV_RE` runs once, up front.
The trap each round hit is that an abbreviation edit made for one branch
silently regresses the other --- dropping `No` un-split `Item No. Three` on the
uppercase branch, then registering every lowercase form un-split
`It took 300 ms. The next ...` on it too.
The disambiguator is the follower's case: a lowercase unit before a lowercase
word (`3 sec. then`) is mid-sentence, but before an uppercase word
(`300 ms. The`) it is a genuine boundary that must still split.
So gha#425 protects the conventional-case abbreviations on both branches
(`No.`, `Sec.`, unchanged from before), and protects the lowercase forms in a
*second* pass (`_ABBREV_LOWER_RE`) applied only after the uppercase branch has
run --- so the lowercase forms suppress the lowercase branch without ever
reaching the uppercase one.
That second list excludes `no` (a lowercase `no.` is the word, and should
split) and adds `min`/`hr`/`hrs`; it is curated rather than exhaustive, so an
unlisted lowercase abbreviation before a lowercase word can still false-split
on this check.
The whole regex is duplicated in `Morrison-Lab/ai-config`'s
`scripts/semantic-line-breaks.py`, the reformatter this check is the detector
half of, so a fix to either is owed to the other (porting gha#425's fix there
is tracked in Morrison-Lab/ai-config#1212).

`check-secrets/tests/test-build-config.sh` is a shell suite over
`build-gitleaks-config.sh`, the script that turns the `paths-ignore`,
`allowlist-file`, and `config` inputs into the gitleaks TOML the scan runs
under.
That generator is the piece worth testing because its failure mode is
one-directional: a bug there widens an allowlist and quietly suppresses real
findings, so the check goes green rather than breaking.
Run it with `bash check-secrets/tests/test-build-config.sh`; CI runs it as the
`secrets-tests` job in `_selftest.yml`, alongside a `secrets` job that
exercises the real composite against this repo's own full history -- the same
"local composite, not yet the `@v2`-pinned reusable-workflow chain" precedent
`phi` and `new-line-breaks` use above.

Two of its cases are the ones to keep if the suite is ever trimmed.
A pattern carrying `'''` is refused rather than written, since a TOML literal
string has no escapes and one would truncate the array, changing which
findings are suppressed; that case was confirmed to fail when the guard is
stubbed out.
And a named-but-missing `config`/`allowlist-file` is an error rather than a
silent fall back to the default ruleset -- a typo'd path must not read as "no
allowlist".

`check-secrets/tests/test-scan-secrets.sh` covers the other half, and exists
because the `secrets` job structurally cannot.
That job runs against this repo's own history, which is clean by design and by
measurement, so it always takes the zero-findings early return -- meaning the
`fail`-keyed branches, the annotation loop, the step summary, and the exit code
never execute in CI.
Round 1 of gha#385's review found a fail-open `fail` bug in exactly that region
while both selftest jobs stayed green, which is the same shape as the
`check-new-line-breaks` lesson two paragraphs up: a step that cannot fail
proves nothing about the code past the point it returns.

The fix is a **stub `gitleaks`** on `GITLEAKS_BIN_DIR` that writes a canned
report and exits 0, so the real branching runs offline with no download and no
network.
Reintroducing either of the two bugs those tests were written for -- the
fail-open comparison, or truncating the fingerprint to a 12-character SHA --
turns two assertions red each; both were confirmed by mutation rather than
assumed.

**Its fixtures carry no credential-shaped strings, deliberately.** The
`secrets` job scans this repo's own history, so a realistic dummy token in a
committed fixture would trip it forever after -- the committed-fixture trap
the paragraph below describes, in the one form no runtime generation can
undo, since the commit that added it stays in history.
The canned report the stub writes carries only `RuleID`, `File`, `StartLine`,
`Commit`, and `Fingerprint`, never `Match` or `Secret`, for the same reason.

`check-junk-files/tests/test-check-junk-files.sh` is a shell suite driving
`check-junk-files.sh` against throwaway git repos built in `$TMPDIR` -- nothing
committed, for the same reason the `test-coverage` fixture is generated: a
committed `.DS_Store` would be swept into this repo's own `junk-files` selftest
job forever after.
Every fixture is force-added (`git add -Af`), because a developer running the
suite on a vaccinated machine has a global gitignore that silently skips the
very files under test.
CI runs it as the `junk-files-tests` job in `_selftest.yml`, alongside a
`junk-files` job that exercises the real composite: once against this repo's
clean tree, once against a `.DS_Store` staged into the index (the scan reads
the index, so no commit is needed) with `continue-on-error` plus an `outcome`
assertion, and once with that file exempted through `paths-ignore` -- the two
input paths a wiring typo would silently turn into "checks nothing" and
"exempts nothing".
The four cases to keep if the suite is ever trimmed are the negative ones,
because each pins a decision that is silent when reversed: a force-added file
listed in the repo's own `.gitignore` is not reported (passing
`--exclude-standard` reports it), `paths-ignore: 'vendor/'` really exempts the
directory (implementing it as gitignore `!` lines exempts nothing), an empty
pattern set is an error rather than a green check that examined nothing, and a
filename merely *containing* `.DS_Store` is not a match.
All five mutations were confirmed to turn the suite red rather than assumed
to, the sixth being the defaults-agreement check that `action.yml` and
`.github/workflows/check-junk-files.yml` declare the same `patterns` string --
the gha#303 precedent, and here a drift would hand a consumer of the reusable
workflow a different pattern set from a consumer of the composite with nothing
red.

**Generate selftest fixtures at runtime; don't commit them.** A fixture
committed under a composite's `tests/` dir (e.g. a minimal R package for
`test-coverage`) gets swept into OTHER selftest jobs' repo-wide scans: the
`bib` job's dependency resolution tries to treat it as a real package, and the
`phi` job's PHI scanner flags any synthetic identifier in it (a fake
maintainer email, etc.). Generate the fixture in a small script
(`test-coverage/tests/make-fixture.sh` is the pattern) that the `coverage`
selftest job runs before invoking the composite, instead of committing R
package source files (gha#148).

`.github/workflows/scripts/check-review-execution.sh` holds
`claude-code-review.yml`'s fail-check guard logic (stub/placeholder-review
detection, quota-exhaustion skip) as a standalone script, so it can run
offline against canned execution-output fixtures instead of requiring a live
Claude API call. `.github/workflows/scripts/tests/run-fixture-tests.sh` feeds
each fixture under `scripts/tests/fixtures/` through the script and asserts
the expected pass/fail/skip/fail-stub outcome (`fail-stub` -- gha#185 -- is a
`fail` fixture that must ALSO write `stub_review=true`, the signature
`claude-code-review.yml` retries on); CI runs it as the `review-fail-check`
job in `_selftest.yml`. These fixtures ARE committed rather than generated at
runtime -- unlike the R-package/PHI-shaped fixtures the rule above warns
about, they're plain JSON execution-output data with no content that would
trip the `bib` or `phi` jobs' repo-wide scans (gha#174).

**Quota exhaustion arrives in two shapes, and the second one has real cost
behind it.**
The original `quota-exhausted.json` is a request rejected at the door --
`total_cost_usd: 0`, `num_turns: 1` with an `error_*` subtype (an `is_error: true`
run with `subtype: "success"` is an execution failure rather than quota exhaustion,
gha#561) -- and the guard keys the graceful skip on that shape.
An account can also run out **mid-review**, which the pair cannot see: gha#520
was observed at 13 turns and $4.10, with `api_error_status: 429` and
`is_error: true` alongside `subtype: "success"`.
Before the fix that fell through to the hard `is_error` exit and reddened
`claude-review` over an account condition the PR's author could not act on,
with no comment on the thread saying so.
Two things constrain any change here.
The detection keys on the structured `api_error_status` field and never on the
`result` message's prose, for the reason `classify-gemini-failure.sh`'s own
header gives (gha#380 finding 1) -- that message is ordinary text, and matching
prose against a transcript is how a genuine failure gets misclassified as a
graceful skip.
And the check sits **after** the gha#391 verdict check rather than beside the
zero-cost one, so a run that stated its verdict and only then hit the limit
still passes; `quota-exhausted-midrun-with-verdict.json` is the fixture that
pins that ordering, and it passes with or without the fix by design -- the
fixture that actually fails when the fix is removed is
`quota-exhausted-midrun.json`, confirmed by mutation rather than assumed.

**`permission_denials_count` can be absent from the real execution file even
though `claude-code-action` prints it to the job log, because the log line is
a display value the action computes, not a field it always writes to disk.**
gha#531 was observed on a real run: the printed log read
`"permission_denials_count": 5`, but the saved execution file's `result`
object carried no such key at all -- only `permission_denials`, an array of
5 denial-detail objects.
Reading `.permission_denials_count // "MISSING"`
alone therefore read `MISSING` and defaulted to the 999999 sentinel, which
wrongly excluded the run from the gha#185 stub-retry even though the real
count (5) sat right at the threshold.
The fix falls back to
`permission_denials | length` when the scalar is absent/null but the array
is present, tried only after the scalar so every scalar-only fixture is
unaffected; `permission-denials-array-only-low-count.json` and
`permission-denials-array-only-high-count.json` pin both directions (within
and above `max_denials`), confirmed to fail pre-fix by running them against
the pre-#531 script.

**That same array is what the log was throwing away, and the count alone reads
as a different failure than it is.**
gha#540: a `permission_denials_count=24` warning names no tool, so two readers
of one log reached a wrong cause for the same failure
(Morrison-Lab/ai-config#1773), and a 12-denial run on Morrison-Lab/wai#83 left
a hypothesis -- sub-agent spawns, or file reads? -- that one line of log would
have settled.
A red check with only a number on it reads as "the reviewer gave up" rather
than as a permissions gap with a specific fix.
So `check-review-execution.sh` now summarizes `permission_denials` beside the
count (`Denied tools: Taskx6 Bashx3 WebFetchx2`) with one argument sample per
tool, and repeats both in the over-threshold annotation, which is the line a
triager reads without opening the job log.
Four things constrain any change to it.
The summary is emitted **where the count is computed**, not inside the
over-threshold branch the issue proposed: the low-count case is retried and can
stub a second time, so it needs the same diagnostic.
Summary and sample come from **one** jq pass emitting two lines, because they
share the grouping and the ordering -- computing them separately meant two
traversals and two copies of `group_by | sort_by` that could drift into
disagreeing about which tool leads, which is `detect-review-request`'s
two-copies-of-one-pattern problem at expression scale.
The sample takes one entry **per tool group**, ordered like the summary and
capped at the leading three groups, rather than the first three distinct
arguments overall -- a globally-unique list is ordered by the argument text, so
the commonest tool can drop out of its own sample entirely (the first draft
summarized six `Task` denials and then showed none of them).
The summary itself stays uncapped, so a fourth tool is still counted even
though it is not quoted.
Token-shaped literals are redacted from the sample, because Actions masks a
configured `secrets.*` value in a run log but not a credential the agent
constructed itself.
And a result carrying a scalar count with **no** array -- the exact mirror of
the gha#531 case above, and what `stub-gha198-high-denial-count.json` already
was -- reports `names unavailable` rather than an empty list, which would read
as "nothing was denied".

**`denials` is three-valued, and the reporting is the first consumer that has
to care.**
It is a real `0`, a real positive count, or the `999999` sentinel, which means
**unknown** rather than "a great many".
Both pre-existing gates want unknown to read as unsafe, so collapsing it into
the positive case is exactly right for them -- which is what makes the
conflation invisible to a reader of that code, and what the gha#540 reporting
then inherited by writing its own guard as `denials != 0`.
The two gates ask "may this be trusted?", where erring toward no is free.
A log line asserts something *about* the run, and there erring is not free:
an unparseable count says nothing about whether any denial occurred, so
reporting it as the no-array case told a **clean passing run** it had denials
(`is-error-success-with-verdict.json`, whose count is JSON `null`).
So knownness is tracked as its own `denials_known` flag rather than
re-derived from the magic number, the unknown case gets its own wording, and
one `denied_note` feeds both the log line and the annotation so they cannot
describe the same run differently.
Note what the negative test could not see: `must_not_log`'s original entry was
`genuine-finished-review.json`, whose count is a literal `0`, so the branch
never fired for it under either version and the assertion passed while the bug
was live.
A fixture with a **null** count is the one that discriminates, which is the
same lesson as the vacuous `names unavailable` needle below -- a negative
assertion is only worth the fixture that can actually reach the branch.
(gha#544 review, caught by the reviewer rather than by this suite.)

**Its coverage needed a new kind of assertion, and the first draft of one
passed vacuously.**
Everything `run-fixture-tests.sh` asserted before keyed on the exit code, a
`GITHUB_OUTPUT` line, or the posted `review_text_file`; what gha#540 changed is
what the script **logs**, which none of those can see.
`must_log`/`must_not_log` are that assertion -- substrings the combined
stdout/stderr must and must not contain -- and they matter more than their
size suggests, since a dropped tool name regresses into a quiet log rather
than a broken check.
All five mutations were confirmed to turn the suite red (dropping the
redaction, sorting alphabetically instead of by count, making the sample
globally unique, deleting the `names unavailable` line, and emitting the
summary only above the threshold), which is how the fourth one was caught not
being: the assertion had been the bare phrase `names unavailable`, and the
over-threshold annotation carries that phrase too as its own
`${denied_summary:-...}` fallback, so it passed with the log line deleted.
It is anchored on the whole line now.
Read that as the general shape rather than as one fixture's detail: a needle
short enough to appear in a second, unrelated code path tests neither.

**A test for one redaction pattern must be reachable by ONLY that pattern, and
getting this wrong three times in one session is what makes it worth a rule.**
gha#543 moved `denied_tools` from a masked run log to an unmasked PR comment,
so gha#548's review round 2 widened the chain to six patterns.
Each new one was measured leaking before the fix and redacted after.
The hard part was not the patterns; it was the tests.
A credential written into an `Authorization:` header is caught by the generic
header backstop whatever vendor prefix it carries, and one written into URL
userinfo is caught by the userinfo pattern -- so a case built either way passes
with the pattern it exists to test deleted.
That happened to the Anthropic case, then again to the modern-PAT case after
the first fix, then again when the PAT was moved into userinfo.
Only a mutation sweep found it each time, because every version looked
plausible and every version passed.
So carry each credential in a form no other pattern can reach: a bare
assignment or a file write, never a header and never a URL.
A sibling pattern is one way to make such a case vacuous.
The other is a **later stage of the same path** (gha#571, gha#574): a guard that
rejects for a second reason -- a missing file, an empty value, a type check -- fails
the input whether or not the alternative under test exists.
So a negative case must be built so the code **succeeds** when the thing being
tested is removed, not merely fails differently.
Simulate both ways before trusting it.
The same sweep found `github_pat_` had no case at all -- a pre-existing pattern
whose deletion turned nothing red.
And pair the set with a benign command that must survive untouched, since a
redaction that ate the diagnostic would satisfy every leak assertion while
destroying what gha#540 added the names for.

**The redaction mutation is the one whose fixture cannot be committed**, so
`run-fixture-tests.sh` builds that one at run time and assembles the token from
a literal prefix plus a generated body.
The committed-fixture rule two paragraphs down is the reason, in the form that
has no undo: `check-secrets` scans this repo's own **history**, so a
credential-shaped string in a committed file trips that scan for good, and
deleting the file later does not reach the commit that introduced it.
Generating it is the same move the `test-coverage` R-package fixture makes for
a different scanner, applied to the one input that must never land in a commit
at all.

**A sixth mutation is about the summarizer itself rather than its output, and
it is the one worth reading if only one is.**
Every `jq` lookup in both filters is `?`-suppressed.
That is not defensive habit: a denial entry whose `tool_input` is a **string**
rather than an object makes a bare `.tool_input.command` raise
`Cannot index string with string`, and under this script's `set -e` that aborts
the whole run at exit 5 -- before the verdict check, before `review_text_file`,
before anything.
So the check goes red carrying a jq error in place of whatever the review
actually concluded, which is strictly worse than the missing-names problem
gha#540 set out to fix.
Reproduced directly (exit 5, empty `GITHUB_OUTPUT` past the count) rather than
reasoned about, and pinned by `permission-denials-malformed-entries.json`,
whose expected outcome is the ordinary `fail-stub` -- the assertion is that the
review still gets classified, not that some log line appears.
The general shape is the one `detect-review-request` already records for its
oversized-body E2BIG: an optional diagnostic must not be able to redden the job
it is diagnosing.
One further constraint follows from where those comments live.
Both filters are single-quoted shell strings, so a comment inside them must
carry **no apostrophe** -- one closes the string, and the first draft of that
very comment failed `bash -n` by writing a possessive.

**Fixing the guard alone leaves the check red, which is why gha#520 touched the
workflow too.**
`claude-code-action` exits 1 on any `is_error` result, quota exhaustion
included, and the `Run Claude Code Review` step carried no
`continue-on-error` -- so the job failed on that step regardless of what the
guard concluded afterwards.
gha#350 had already made the guard *run* in this case; what it did not do was
stop the step's own failure from deciding the job.
Read a green `fail-check` step alongside a red `claude-review` job as this
shape rather than as a contradiction: the guard's verdict and the job's
conclusion were reached by different steps.
`Resolve final review outcome` is documented as the only step that genuinely
fails the job, and the retry attempt already carried the flag, so attempt 1
was the odd one out.
Note that `outcome` is read *before* `continue-on-error` applies, which is what
lets the retry keep gating on `steps.claude-review.outcome == 'success'`
unchanged.

**Two fixtures pin the gha#550 spawn-denial exclusion, and the pair is the
point rather than either one.**
`spawn-denials-only-retryable.json` carries an 8-spawn fan-out whose denials
are all deliberate: the raw count clears the threshold while the
starvation-relevant count is zero, so it must stay a retryable `stub`.
`spawn-denials-plus-starved-calls.json` carries those same 8 beside 6
genuinely-starved `gh api` calls and must still classify `high-denial`.
Without the second, an exclusion that simply zeroed the count would pass.
Confirmed by mutation rather than assumed: reverting the gate to the raw count
turns the first red and leaves the second green.

`.github/actions/parse-workflow-ref/tests/run-tests.sh` exercises the
extracted `parse-workflow-ref.sh` (see Layout above) offline against a tag, a
branch, and a full-SHA ref; CI runs it as a step in the same
`review-fail-check` job in `_selftest.yml` (gha#191).

`review-fail-check` also runs `run-review-guard` (see Layout above) itself via
a real `uses: ./.github/actions/run-review-guard` step against the
`genuine-finished-review.json` fixture, asserting it produces a non-empty
`review_text_file` output -- and a second such step against a stub fixture,
asserting the `stub_review` output comes back `true`. Unlike the fixture
tests above (which invoke `check-review-execution.sh` directly), these prove
the composite action's `github.action_path`-relative resolution of that
script, and its output passthrough wiring, actually work -- a gap that let
gha#191's `job_workflow_ref` regression (gha#196) go unnoticed: the
sed-parsing logic was unit-tested, but nothing exercised the real `uses:`
call end-to-end. `run-claude-review-attempt` (see Layout above) has no
equivalent selftest coverage -- it wraps a live `anthropics/claude-code-action`
call, which isn't something a selftest job can exercise offline; it's
validated the same way the inline step it replaced always was, by real PR
reviews once merged and released.

`.github/workflows/scripts/tests/run-sum-costs-tests.sh` exercises
`sum-costs.sh` (see Layout above) offline against a table of
`(cost-a, cost-b)` pairs, including both-empty and one-empty cases; CI runs
it as a step in the same `review-fail-check` job. `review-fail-check` also runs
`extract-total-cost` and `sum-costs` themselves via real `uses:` steps (the
same `github.action_path`-resolution proof the `run-review-guard` e2e steps
give), asserting `extract-total-cost` surfaces the right cost for a real
fixture and stays silent for a missing file, and `sum-costs` surfaces the
right total for a real `uses:` call (gha#219 review finding 5).

`.github/workflows/scripts/tests/run-detect-review-request-tests.sh` exercises
`detect-review-request.sh` (see Layout above) offline against a table of
comment bodies: the phrasings that must dispatch a review, the ones that must
not (a quote-reply, an `@claude` request that merely contains the word
"review", `reviewer` as a whole different word), a multi-body call, and
stripper-failure propagation under `set -e` (gha#451).
CI runs it as a step in the `review-fail-check` job, which also calls
`detect-review-request` itself through two real `uses:` steps -- the same
`github.action_path`-resolution proof the `run-review-guard` /
`extract-total-cost` / `sum-costs` e2e steps give, plus the one thing the
offline tests cannot reach: the base64 round-trip on the `bodies-file` path,
built by that job with the same `jq ... | @base64` pipeline `claude.yml` uses.
As with `request-dependabot-review` below, `claude.yml`'s own layer above the
composite is not covered -- it calls the action via `Morrison-Lab/gha/...@v2`,
which does not resolve until `@v2` is advanced past this capability's merge.

`.github/workflows/scripts/tests/run-detect-bot-mention-tests.sh` covers the
quoted-mention gate the same way, and `review-fail-check` also calls
`detect-bot-mention` through two real `uses:` steps -- one quoted mention, one
genuine -- for the same `github.action_path`-resolution proof.
Both directions are asserted deliberately: the only behaviour this gate can
cause is a skip, so the negative case is the bug and the positive case is what
stops the fix from silencing real requests.
Read its `true` rows as the guard rails rather than as filler.

`.github/workflows/scripts/tests/run-mention-filter-tests.py` pins the gha#554
job split that moved that decision out of the agent job.
`_selftest.yml` cannot invoke `claude.yml` (that would be a live agent run),
so the suite reads the workflow YAML and executes the `proceed` step's own
script against a table: a real mention dispatches, a `match=false` quoted /
code-span / fence mention does not start the agent job, and an allowlisted
assignment still dispatches with no mention.
It also asserts the wiring that would silently undo the split --
`claude` needing `mention-filter`, the agent `if:` requiring `proceed ==
'true'` rather than `!= 'false'` (empty output from a skipped filter would
otherwise start the agent for an untrusted commenter), `outputs.proceed`
reading the proceed step rather than `match` (which would kill
assignment-without-mention), the detect step's `if:` omitting
`workflow_dispatch`/`schedule` (four empty bodies print `false`), those two
events still admitted at the job `if:` (gha#245), the trusted-author
association gate living on `mention-filter` now that the agent job's only
`if:` is `proceed`, `ubuntu-latest` rather than `inputs.runs-on`, no caller
checkout, no concurrency group on the filter, and detect-bot-mention living
only in the filter job.
CI runs it as a step in the same `review-fail-check` job.
The composite already exists at `@v2`; this suite pins the *workflow* job
split by reading `claude.yml`, not by invoking it.
`claude.yml@v2` itself picks the split up only when the major tag slides,
the usual reusable-workflow lag, not a new-composite bootstrapping gap.

`.github/workflows/scripts/tests/run-strip-non-invoking-markup-tests.sh`
covers the stripper that matcher now pipes its bodies through, as a table of
`(input, expected output)` pairs rather than of verdicts.
CI runs it as a step in the same `review-fail-check` job in `_selftest.yml`.
It is a separate suite because the stripper has a second consumer coming
(`claude.yml`'s mention gate, gha#342) and because its failure modes run in
both directions: under-stripping dispatches on quoted text, over-stripping
swallows a real request.
So the table pins both, and the cases that matter most are the ones a
verdict-level test cannot distinguish -- an unclosed backtick run left alone,
a shorter run failing to close a longer fence, a dropped block *not* joining
its neighbouring lines.
Three of its cases exist because gha#345's first review round found the
corresponding gaps by hand-tracing the awk against CommonMark: a span whose
delimiters sit on different lines, a 4-space-indented delimiter that must not
close a fence, and an indented code block, which the first draft did not
handle at all.
Each was reproduced end to end through `detect-review-request.sh` before the
fix and again after, since all three were under-stripping -- the direction
that dispatches a review off quoted text.
Their counterweight is the pair of cases asserting that an indented list
continuation and an indented line with no blank line before it are *kept*:
that is the over-stripping direction, which drops a genuine request.
Two of the new cases in the matcher's own table were checked against
`main`'s pre-fix script to confirm they fail there, per the regression-test
rule in
[`Morrison-Lab/ai-config`'s `shared/workflow/ardi.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/ardi.md);
the first draft of the double-backtick case passed pre-fix for an unrelated
reason (trailing prose after the keyword already blocked the match), so it
was rewritten to end the line and re-checked.

`.github/workflows/scripts/tests/run-classify-push-failure-tests.sh` exercises
`classify-push-failure.sh` (see Layout above) offline against a table of push
outputs: the verbatim GitHub App rejection gha#360 was filed over, its PAT and
OAuth App wordings, two non-fast-forward phrasings, and cases that must fall
through to `other` (a protected-branch decline, an auth failure, an empty
log).
It also pins the four-part output contract the composite parses -- `kind=`,
`withhold-patch=`, `headline=`, blank line, advice -- and that the headline
stays a single line, since it reaches an `::error::` annotation.
The composite reads each field by fixed line offset, so a reordering breaks
it silently; that is why the shape is asserted rather than only the values.
The one assertion worth reading as a guard rail rather than filler is that a
generic failure's advice does **not** name `WORKFLOW_TOKEN`: the value of
naming the secret comes entirely from naming it only when it is the cause.
CI runs the suite as a step in the `review-fail-check` job, which also calls
`report-push-failure` itself through four real `uses:` steps with
`dry-run: true` -- one per classified `kind` (`workflows-permission`, a
backtick-free `other` case, `no-push-attempt`, and the `push-protection`
case, whose assertion is that no patch is rendered) -- the same
`github.action_path`-resolution proof the other
e2e steps give, plus the two things the offline table cannot reach: the patch
generated from a live checkout, and the credential redaction.
Those steps run **last** in that job because they commit a throwaway file to
the checkout, which is what gives `git format-patch` a real one-commit range
to render (a merge commit would render as nothing, since `format-patch` skips
merges).
As with `detect-review-request`, `claude.yml`'s own layer above the composite
is not covered -- it calls the action via `Morrison-Lab/gha/...@v2`, which does
not resolve until `@v2` is advanced past this capability's merge.

`.github/workflows/scripts/tests/run-classify-gemini-failure-tests.sh`
exercises `classify-gemini-failure.sh` (see Layout above) offline against a
table of `run-gemini-cli` `error` outputs: a 429/`RESOURCE_EXHAUSTED` quota
blob, a 403/`PERMISSION_DENIED` auth rejection, plain suspended-project and
rate-limit wording with no JSON envelope, and cases that must fall through to
`other` (a malformed-request/`INVALID_ARGUMENT` blob, a network timeout, an
empty error output) -- the last group matters as much as the first, since a
genuine bug swallowed into the graceful-skip path would silently stop failing
the check it should fail. Three more regression fixtures pin the anchoring
fix from gha#380 review finding 1: a stack trace whose line:column number
contains a bare `429` substring, an MCP log line carrying the bare word
`disabled`, and a bare `HTTP 429` status line with no other marker present --
the first two must classify `other` (the pre-fix regex matched either as a
substring), the third must still classify `quota-or-auth` via the anchored
`HTTP`-status-line alternative.
It pins the four-part output contract (`kind=`, `headline=`, blank line,
advice) by fixed line offset, the same reasoning
`run-classify-push-failure-tests.sh` gives, and separately asserts the advice
never embeds the raw error output itself -- that split is deliberate (see
Layout above), so a test asserting the *opposite* would be asserting a
regression.
CI runs this suite as a step in the new `gemini-review-fail-check` job, which
also calls `report-gemini-failure` itself through two real `uses:` steps with
`dry-run: true` -- one quota-or-auth fixture, one genuine (`other`) fixture --
proving `github.action_path` resolution end-to-end, the same proof
`run-review-guard`'s/`report-push-failure`'s own e2e steps give.
Kept as its own job rather than folded into `review-fail-check` above, so a
failure here is attributable at a glance -- the same one-capability-per-job
split `phi-tests`/`new-line-breaks-tests` already use.
As with `report-push-failure`, `gemini.yml`'s/`gemini-code-review.yml`'s own
consumption of this composite via `@v2` is not covered here -- it does not
resolve until `@v2` is advanced past this capability's merge.

`.github/workflows/scripts/tests/run-compose-review-failure-report-tests.sh`
exercises `compose-review-failure-report.sh` (see Layout above) offline.
The script emits prose, and asserting prose word-for-word produces a suite that
fails on every wording change while catching nothing, so the table asserts two
things only: the four-part output contract by fixed line offset (the same
reasoning `run-classify-push-failure-tests.sh` gives for its own), and the
claims a reader would act on -- which kind was chosen, and whether the
denied-tool line says names, none, or not recorded.
The denied-tools trio is the group to keep if the suite is ever trimmed, and
its middle case is the trap: an empty denial count must not render as "none",
since that asserts something about permissions on a run that never measured
them.
Seven mutations were confirmed to turn it red rather than assumed to --
collapsing "not recorded" into "none", dropping the contract's blank line,
restoring the duplicated `5` default, accepting any kind verbatim, giving two
kinds the same headline, printing the 999999 sentinel as a count, and `eval`-ing
the denied-command text instead of rendering it verbatim.
That last one is pinned by a single POSITIVE assertion.
A negative counterpart was written and removed: a needle naming the substituted
result is either the bare username, which may legitimately appear elsewhere in
a report, or a marker string no version of the script can emit -- and the
marker form passes under every mutation, which is the same vacuous shape this
file records two paragraphs down for `must_not_log`.
CI runs it as the `review-failure-report` job in `_selftest.yml`, kept separate
from `review-fail-check` so a failure is attributable at a glance -- the same
one-capability-per-job split `phi-tests` and `gemini-review-fail-check` use.
That job also calls `report-review-failure` through two real `uses:` steps with
`dry-run: true`, for the `github.action_path`-resolution proof the other
composite e2e steps give plus the one thing the offline table cannot reach,
since it calls the script directly and so cannot see whether `action.yml` wires
its inputs through at all.
The second of those two steps is not a duplicate of the first: it pins
normalization, the only judgment the composite makes for itself.
As with `report-push-failure`, `claude-code-review.yml`'s own consumption of
this composite via `@v2` is not covered here -- it does not resolve until `@v2`
is advanced past this capability's merge.

`run-fixture-tests.sh` gained three assertions alongside it, and the last two
are the ones worth reading.
`failure_kind` is asserted for **every** fixture rather than only the failing
ones, because a stale kind left on a clean run is what would let the comment
describe a failure that did not happen; the exit code and `stub_review` are
identical across `hard-error`, `no-output`, and `high-denial`, so nothing else
in that suite can tell those three apart.
`max_denials` is asserted as an **invariant** instead of per fixture -- it is
written immediately after `denials`, unconditionally, so the two must always
co-occur.
Keying on that relationship rather than on a table means a fixture added later
cannot forget to declare it, and it pins the value, so a caller reading an
empty output and silently falling back to a hard-coded `5` is caught here
rather than on a live review.
The first draft asserted `failure_kind` alone, and dropping the `max_denials`
write was confirmed to pass under it -- an unasserted new output is exactly
what regresses in silence.

`assert_denied_tools_presence` is the third, and it pins a contract that had
been asserted only in prose, and asserted wrongly: `run-review-guard`'s docs
claimed `denied_tools` was set on every exit path, which is false for the two
short-circuit exits that return before the denial count exists.
It asserts presence rather than content -- the value is legitimately empty on
a zero-denial run, so `denied_tools` must be present exactly when `denials` is,
and writing it on the short-circuit path turns the suite red.
The distinction it protects reaches the PR comment: an ABSENT value means
"never counted", an EMPTY-but-present one means "counted, and there were none",
and only the second licenses saying the reviewer was not blocked by
permissions.

`.github/workflows/scripts/tests/run-trigger-bugbot-review-tests.sh`
exercises `trigger-bugbot-review.sh` (see Layout above) offline against a
stub `curl`: a successful queue, `DRY_RUN=true` in the JSON body, HTTP 400
when Bugbot is disabled for the repo, HTTP 401, a curl transport failure,
a 2xx body with `"outcome":"error"`, and missing `CURSOR_API_KEY` /
`PR_URL`.
The stub is the coverage that matters, because `_selftest.yml` cannot call
`api.cursor.com` and a live queue would bill.
Two of its cases are the ones to keep if the suite is ever trimmed
(gha#511):
a `"dry_run":false` API body must win over a local `DRY_RUN=true`,
and the stub's captured argv must not contain `Authorization` or the
raw key -- the `--header` form put the base64 credential on argv even
though the comments claimed otherwise.
CI runs the suite as the `cursor-review-check` job, which also calls
`trigger-bugbot-review` through a real `uses:` step with that same stub on
`CURL_BIN`, proving `github.action_path` resolution.
`cursor-code-review.yml`'s own consumption of the composite via `@v2` is
not covered here -- it does not resolve until `@v2` is advanced past this
capability's merge.

`.github/workflows/scripts/tests/run-classify-review-delivery-tests.sh`
exercises `classify-review-delivery.sh` (gha#362) offline against a table of
comment bodies.
That script decides whether a dispatched review actually produced a verdict,
because a run CONCLUSION of `success` is not the same as "produced a verdict"
-- `claude-code-review.yml` deliberately succeeds on a graceful quota skip
(gha#520) and surfaces the skip through a comment, so the run-level conclusion
cannot see the commonest runtime failure there is.
**It tests for FAILURE markers rather than for a positive verdict, and that
direction is the design rather than caution.**
Requiring each agent's success marker means a wrong pattern makes every review
by that agent fall through to a second agent, which costs a duplicate paid
review and, on workflows sharing a per-PR `cancel-in-progress` group, can
cancel the review it was checking.
The failure direction degrades to today's accept-on-success behaviour instead.
It is also complete for the two agents that emit markers, which is what makes
the safe direction the correct one: gha#548 made every no-verdict path in
`claude-code-review.yml` post a failure comment, and `report-gemini-failure`
(gha#379) does the equivalent, so "no failure marker" and "produced a verdict"
coincide there.
The case to keep if the suite is ever trimmed is the discriminating negative:
a failure marker on a **different** run must not decide this one.
Without it, scoping the match to comments naming this run could be dropped and
every other case would still pass.
Four mutations were confirmed to turn the suite red rather than assumed to --
dropping the run-URL scoping, collapsing the two `delivered=true` reasons into
one, deleting a marker from the table, and dropping the self-mod marker
specifically.
**That last marker is the one the list most easily omits**, and #571's review
caught it missing: the `self_mod` and dispatch-guard skips report a job conclusion
of `success` with every post-guard step `skipped`, so nothing about them looks like
a failure, and their skip notices carry the run URL without matching failure wording.
The pre-fix classification was `delivered=true reason=no-failure-marker`, which
is the green-check-no-verdict case the capability exists to close.
`gemini-code-review.yml`'s dispatch guard posts a skip notice on fork/Dependabot
PRs so delivery classification matches it as well (gha#573).
CI runs the suite as the `review-delivery` job in `_selftest.yml`, which also
calls `install-gha-scripts` through two real `uses: ./...` steps: one
installing the classifier and running it on a marker body, for the
`github.action_path`-resolution proof the other composite e2e steps give, and
one asserting a path-bearing filename is refused.
`ai-code-review.yml` does not call any of this yet -- a new composite cannot
gain its first `@v2` caller in the PR that introduces it, so the wiring waits
on the tag slide and is tracked in gha#569.

`.github/workflows/scripts/tests/run-save-pr-diff-tests.sh` exercises
`save-pr-diff.sh` offline against stubbed `gh` outcomes, asserting successful diff
saving, empty diff handling, command failure, and partial output cleanup;
mutation tests verify `rm -f` and non-empty `-s` checks are load-bearing.
CI runs it as the `save-pr-diff` job in `_selftest.yml`, calling the
`.github/actions/save-pr-diff` composite action through a real `uses:` step
and asserting a non-empty saved diff path (gha#568).

`.github/workflows/scripts/tests/run-resolve-major-tag-tests.sh` exercises
`resolve-major-tag.sh` (see Layout above) offline against throwaway git repos;
`.github/workflows/scripts/tests/run-check-tag-drift-tests.sh` exercises
`check-tag-drift.sh` (see Layout above) offline against throwaway git repos,
asserting zero-drift, N-commit-drift, no-semver-tag, and missing-major-tag behavior;
CI runs both in the `tag-drift` job of `_selftest.yml`.

`.github/workflows/scripts/tests/run-build-reviewer-args-tests.sh` exercises
`build-reviewer-args.sh` (see Layout above) offline against a table of
reviewer-list inputs, including comma-only, whitespace-padded, and
doubled-comma cases; CI runs it as a step in the `dependabot-review` job.
That job also runs `build-reviewer-args` itself via a real `uses:` step (the
same `github.action_path`-resolution proof the `run-review-guard` /
`extract-total-cost` / `sum-costs` e2e steps above give), asserting it
surfaces the correctly trimmed and split JSON array for a real call. Unlike
those other e2e steps, this one can't also exercise
`request-dependabot-review.yml`'s own reusable-workflow layer end-to-end yet:
that workflow calls `build-reviewer-args` via `Morrison-Lab/gha/...@v2`, which
won't resolve until `@v2` is advanced past this capability's merge (the same
`test-coverage` bootstrapping gap the Layout section's `_selftest.yml`/
local-ref paragraph describes) -- so `dependabot-review` tests the composite
directly, the same
"local composite, not the full reusable-workflow chain" precedent `coverage`
below uses for `test-coverage.yml` (gha#253 review: missing selftest coverage
for a new workflow with real side effects, precedented by the `sync-pr` job's
`open-sync-pr` no-op test).

`.github/workflows/scripts/tests/run-select-existing-issue-tests.sh` exercises
`select-existing-issue.sh` (see Layout above) offline against a table of
`(title, open-issues)` pairs, including the no-match, prefix-is-not-a-match,
case-sensitivity, and already-duplicated cases;
`run-split-csv-list-tests.sh` does the same for `split-csv-list.sh`, covering
the space-after-comma case that motivated it and asserting that a label's
internal spaces survive trimming (`good first issue` is a real label). CI runs
both in the `failure-issue` job of `_selftest.yml`. That job also calls
`open-failure-issue` itself through a real `uses:` step with `dry-run: true`
-- the same `github.action_path`-resolution proof the `run-review-guard` /
`build-reviewer-args` e2e steps give, and the reason `dry-run` exists at all:
without it the only end-to-end call would file an issue on this repo every
selftest run. As with `request-dependabot-review`, the `report-failure.yml`
reusable-workflow layer above the composite is not covered -- it calls the
action via `Morrison-Lab/gha/...@v2`, which does not resolve until `@v2` is
advanced past this capability's merge -- so the job tests the composite
directly, the same "local composite, not the full reusable-workflow chain"
precedent `coverage` and `dependabot-review` use.

`.github/workflows/scripts/tests/test-description-version.R` exercises
`description-version.R`'s `read_version`/`versions_equal`/`bump_dev_version`
functions offline against 15 cases, including the 3-vs-4-component version
boundary (a freshly-cut release starts its next dev cycle at `.9000` rather
than bumping a 4th component that doesn't exist yet) and the `.9999` ->
`.10000` carry, mutation-verified against a deliberately broken bump rule so
the suite is confirmed to actually catch a regression rather than pass
vacuously. CI runs it, plus real `uses:` calls to both `bump-dev-version` and
`check-dev-version` with `dry-run: true`, as the `dev-version` job in
`_selftest.yml` -- the same `github.action_path`-resolution proof the other
composite e2e steps above give, and asserting `check-dev-version`'s outcome
differs between a matching and a mismatched `DESCRIPTION` pair (the
`check-equation-renders` precedent for a pass/fail composite). Neither
reusable workflow's own `@v2` composite reference resolves pre-merge (the
bootstrapping gap `dependabot-review`/`open-failure-issue` above hit too),
and `bump-dev-version.yml`'s real run is a write side effect selftest can't
exercise, matching `sync-pr`'s own no-op-only precedent -- so this job
covers the composites directly rather than the reusable workflows as a
whole, which is exactly the gap gha#390's own review found in
`version-check.yml` (a checkout resolving against the *calling* repo rather
than gha's own; see Layout above).

`.github/actions/inject-canonical-urls/tests/test_inject_canonical_urls.py`
covers the canonical injector (see Layout above) offline, generating its HTML
fixtures into `tmp_path` rather than committing them -- committed HTML under a
tests directory gets swept into the `bib` and `phi` jobs' repo-wide scans, the
same trap the `test-coverage` R-package fixture records below.
CI runs it as the `canonical-urls` job in `_selftest.yml`, kept separate from
`altdoc-docs` so a failure is attributable at a glance.
That job also calls the composite through two real `uses: ./...` steps -- one
release-style, one preview-style -- the `github.action_path`-resolution proof
`run-review-guard`'s own e2e steps give, and the one thing the unit tests
cannot reach, since they call the script directly and so cannot see whether
`action.yml` wires its inputs through at all.
Six mutations were confirmed to turn the suite red, and the first is the one to
keep if it is ever trimmed: making the canonical always point at `/latest-tag/`
regardless of whether the page exists there.
That is the issue's own open decision point, and the failure it produces is
silent -- a canonical to a 404 looks fine in the generated HTML and is only
wrong at the indexer.
The others cover dropping the `404.html` exclusion, dropping the
already-tagged skip, canonicalizing a preview instead of marking it `noindex`,
dropping the base-URL trailing-slash normalization, and dropping the `https://`
guard.

The `altdoc-docs` job in `_selftest.yml` exercises
`generate-altdoc-version-dropdown`, `generate-altdoc-landing-page`, and
`resolve-altdoc-base-url` (see Layout above) directly against a throwaway
fixture: a separate git-init'd
package directory (not this checkout) with two release tags, asserting the
composite picks the correct latest/previous tags and dev version and rewrites
the navbar "Versions" block and root-redirect HTML correctly.

It calls `generate-altdoc-version-dropdown` four times, over three fixtures.
Twice over the one above: first with no `current-version`, covering the
inference path and the dev-build labeling, then with
`current-version: v0.1.0`, covering an explicit release build. That second
call also proves two things only a re-run can: that the generated-by marker
keeps the block findable after the first run replaced its
`- text: Versions` anchor, and that the navbar badge is replaced rather than
stacked.

The third call uses a **clone** of that fixture, whose own `DESCRIPTION`
is bumped to `0.2.0.9000` while `origin/main` still holds `0.1.0.9000`. That
is the only way to pin the PR-preview divergence described in the Layout
section above -- the menu's label and badge naming the branch's version while
the `/dev/` entry names the default branch's. A unit test cannot reach it:
`resolve_current_version()` takes one version, and the split between
`local_version` and `dev_version` lives in `generate_version_dropdown.py`
itself (gha#308 review). `navbar_version.py`'s own pytest suite
(`generate-altdoc-version-dropdown/tests/test_navbar_version.py`) covers the
label resolution and YAML rewriting offline; the job runs it alongside
`generate-altdoc-landing-page`'s.

A fourth call, over a fresh clone of the same fixture, pins the
`release-tags` input (gha#287): passed `v9.9.9` (a tag the fixture repo was
never actually tagged with, alongside its real `v0.1.0`), the composite must
use that list as-is rather than falling back to its own `gh api`/`git tag`
discovery, so `latest-tag` comes back `v9.9.9`.
This is what proves the `release-tags` passthrough is load-bearing rather
than a no-op default: every other call in this job leaves `release-tags`
empty and no `github-token`, so it exercises the composite's own `git tag`
fallback instead -- a different mechanism from `altdoc-multiversion-docs.yml`'s
"Determine latest stable release tag" step, which only ever calls `gh api`
with no `git tag` fallback of its own.
On the production path (the real workflow calling the real composite) only
the workflow step's `gh api` call ever runs; the composite's own discovery,
in either form, never fires there once `release-tags` is set.

The same job also covers the `legacy-paths` 404 redirect at three levels:
`generate-altdoc-landing-page/tests/test_legacy_redirects.py` (pytest, the
`old=new` parsing and its fail-fast validation), a real `uses:` call to the
composite with `legacy-paths` set, and
`generate-altdoc-landing-page/tests/run-redirect-js-tests.mjs`, which
*executes* the generated page's redirect script under node with a stubbed
`window` against a table of request paths. That last one exists because the
Python tests can only assert the mapping reaches the page as text -- whether
a given request then lands in the right place is a separate question, and
getting it wrong is silent (a bad redirect still renders a plausible
not-found page). Its table includes the paths that must *not* redirect: a
genuinely missing page under `/dev/` would otherwise bounce forever.

It does not
exercise the full `altdoc-multiversion-docs.yml` reusable workflow end-to-end
(the render + multi-target `gh-pages` deploy is a real write side effect
selftest can't run); that layer is validated by real consumer usage once
merged and released, the same precedent `dependabot-review`'s
reusable-workflow layer follows just above.

## GitHub access in remote / web sessions

Claude Code on the web (and other remote/CI sessions) runs in a sandbox where the
`gh` and `glab` CLIs are **not installed** and there is no direct GitHub API
access. Skills and built-in commands that tell you to "use `gh`" --
`/review`,

`/code-review --comment`, `/security-review`, `/verify`, PR babysitting, PR
creation -- only work if their GitHub steps are translated to the GitHub MCP tools
(`mcp__github__*`). When a skill or command instructs a `gh`/`glab` command in
such a session, substitute the equivalent MCP tool below. (In a local session
where `gh` is on `PATH`, use `gh` as the skill describes.)

This repo is `Morrison-Lab/gha` (moved there from `d-morrison/gha`), so MCP
calls use `owner: Morrison-Lab`, `repo: gha`.

**Use whichever owner the session was scoped with, not whichever one is
current.** A session's GitHub access is pinned to the repository name it was
started with, and the two names are not interchangeable at the tool layer even
though they are the same repository:

- A session scoped to the old `d-morrison/gha` keeps working, because the API
  follows the transfer redirect server-side. Passing `owner: Morrison-Lab` to
  that session fails with `Access denied: repository "morrison-lab/gha" is not
  configured for this session`, and `add_repo` cannot rescue it -- it refuses
  the cross-owner add outright.
- Some endpoints return `301 Moved Permanently` to the old name rather than
  following it, so a call can fail on the redirect alone. If one does, the
  answer is usually a different route to the same fact, not a different owner
  string.

So read the allowed-repositories list in the session's own context before
assuming an owner, and if the scoped name is the old one, keep using it.

**A Cursor Cloud Agent's `@claude review` / `/review` comment is not a
human collaborator comment.**
It posts as `cursor[bot]` with `author_association: NONE`, so the default
OWNER/MEMBER/COLLABORATOR gate skips the run (the workflow may still wake
and report every job `skipped`).
This repo's dogfood callers admit `cursor[bot]` on the caller-side `if:`;
`claude.yml`'s `trusted-bot-logins` input is the matching reusable-workflow
allowlist (default `[]`).
Until `@v2` carries that input, do not pass it in `with:` -- an unknown
`workflow_call` input fails the job at the call gate for every mention.
Prefer `/review` from `cursor[bot]` once `claude-review.yml` on `main`
admits that login: that path is entirely in the caller and does not wait
on a tag slide.
A human OWNER/MEMBER/COLLABORATOR `/review` or `@claude review` remains
the reliable workaround on any older pin.

**Some of these sessions have no local git checkout at all** (not just a missing
`gh` CLI) -- there is no working tree to run `git commit`/`git push` against, so
every change (branch, file edit, PR) must go through the MCP write tools below.
Editing a file means: `mcp__github__get_file_contents` first to get its current
blob `sha` (required on every update, not just the first -- re-fetch it after
each write since it changes on every commit), then
`mcp__github__create_or_update_file` with the **full** new file content (it
replaces the whole file, there is no patch/diff mode) and that `sha`. A stale
`sha` (from before another commit landed) fails the write -- re-fetch and retry
rather than guessing.

| Operation / `gh`/`glab` command | GitHub MCP equivalent |
| --- | --- |
| `gh pr list` | `mcp__github__list_pull_requests` |
| `gh pr view <n>` | `mcp__github__pull_request_read` (`method: get`) |
| `gh pr diff <n>` | `mcp__github__pull_request_read` (`method: get_diff`) |
| changed files in a PR | `mcp__github__pull_request_read` (`method: get_files`) |
| `gh pr status` / `gh pr checks` | `mcp__github__pull_request_read` (`method: get_status` / `get_check_runs`) |
| `gh pr create` | `mcp__github__create_pull_request` |
| read PR conversation comments | `mcp__github__pull_request_read` (`method: get_comments`) |
| read inline review comments | `mcp__github__pull_request_read` (`method: get_review_comments`) -- also returns `threadId`s |
| post a top-level PR comment | `mcp__github__add_issue_comment` |
| post inline review comments | `mcp__github__pull_request_review_write` (`method: create`, no `event`) → `mcp__github__add_comment_to_pending_review` per comment → `mcp__github__pull_request_review_write` (`method: submit_pending`) |
| reply to a review comment | `mcp__github__add_reply_to_pull_request_comment` |
| approve / request changes | `mcp__github__pull_request_review_write` (`method: create` with `event`) |
| resolve a review thread | `mcp__github__pull_request_review_write` (`method: resolve_thread`, `threadId: <id from get_review_comments>`) |
| `gh issue list` / `gh issue view <n>` | `mcp__github__list_issues` / `mcp__github__issue_read` |
| read a file / repo contents | `mcp__github__get_file_contents` |
| create/edit a file (no local checkout) | `mcp__github__create_or_update_file` -- needs the target branch, full new file content, and the file's current blob `sha` (from `get_file_contents`) if it already exists |
| create a branch (no local checkout) | `mcp__github__create_branch` |
| CI runs & job logs | `mcp__github__actions_list`, `mcp__github__actions_get`, `mcp__github__get_job_logs` |
| watch / stop watching PR activity | `mcp__github__subscribe_pr_activity` / `mcp__github__unsubscribe_pr_activity` |
| `glab mr ...` (GitLab) | N/A -- this repo is on GitHub; use the tools above |

Posting inline comments requires a **pending review to already exist** before
`mcp__github__add_comment_to_pending_review`; create the pending review first, add
each comment, then submit once at the end. Watch and respond to PR activity with
`mcp__github__subscribe_pr_activity` / `mcp__github__unsubscribe_pr_activity` (not
`gh pr checks --watch`).

### Reading repos outside the session's MCP scope

A task often needs files from a *sibling* repo (e.g. `d-morrison/qwt`) that the
session's GitHub MCP tools aren't scoped to -- those calls fail with
`Access denied: repository … is not configured for this session`. **Don't report
the repo as inaccessible from that alone.** First try the raw HTTP URL directly:
any **public** repo's files are fetchable with `curl` (or `WebFetch`) at
`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>`, which works
even when `gh` and the MCP tools don't. (This is how qwt's standalone workflows
were obtained to port them faithfully into the reusable workflows for #44/#45.)
Only fall back to "can't access it" -- or to whatever session tooling can add a
repo to scope, if any -- after the raw fetch also fails (private repo, or the
network policy blocks the host).

**A 403 from a *rendered* docs site is not the same as the content being
inaccessible.** A GitHub Pages / Quarto-rendered site (e.g.
`ucd-serg.github.io/lab-manual/coding-style.html`) can reject `WebFetch` (for
reasons unclear -- possibly anti-scraping) even though the *source* file it
was built from is a plain file in a public repo. Don't conclude the content is
unreachable -- find the source path (often the same repo, e.g.
`coding-style.qmd` for `coding-style.html`, sometimes with `_`-prefixed
included fragments) and raw-fetch that instead using the same
`<path>`-includes-its-extension template above, e.g.
`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/coding-style.qmd`.
(Confirmed this way that `ettbc`'s `.lintr.R` predates
`UCD-SERG/lab-manual`'s move to a shared `lms` linter package (source:
[`UCD-SERG/lab-manual/.lintr.R`](https://github.com/UCD-SERG/lab-manual/blob/main/.lintr.R),
which calls `lms::default_linters()` from a package defined in that repo's own
`lms/` subdirectory) -- the manual's own docs page 403'd, but its `.qmd`
source and the referenced `.lintr.R` file both fetched cleanly.)

## A canceled review skips require-review gracefully (gha#585)

`claude-code-review.yml`'s `claude-review` job is concurrency-grouped per PR
(`claude-review-<PR>`, `cancel-in-progress: true`) across BOTH the automatic
`pull_request`-triggered review and claude.yml's comment-triggered (`@claude
review`) re-dispatch. When a push and an `@claude review` comment land close
together -- or claude.yml's agent run finishes and re-dispatches a review a
minute or two later, landing on top of the next push's auto-review -- the two
reviews race and one cancels the other.

The `require-review` gate job treats a cancelled run as a graceful skip
rather than an outright failure (gha#585), allowing surviving and subsequent
reviews to proceed cleanly without leaving a false-negative red check on
superseded runs.
To avoid causing unnecessary cancellations: don't post
`@claude review` immediately after pushing a commit on a PR using this
workflow; let the automatic review run alone, or wait for any in-flight
dispatched review to finish first. (See the `claude-review` job's
`concurrency:` comment in `.github/workflows/claude-code-review.yml` for the
full mechanism.)

**The same race fires from two plain pushes close together, not just a push
plus an `@claude review` comment.** Pushing two commits back-to-back (e.g. a
code fix, then a small follow-up doc/memory commit) triggers two separate
`pull_request`-type review runs; the second cancels the first via the same
concurrency group. Don't chase this either --
and don't bother "fixing" the

workflow to prevent it: `cancel-in-progress` on a stale commit's review is
the *correct*, intended behavior (only the latest commit's review matters,
and canceling a stale run saves CI time), not a defect. A debounce to
coalesce rapid pushes would trade away review latency on every normal
single-push PR just to suppress a cosmetic, self-resolving non-issue on the
rare double-push. The fix is behavioral: batch closely-related changes into
one commit/push instead of two in quick succession.

**Until `@v2` picks up gha#342's gate, you cannot even *quote* the mention
safely, and that interacts badly with the paragraph above.**
`claude-bot.yml` gates on `contains(body, '@claude')`, so a comment writing
the mention inside backticks -- exactly what explaining any of this requires
-- spawns an agent run, which re-dispatches a review, which cancels the review
already in flight.
The natural response to a red `require-review` is a comment explaining why it
is red, and that comment fires it again.
So while writing about the bot on an issue or PR, defang the string the way
gha#342's own body does.
Once the gate ships and the tag advances, a quoted mention stands down on its
own and the mitigation can be dropped.

**Cheap self-check before investigating a post-push `require-review`/`claude-review` failure:**
compare the failing check's commit SHA against the PR's *current* head SHA
(`pull_request_read` method `get`, its `head.sha` field). If they don't
match, the event is almost certainly this exact race on a now-superseded
commit -- skip straight to "wait for the head commit's review" instead of
spending a tool call fetching the workflow run to confirm `cancelled` vs
`failure`. This shortcut is scoped to the two jobs that actually run under
`cancel-in-progress: true` (`claude-review`/`preview`) -- `_selftest.yml`'s
jobs (`check-links`, `phi-tests`, `bib`, `coverage`, `review-fail-check`,
etc.) have no `concurrency:` block, so a `failure` there on a non-head SHA
is a real result the reader hasn't re-checked yet, not this race; don't
apply the shortcut outside `claude-review`/`require-review`/`preview`.
(`Lacaedemon/sparta` PR #780, 2026-07-12: two pushes 3 minutes apart
triggered exactly this on `require-review`; confirmed via `actions_get`
`get_workflow_run` that the failing check's conclusion was `cancelled` on
the non-head SHA, matching this pattern.)

## Green `require-review` is not fully clean - read the review comment body

**Fully clean** (the bar for standing `mwc` merge and for ARDI/GII session
summaries) requires **both** green CI **and** a substantive clean review on
the PR's **current head SHA** - see
[`Morrison-Lab/ai-config`'s `shared/workflow/fully-clean.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/fully-clean.md).
Green `review / claude-review` plus green `review / require-review` satisfies
criterion 1's review *job* half only.
It is **not** sufficient for criterion 2.

**Before declaring a PR clean, zero findings, or ready to merge**, fetch and
read the latest `@claude` review comment on the thread and confirm all of
the following:

1. **The comment's `created_at` brackets inside the review job that ran on
   the current head commit.**
   Use `created_at`, not `updated_at`.
   Later rounds fold earlier verdict comments and advance `updated_at`
   without editing their bodies; see
   [`review-verdict-pitfalls.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/review-verdict-pitfalls.md)).

2. **The body contains a real `### Verdict` (or `Verdict:`) line** naming
   approval.
   It must not be a stub, a quota skip, or a self-mod skip.

3. **The verdict is not a deferral or refusal.**
   Any of these mean the PR was **not reviewed** and is **not clean**,
   even when both review checks are green:

   - `Deferred - author requested reviewers hold off`
   - `honoring that request and stopping here without conducting`
   - `without conducting the review`
   - No verdict section at all (stub review - gha#185)

4. **Read to the end of the comment and count findings under every heading.**
   Criterion 2's test is the **absence of findings**, not the presence of a
   positive verdict line - a "Ready" verdict above a findings list loses to
   the findings.
   Zero **inline** review threads is not a substitute.
   Deferrals and stubs often post as **top-level** comments only.

**Session-lock claim comments are not a reason to skip review or call a PR
clean.**
Comments such as `Driving this PR to clean - back off until done` or
`paws off until I'm done` (from the `claim-pr` / `ardi` rituals) tell **other
write sessions** not to push in parallel.
They do **not** instruct automated review to stand down.
They do **not** mean a review already ran.
An agent that posted such a claim and then saw green review checks must still
read the review body.
Mistaking the claim for "don't review" produced gha#527:
PR 527 was declared clean with zero findings while the bot posted only
`Deferred - author requested reviewers hold off` and never reviewed the diff.
PR #528 hardens the reviewer prompt and fails that deferral pattern in
`check-review-execution.sh`.
This paragraph is the matching guardrail for **agent sessions** driving
ARDI/GII loops in this repo.

**Cheap self-check before marking ✅ Clean in a GII summary or invoking
`mwc`:**

```bash
HEAD=$(gh pr view <N> --json headRefOid --jq .headRefOid)
REPO=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
REVIEW_OK=$(gh api "repos/$REPO/commits/$HEAD/check-runs" --paginate \
  --jq '[.check_runs[] | select(.name == "review / claude-review" and .conclusion == "success")] | length')
gh pr view <N> --json comments --jq --arg head "$HEAD" --argjson reviewOk "$REVIEW_OK" '
  if ($reviewOk | tonumber) == 0 then empty
  else
    [.comments[]
     | select(.author.login | test("claude|github-actions"; "i"))
     | select(.body | test("### Verdict|Verdict:"))
     | select(.body | test("Deferred.*hold off|without conducting the review"; "i") | not)
    ] | last | {createdAt, bodyPreview: (.body[:200]), head: $head}
  end'
```

`REVIEW_OK` is zero when no successful `review / claude-review` check ran on
the current head commit, so an empty result means **not clean** even if an
older verdict comment exists on the thread.
An empty `last` or a body matching the deferral patterns above also means **not
clean**.
Re-trigger review (`@claude review` after the in-flight run finishes, or a
no-op push) and read the new comment before merging or advancing the loop.

## A PR fixing claude-code-review.yml (or claude.yml) itself can't self-verify before merge

This repo's own dogfood workflow (`.github/workflows/claude-review.yml`)
calls `Morrison-Lab/gha/.github/workflows/claude-code-review.yml@v2` -- the
**released, floating tag**, not a local `./` ref (unlike `_selftest.yml`'s
handling of brand-new pre-release capabilities; see "About this repo" above).
`.github/workflows/claude-bot.yml` similarly calls
`Morrison-Lab/gha/.github/workflows/claude.yml@v2`. `@v2` only advances to
include a fix once that fix's PR merges to `main` and `slide-major-tag.yml`
runs.

So a PR that fixes a bug **in** either reusable workflow cannot exercise its
own fix via this repo's automatic review or agent dispatch -- every review
(or agent re-dispatch) of that PR runs the **pre-fix** version, and will keep
hitting the exact bug being fixed until after merge. Seeing `review /
claude-review` or `review / require-review` fail on such a PR with the bug's
own signature is expected, not a regression in the diff; don't debug the new
code as the cause. The current workaround is to re-trigger the review (push,
or `@claude review` -- see the race-avoidance note above) as many times as
needed, or just proceed to merge on the strength of a manual/offline review
once CI's other jobs and a careful read of the diff are clean. (Hit on
gha#201, whose diff fixed `claude-code-review.yml`'s stub-review bug
directly: every review of the PR itself failed with that exact signature --
`is_error:false`, a low `permission_denials_count`, no verdict -- right up
until merge. gha#202 (a different fix, allowlisting `WebFetch`/`Bash(curl:*)`)
hit the identical signature as a bystander while it still edited
`claude-code-review.yml`'s inline `claude_args` block directly, before a
rebase onto #201 relocated that edit into the new `run-claude-review-attempt`
composite action -- confirmed via that run's own execution output:
`permission_denials_count:1`, no verdict. Once `@v2` picked up #201's fix,
both PRs' subsequent reviews went clean.

The `claude.yml` side of this hit on gha#286, fixing gha#285's
`gh workflow run`-without-`--ref` bug: a plain `@claude review` comment on
PR #286 dispatched through `claude-bot.yml`'s `claude.yml@v2` -- the
released, pre-fix tag -- and reproduced the exact #285 symptom live
(the re-dispatched review's check-run landed on `main`'s SHA, not the PR's
head) even though the fix had already been pushed to the PR branch itself.
Not a regression; the same "can't self-verify" gap, one layer up.)

## Re-running *failed jobs* cannot verify a tag slide

The section above ends at the merge; this one covers the step after it.
Once `slide-major-tag.yml` moves `v2`, the obvious way to confirm the fix
reached consumers is to re-run the run that failed.
Which re-run you pick decides whether that works, and the wrong one fails in
a way that looks like the fix itself is broken.

GitHub resolves a `uses:` reusable-workflow reference when the run is first
created and records the resolved commit in the run's `referenced_workflows`.
Whether a re-run reuses that record depends on the mode, per
[GitHub's own docs](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)
("Behavior of reusable workflows when re-running jobs"):

> - Re-running all jobs in a workflow will use the reusable workflow from the
>   specified reference.
> - Re-running failed jobs or a specific job in a workflow will use the
>   reusable workflow from the same commit SHA of the first attempt.

So **Re-run failed jobs**, **Re-run this job**, and their programmatic
equivalents all replay the pre-slide workflow, however long ago the tag
moved.
**Re-run all jobs** re-resolves the reference and does pick the slide up.
The failed-jobs call is spelled differently on every surface, so none of
these is *the* name for it: REST is
`POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun-failed-jobs`, the CLI
is `gh run rerun --failed`, and the GitHub MCP server's
`actions_run_trigger` takes `method: rerun_failed_jobs`.
Note the docs' own precondition: this only applies where the reference is a
tag or branch rather than a SHA, which is exactly how consumers pin `@v2`.

What makes the stale mode deceptive is that the two layers behave
differently within it.
Composite actions nested *inside* the reusable workflow
(`uses: Morrison-Lab/gha/.github/actions/...@v2`) resolve at
job-preparation time, so those **do** come back at the new tag even on a
failed-jobs re-run.
That mixes new-version composites with the old reusable workflow's logic,
inputs, and defaults -- which reads as "the fix is live and didn't work"
rather than "the fix isn't live".
It also means such a re-run *can* surface a slide whose only substantive
change lives in a composite, so what a failed-jobs re-run cannot verify is
specifically a change to the reusable workflow's own content.

Decide it mechanically instead of inferring it from step output: read
`referenced_workflows[].sha` on the run (`actions_get` `get_workflow_run`)
and compare it against the tag's current commit.

**Read that tag's commit with `git ls-remote`, and do not try to read it off a
plain `git fetch --tags`.**
Sliding a major tag force-moves it, and a plain `git fetch --tags` will not
move an existing local tag, so the one operation this section exists to verify
is the one it cannot perform.

git does say so.
Measured on git 2.43.0 against this repo's own slid `v2`, a plain
`git fetch origin --tags` printed
`! [rejected]        v2         -> v2  (would clobber existing tag)`
on stderr and exited 1.

Both signals are easy to lose, though, and the habits that lose them are
ordinary ones.
`-q` suppresses the message.
Piping the combined output through `tail` can drop it as well, since git prints
ref-update lines in refname order and a slide follows cutting a `vX.Y.Z` that
sorts after `v2`.
And a pipeline reports `tail`'s exit status rather than the fetch's, so `&&`
guards nothing once a pipe is involved.
Measured on a throwaway remote carrying a rejected `v2` beside a newly created
`v2.6.0`:

```text
$ git fetch origin --tags 2>&1 | tail -1 && git rev-parse 'v2^{}'
 * [new tag]         v2.6.0     -> v2.6.0
3dbbb1e95f5026c06799e548b05b820df0573581     # stale, and the chain did not stop
```

So do not reason about which invocation preserves the warning.
Read the tag directly, or force the local update:

```bash
# Ask for both refspecs and take the ^{} line when there is one: an ANNOTATED
# tag's bare line is the tag object's sha rather than the commit. See
# ai-config's memories/git-tags.md. slide-major-tag.yml writes lightweight
# tags, so both forms agree for v1/v2 today.
git ls-remote origin 'refs/tags/v2' 'refs/tags/v2^{}'
git fetch origin --tags --force        # when the local checkout must be updated
```

Comparing two API-derived values sidesteps the question entirely, since
`referenced_workflows[].sha` has no local-staleness failure mode.
(Measured 2026-08-19, minutes after #521 merged and `v2` slid to `3ec11c0`:
`git rev-parse 'v2^{}'` after a `-q` fetch returned the previous `3b09703`,
and that stale read was reported twice as
"the fix has not reached consumers" while `d-morrison/rme` run 32298939967 was
demonstrating the fix working -- that run's `referenced_workflows[].sha` reads
`3ec11c0`, its `claude-review` job's conclusion is `success`, and its
`Run Claude Code Review` step's conclusion is `success` over an inner step
that exited 1, which is #521's `continue-on-error`.
`Morrison-Lab/ai-config`'s `memories/git-tags.md` records the git behavior
itself, and gha#522 is the pointer from here.)
To verify a slide, prefer a **fresh** run -- push a commit, open a PR, or
`workflow_dispatch` -- since it resolves the tag unambiguously and needs no
reasoning about which re-run mode you are in.
"Re-run all jobs" works too; "Re-run failed jobs" never does.

(`UCD-SERG/serodynamics` run 30471653690, 2026-07-29: after `v2` was slid to
c50e847 to pick up #359's `ai-config@Morrison-Lab` retarget, a failed-jobs
re-run failed with the identical
`Failed to install plugin 'ai-config@d-morrison'`.
The job log showed both layers at once -- `INPUT_PLUGINS:
ai-config@d-morrison` from the old reusable workflow, alongside a
`detect-review-request: match=false` line that only exists at c50e847 --
and `referenced_workflows` still read `sha: 6ee996b` on attempt 2.
A dispatched run on a PR branch confirmed the fix immediately.)

## A push touching `.github/workflows/` can fail even though `WORKFLOW_TOKEN` is wired correctly in code

If a push from `claude.yml` (or `claude-bot.yml`'s dispatch of it) fails with:

```text
! [remote rejected] ... (refusing to allow a GitHub App to create or
  update workflow `.github/workflows/<file>` without `workflows` permission)
```

this means the `WORKFLOW_TOKEN` **repository secret** is unset or lacks
`contents:write` + `workflows:write` scope for this repo -- it is not a bug in
`claude.yml`'s own token-resolution code. `claude.yml` already resolves
`PUSH_TOKEN` as `${{ secrets.WORKFLOW_TOKEN || secrets.GITHUB_TOKEN }}`, and
`claude-bot.yml` already passes `WORKFLOW_TOKEN` through; `GITHUB_TOKEN` alone
can never push a `.github/workflows/` change, so the fallback reproduces this
exact rejection whenever `WORKFLOW_TOKEN` isn't configured with the right
scope. Only someone with admin access to this repo's Settings -> Secrets and
variables -> Actions can fix it (a classic PAT with `repo` + `workflow`
scopes, or an equivalent GitHub App installation token) -- an `@claude` session
has no path to set repository secrets itself. If you hit this, don't debug
`claude.yml`'s `PUSH_TOKEN` wiring; recover by pushing the already-committed
local branch from a differently-credentialed session/human, and flag that
`WORKFLOW_TOKEN` needs to be (re)configured. (Hit twice on 2026-07-24: PR #286
fixing #285, and PR #290 fixing #289, both editing `.github/workflows/*.yml`
-- both required manual recovery; see gha#292.)

**Recovery is cheaper than that paragraph implies once `@v2` carries gha#360:
the run now posts the commits back as a patch.** `claude.yml` captures the
push output, hands it to `report-push-failure` (see Layout above), and
comments the explanation plus a `git format-patch` on the thread, so the work
comes back with `git am` instead of being redone from scratch.
Read the comment before re-doing the work; the diagnosis of the *cause* above
is unchanged, and still needs a human with admin access.

The same change closed a second, worse defect.
The rejection left the PR head SHA where it started, which is
indistinguishable from "Claude committed nothing" -- so the "Post Claude's
response if no code was committed" step ran and posted Claude's prose
describing the fixes it had just made, onto a branch carrying none of them
(gha#360, seen on
[Morrison-Lab/ai-config#805](https://github.com/Morrison-Lab/ai-config/pull/805)).
That step is now gated on the push not having failed.
When reading an older thread, treat a "here is what I did" comment as a claim
about the branch to verify rather than as a record of it, per the
SHA-comparison rule in
[`Morrison-Lab/ai-config`'s `shared/workflow/ardi.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/workflow/ardi.md).

**A third, more direct mechanism produces the identical symptom without
`@v2` even entering the picture.** `claude-code-review.yml`'s own `Skip
self-review when the PR edits this workflow` step compares the PR's changed
files against the CALLER's review-workflow path (derived from
`github.workflow_ref`) and, when the PR itself edits that file, skips every
downstream step: checkout, run review, post review comment.
`review / claude-review` reports `success`, but every step past the guard shows
`skipped`, and no verdict is ever produced.
This is deliberate, since the action's own App-token exchange 401s on a workflow
file that doesn't match the default branch's content until merge (see the
guard's own comment).
But a green `claude-review` check is easy to mistake for a real review.

**`require-review` used to report `success` here too, which is what made this
indistinguishable from a clean review on a required check (gha#434).**
Since gha#440 the skip is surfaced as a `self_mod` job output that
`require-review` excludes, so that gate shows a gray *skipped* instead, and the
review job posts a PR comment explaining that no review ran.
Read the gray as "nobody reviewed this", not as an all-clear.
Note the usual tag lag: consumers pinned to `@v2`, this repo's own dogfood
caller included, keep the old both-green behaviour until `@v2` slides past that
merge, so a green `require-review` on an older run is this case rather than a
contradiction.

**The guard checks the caller review workflow on all events, plus any top-level
workflow YAML file on `workflow_dispatch` (gha#386).** `WF_PATH` comes from
`github.workflow_ref` -- in a `workflow_call` run that's the CALLER's own workflow
file, which in this repo's dogfooding setup is `.github/workflows/claude-review.yml`
(for a downstream consumer, their own copy of the caller stub). On automatic
`pull_request` runs, only a PR that touches that one file trips `self_mod=true`.
On `workflow_dispatch` runs, `claude-code-action`'s token exchange validates that
all `.github/workflows/*.yml` files match `main` or it skips with an OIDC
validation error; to prevent false-positive failures, the guard trips `self_mod=true`
for any touched top-level workflow YAML file on dispatch (gha#386).
`examples/claude-code-review.yml` lives under `examples/`, not
`.github/workflows/`, so it never actually executes as a workflow in this
repo and `github.workflow_ref` can never resolve to it either. Check the
job's step list, not just its conclusion, before trusting a green
`claude-review` on a PR that touches `.github/workflows/claude-review.yml` (or
any workflow on dispatch): every step after the guard reading `skipped` means no
review ran, regardless of what `@v2` currently points at. (gha#286: an `@claude
review` comment produced only a `$0.60` cost comment, no verdict -- the guard had
set `self_mod=true` and skipped straight through, because the PR touched
`claude-review.yml` itself.)

**This section's title says "a PR fixing" the review workflow, but the guard
does not check intent -- it checks whether workflow files are in the
changed-file list.** So it also fires on a PR that has nothing to do with the
review system and touches that file only incidentally: a repo-wide sweep, a
lint fix, a formatting pass, a dependency bump.
That case is the dangerous one, because the two cases above at least give you
a reason to be suspicious of a green `claude-review`.
Here nothing prompts the thought -- the PR is "about" something else
entirely, `claude-review.yml` is one file among dozens, and the check is
green.

Before trusting a green `claude-review`, run
`git diff --name-only origin/main | grep -E '^\.github/workflows/[^/]+\.ya?ml$'` rather than
asking yourself whether the PR is *about* the review workflow.
A hit means no review ran, whatever the check says, and the fallback is to
self-review and say so on the PR (see the "Do the review yourself when the
@claude workflow doesn't produce a verdict" section of
[`Morrison-Lab/ai-config`'s own `CLAUDE.md`](https://github.com/Morrison-Lab/ai-config/blob/main/CLAUDE.md)
-- the root file, not one of the `shared/` fragments).
Note the guard cannot clear before merge, since it keys on the PR's own diff
-- re-triggering is not a workaround, so don't spend rounds on it.

Splitting the offending line into a follow-up PR *would* clear the guard, at
the cost of leaving the sweep incomplete and its own docs overclaiming for a
release cycle.
Whether that trade is worth it depends on how much the review is worth for
the rest of the diff; for a mechanically uniform change it usually is not.
(gha#329: a `timeout-minutes` hardening sweep across all 36 workflows touched
`claude-review.yml` for exactly one inserted line, and its review was
silently skipped -- caught only by noticing the job finished in 4 seconds.
Copilot, requested as a fallback, refused separately for quota, so the PR
merged on CI plus a self-review with no external verdict at all.)

**That guard is the workflow-level skip; the action carries its OWN
workflow-content validation, which would fire if the guard were bypassed --
and it does not print a literal `401`.**
The section above skips every step of the review job when the PR edits the
caller workflow `claude-review.yml` (the job itself still runs and reports
`success`, green -- not a gray skipped job).
That `self_mod` skip fires on every such run, dispatched or automatic alike:
`PR_NUMBER` resolves via `github.event.pull_request.number || inputs.pr-number`
with no trigger gating, so an `@claude review` dispatch trips it exactly as an
automatic run does -- the gha#286 example above is that case, the guard firing
on a dispatched review (green job, every post-guard step `skipped`).
So today a caller-editing PR just gets that silent skip.
The review can still run and hit the action's OWN content validation by two
paths.
One is a deliberate bypass -- as gha#417 proposed and this repo rejected.
The other is live and undeliberate: the guard sets `self_mod` from
`files=$(gh api .../files ... || true)` in `claude-code-review.yml`, so a
transient `gh api` failure leaves `files` empty, `self_mod=false`, and the
review proceeds even on a PR that does edit `claude-review.yml`.
Either way the action's content validation then checks the running workflow
against the default branch and gracefully skips on a mismatch.
The "Run Claude Code Review" step then reads:

```text
Exchanging OIDC token for app token...
##[warning]Skipping action due to workflow validation: Workflow validation
failed. The workflow file must exist and have identical content to the
version on the repository's default branch...
Exiting due to workflow validation skip
```

The action STEP reports `outcome=success` (it "gracefully skips"), runs only
~4-11s, and writes NO execution output -- so `check-review-execution.sh`
reports `Claude review produced no execution output -- treating as a failed
review`, and `claude-review` + `require-review` go RED with no verdict.
That is worse than the silent skip, which is why gha#417 was abandoned.

Diagnostic tells for that validation skip, so it is not misdiagnosed as a
`401`:

- The "Run Claude Code Review" STEP finishes in seconds (~4-11s measured)
  while writing no execution output; total job time is not a reliable tell,
  since checkout, submodules, and package installs run first and can dominate.
- Grepping the log for `401` finds nothing -- the auth failure the
  parenthetical above calls "401s" does not surface as a literal `401`
  string; grep for `workflow validation` / `Exiting due to workflow
  validation skip`, or just READ the "Run Claude Code Review" step's own
  output rather than grepping for a guessed string (per
  [`Morrison-Lab/ai-config`'s `shared/principles/fail-fast.md`](https://github.com/Morrison-Lab/ai-config/blob/main/shared/principles/fail-fast.md)).
- The validation keys on workflow CONTENT vs. the default branch, independent
  of trigger type, so bypassing the self-review skip on a dispatched
  `@claude review` does NOT help -- it just reddens the check with no verdict.

The likely fix for a PR editing the review workflow is a `github_token`
override on the action, which would skip the OIDC exchange and its content
check -- but that is untested: PR #420 only showed that bypassing `self_mod`
*without* such an override is counterproductive (it hits this validation skip),
and no `github_token` input is wired up in `run-claude-review-attempt` today.
The [Test changes against a template repo](#test-changes-against-a-template-repo-before-declaring-ready-to-merge)
section reaches the same OIDC content-validation from the testing angle.

## A prompt instruction is a request; a permission rule is a constraint

`run-claude-review-attempt`'s `--append-system-prompt` tells the reviewer to
pass `run_in_background: false` on every `Agent`/`Task` call, because a
background spawn in a headless CI run ends the turn waiting for completion
notifications that no later turn will deliver (gha#392).
That instruction was live, verbatim, when the same failure recurred on
`Morrison-Lab/ai-config#1744` (run 32347489886): four background agents
spawned, turn ended, no verdict, $4.21 (gha#532).

The general point is worth keeping separate from the incident.
**A prompt tells the model what to do, and the model may not.**
When a constraint matters, look for a mechanical form of it before concluding
that a better-worded prompt is the ceiling.

Claude Code has one here, and it is easy to miss because it is newer than the
tool-name and command-prefix rules everyone knows.
Per
[code.claude.com/docs/en/permissions](https://code.claude.com/docs/en/permissions),
"Match by input parameter":

> Deny and ask rules can match a top-level input parameter on any tool with
> `Tool(param:value)`.

So `Agent(run_in_background:true)` is a well-formed deny rule, and it is
narrower than denying `Agent` outright -- which gha#392's follow-up rejected
precisely because it would also break the `code-review` plugin's legitimate
*synchronous* fan-out.

Five things constrain any change here.

**It is a DENY on `true`, not an allow on `false`.**
The same section rules the allow shape out: "allow rules continue to use each
tool's own specifier syntax."
gha#532's body guesses at `Agent(run_in_background:false)` as an allow rule;
that does not work.

**It closes one of two routes, and the prompt still covers the other.**
"A parameter the model omits is never matched", and `Agent`'s
`run_in_background` defaults to true -- so a call that omits the parameter
still backgrounds and this rule does not see it.
The prompt instruction is therefore not redundant, and must not be deleted on
the strength of the rule.
Read the two as covering different halves.

**A parameter rule cannot reach a tool's primary content field.**
The same section lists them (`command` for Bash, `file_path` for Read, `url`
for WebFetch, and so on) and says Claude Code ignores such a rule and warns at
startup, because `Bash(command:rm *)` would be bypassable by a compound
command.
Use the tool's own specifier for those.

**The CLI flag parses this form, and that was measured rather than assumed.**
The documentation describes `Tool(param:value)` as a permission-rule syntax and
never says that `--disallowedTools` accepts it, so a rule that silently failed
to parse would make the mitigation a no-op that looks shipped.
On Claude Code 2.1.238, `Agent(run_in_background:true)` and
`Task(run_in_background:true)` were accepted with no warning.
The negative control is what makes that silence informative: the same CLI
answered `Bash(command:rm *)` -- a rule the docs say is ignored -- with
`Permission deny rule "Bash(command:rm *)" targets command as a raw string and
will not match`.
This establishes that the rules parse, not that they match at call time.

**The denials these rules produce are excluded from the stub-retry gate, and
that exclusion is part of the fix rather than a refinement of it.**
`check-review-execution.sh`'s threshold treats a high denial count as evidence
the reviewer was **starved** of tools it needed -- its own comment says
gha#198's pattern "has repeatedly NOT recovered", which is why crossing the
threshold withholds the retry.
A denial produced by a rule this repo added on purpose is not evidence for
that, and it is not a small distortion at the sizes actually observed: the two
incidents motivating these rules were a 4-spawn and an 8-spawn fan-out, so the
second alone clears the default threshold of 5 before any genuinely-starved
call is counted.
Shipping the deny without the exclusion would therefore flip a retryable
gha#185 stub into a hard-failed gha#198 classification in precisely the
scenario the deny exists to serve.
So the gate reads a count with the intended denials removed, while every
reporting path keeps the true total -- a PR comment saying the reviewer was
denied nothing when it was denied eight times would be false, and the
denied-tools summary is what a triager acts on.
The subtraction needs the `permission_denials` array, since that is what names
tools; where only the scalar count survives (the gha#531 shape) no subtraction
is possible and the gate falls back to the raw count, classifying such a run
exactly as it is classified today.
That direction is deliberate, since assuming unnamed denials were ours would
weaken the gha#198 gate on evidence we do not have.

## Never just theorize -- investigate empirically

A hypothesis that is cheap to test must be tested before it is asserted, and
certainly before it is acted on or reported to anyone.
Naming a plausible cause is the start of the work, not the end of it.
The failure mode is not being wrong; it is being wrong *and* confident,
because a stated hypothesis reads to everyone else like a finding.

This matters most when diagnosing CI, where the authoritative answer is
almost always one call away and the plausible answer is almost always
slightly wrong:

- **Read the failure's own output before theorizing about its cause.**
  A job that fails with no logs still has an error banner on its job page,
  reachable with `WebFetch` on the run URL even when the API will not serve
  it. gha#351/#352: an org-wide job failure was attributed to an Actions
  spending limit, then -- after that was disproved -- to anything but
  billing, when the banner said
  `The job was not started because your account is locked due to a billing
  issue` all along.
- **Read the tool's config before modelling its behavior.**
  A guess at lychee's redirect handling was wrong because `301` is in
  `check-links/lychee.default.toml`'s `accept` list; two successive guesses
  at markdownlint's MD013 flagged 269 and then 31 lines against the
  linter's actual 1, because
  `lint-qmd/.markdownlint.qmd.jsonc` sets
  `{ line_length: 80, code_blocks: false, tables: false }` and markdownlint
  ignores a line with no space past the limit.
  A model of a checker is only worth using once it reproduces that checker's
  known result on a known input.
- **Prefer the run's own artifacts to your inference about them.**
  Which repositories moved in the org transfer was answerable from the lychee
  run's redirect and error lists -- `qwt`, `rme`, and `rpt` appeared in
  neither at the time, so they resolved cleanly then -- rather than from
  reasoning about which ones "probably" moved.
  (`rpt` has since moved to `Morrison-Lab/rpt`; the point here is the method,
  and the list is a snapshot of what that specific run found.)

**A wall of access failures is not evidence that something cannot be
investigated.** In the same work, `get_check_run` returned `301`, the
MCP tools refused the new owner as out of scope, and the agent proxy
returned `403` for `api.github.com` -- three failures in a row, after which
a plain public `https://github.com/...` URL answered the question
immediately. Exhausting the authenticated routes is a reason to try an
unauthenticated one, not a reason to report the question as unanswerable.
The same principle already appears above for reading files out of
repositories this session is not scoped to.

## Test changes against a template repo before declaring ready to merge

Before declaring a PR ready to merge -- or reporting a clean / ready-for-merge
verdict -- for a change in this repo (`gha`) that touches a GitHub Action or a
component action/workflow, test that change against one of the lab's template
repos.

Running the unit tests or `_selftest.yml` in `gha` alone is not sufficient for
such a change, because `_selftest.yml` exercises local composites and throwaway
fixtures rather than the full downstream project structures -- an R package's
vignettes, a Quarto site build -- that pin the `@v2` reusable workflows.
Instead, point a template repo's `uses:` at the PR's branch or SHA and confirm
the workflow succeeds there:

- **`rpt`** ([`Morrison-Lab/rpt`](https://github.com/Morrison-Lab/rpt)) -- R package template
- **`qwt`** ([`d-morrison/qwt`](https://github.com/d-morrison/qwt)) -- Quarto website template
- **`qbt`** ([`d-morrison/qbt`](https://github.com/d-morrison/qbt)) -- Quarto book template
- **`qmt`** ([`d-morrison/qmt`](https://github.com/d-morrison/qmt)) -- Quarto manuscript template

Repointing the template's top-level `uses:` exercises a change to a reusable
workflow's own YAML, but not a change to a **composite action**
(`.github/actions/<x>/`, where most of this repo's capabilities live).
A reusable workflow pins its internal composite calls to a literal `@v2`
(e.g. `claude-code-review.yml` has ~10 such `uses: .../actions/<x>@v2` sites),
and those resolve at job-preparation time from the released tag regardless of
the ref the parent workflow file was fetched from (see [Re-running *failed jobs*
cannot verify a tag slide](#re-running-failed-jobs-cannot-verify-a-tag-slide)).
So a template test of a composite-only change passes vacuously against the old
released code.
To exercise a composite change, also repoint the nested `@v2` refs to the PR
branch on the branch-pinned reusable workflow, or invoke the composite directly.

A PR fixing a reusable **review** workflow (`claude-code-review.yml` or
`claude.yml`) can't be verified this way at all.
The review runs `anthropics/claude-code-action`, whose OIDC App-token exchange
validates that the calling review-workflow content matches the repo's default
branch.
Testing the fix means running the review against a modified copy of that
workflow, which makes the caller differ from its own default branch -- in `gha`
or in a template repo alike -- so the action aborts with `Workflow validation
failed` ("Exiting due to workflow validation skip"), produces no output, and
reddens the check with no verdict.
(Confirmed empirically 2026-08-05 via a throwaway dispatched review; the failure
surfaces as a fast `no execution output`, not a literal `401`.)
Fall back to the manual/offline path in
[A PR fixing claude-code-review.yml (or claude.yml) itself can't self-verify before merge](#a-pr-fixing-claude-code-reviewyml-or-claudeyml-itself-cant-self-verify-before-merge),
or give the action a `github_token` override that skips the OIDC exchange
(untested -- see the workflow-validation-skip note's `github_token` caveat above).

## Code review guidelines

When reviewing a pull request (e.g. via `/review`, `/code-review`, or as a Claude
PR bot), evaluate the diff against **all** of the following, in addition to
correctness:

### 1. The SERG lab manual

The [UCD-SERG lab manual](https://ucd-serg.github.io/lab-manual/) is the lab's
authority on coding conventions. Hold changes to its standards, especially:

- [Coding style](https://ucd-serg.github.io/lab-manual/coding-style.html) --
  object naming, line breaks/formatting, function documentation, comments,
  message/communication style, and Quarto code-reference conventions (backticked
  `pkg::fn()`, markdown package links -- no raw HTML in `.qmd`).
- [Coding practices](https://ucd-serg.github.io/lab-manual/coding-practices.html) --
  function decomposition and length limits, testing requirements, the QA
  checklist, documentation, `{here}` for paths, and tidyverse idioms.
- [Code repositories](https://ucd-serg.github.io/lab-manual/code-repositories.html) --
  repository organization and version-control practices.

The manual defers to the [tidyverse style guide](https://style.tidyverse.org/)
for R; prefer tidyverse idioms and the native `|>` pipe.

### 2. d-morrison's review priorities

Above all, code should be **highly modular and idiomatic**:

- **Modular / decomposed.** Favor small, single-purpose functions over long
  monolithic blocks. Flag duplicated logic (DRY), functions that do too much,
  deep nesting, and steps that should be extracted and named. In workflows and
  composite actions, factor shared logic into reusable units rather than copying
  it between files.
- **Idiomatic.** Code should read like the surrounding code and like the
  ecosystem's conventions -- idiomatic R (tidyverse), idiomatic YAML/GitHub
  Actions, idiomatic shell. Prefer the standard, well-known way over a clever or
  bespoke one. Match existing naming, structure, and formatting in the file.
- Keep these front-of-mind: surface modularity and idiom issues even when the
  code is otherwise correct.

Be specific and cite the relevant manual section or principle when raising a
point. Distinguish blocking issues from optional suggestions.

### 3. Challenge ambiguous phrasing and terminology

Flag ambiguous terms and phrasing rather than accepting a plausible-sounding
reading -- a name that could mean more than one thing, a claim that cites a
value or construct without confirming it exists in the actual code. This is a
global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus.
Ambiguity accepted at face value is how a factually wrong claim (e.g.
documentation citing a nonexistent enum value) slips through review
unchallenged.

### 4. Fact-check prose against domain knowledge and external sources

When a diff touches prose (`README.md`, `CHANGELOG.md`, `website/`, action
descriptions), assess the accuracy and clarity of its claims -- check each
against domain knowledge and, where checkable, an external source (the
referenced tool's own docs, a linked spec) -- and check any document-internal
reasoning the prose makes (e.g. a justification for why a workflow does
something a particular way). Also check that every factual claim is
*defended*, separately from whether it's accurate: it needs either
reasoning in the surrounding text or a citation, and a bare assertion with
neither is a finding even when it turns out to be true. State which claims
are inaccurate or undefended, cite the specific source checked for each
judgment, and proactively suggest additional citations where they'd help.
This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/fact-check-prose.md`).

### 5. Check for AI-generated prose tells

When a diff touches prose (`README.md`, `CHANGELOG.md`, `website/`, action
descriptions), scan it for the telltale signs of AI/LLM authorship --
overused vocabulary (delve, leverage, robust, seamless, tapestry,
testament…), the "it's not just X, it's Y" antithesis, mechanical
rule-of-three lists, hedging stacks, signposting filler, em-dash overuse,
bold-leading bullets, emoji headers, and promotional register. Flag each
tell found with its location and a de-slopped suggested revision -- weigh
clustering, not an isolated instance. This is a global standing rule from
the [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/ai-tells.md`).

### 6. Hyperlink technical terms/results; no forward references

When a diff touches prose that defines technical terms or named results via
Quarto's theorem-like crossref divs (`::: {#def-...}`, `{#thm-...}`,
`{#lem-...}`, `{#cor-...}`, `{#prp-...}`, `{#cnj-...}`, `{#exm-...}`,
`{#exr-...}`), check that every mention of a term or result links to the
div that defines it, and that the div appears *before* its first mention in
reading order -- a link to a definition the reader hasn't reached yet is a
forward reference. This scope is per rendered file: cross-chapter ordering
in a multi-file Quarto book is out of scope, check it manually. This is a
global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/definition-crossrefs.md`).

The same problem also shows up as plain-text signposting -- "as discussed
below", "in the following section", "we'll cover this later" -- pointing at
content the reader hasn't reached yet, in *any* prose, not just documents
with crossref divs. Flag these too: confirm each hit is a genuine reference
(not an idiom like "values below the threshold") and that the target really
comes later, then suggest reordering the content earlier or rewording the
pointer into a working link. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/forward-references.md`, added in
[ai-config#507](https://github.com/Morrison-Lab/ai-config/pull/507)), with a
dedicated `fix-forward-references` (`ffr`) skill there that applies
the fix directly rather than only flagging it in review.

### 7. Suggest semantic line breaks in prose

When a diff touches prose (`README.md`, `CHANGELOG.md`, `website/`, action
descriptions), check that lines break at clause/sentence boundaries (roughly
60-80 characters) instead of reflowing into long unbroken lines -- a semantic
break keeps a diff scoped to the changed sentence. Raise violations as a
suggestion, not a blocking requirement, and don't re-raise it if the author
declines. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/semantic-line-breaks.md`).

### 8. Check code and math for strategic and tactical correctness

Beyond style, check whether the diff's code -- and any math or statistics
embedded in it -- is *right*, not just correctly styled:

- **Strategic correctness.** Is this the right algorithm or design for the
  problem? A clean implementation of the wrong approach (wrong data
  structure for the scale, a statistical method whose assumptions don't
  hold for this data, a concurrency strategy prone to races) is still
  wrong.
- **Tactical correctness.** Given the chosen approach, does the code
  correctly execute it -- no off-by-one errors, sign errors, wrong
  comparison operators, mis-transcribed formulas, unit/dimension
  mismatches, or numerical instability.
- **Math/stats in code.** Verify a formula, statistical test, or model
  against its source (a paper, a spec, a package's reference
  implementation) with the same rigor that item 4 applies to a derivation
  in prose.

Distinguish a strategic finding (needs a different approach) from a
tactical one (needs a correction within the existing approach) -- the fix
differs. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/coding/fact-check-code-logic.md`, added in
[ai-config#455](https://github.com/Morrison-Lab/ai-config/pull/455)).

### 9. Challenge unnecessary complexity

When reviewing prose, math, or code, check whether it is more complex than
the problem requires --
not just whether it's correct or clear. Flag

needlessly convoluted control flow, abstraction layers that add
indirection without earning it, an overcomplicated derivation or an
unnecessarily general result when a simpler equivalent exists, and prose
that restates a point through more clauses or jargon than a plain rewrite
needs. For each finding, propose the concrete simplification rather than
just naming the complexity, and confirm it doesn't drop a feature, an edge
case, or a meaning the original carried. This is a global standing rule
from the [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config)
corpus (`shared/workflow/challenge-unnecessary-complexity.md`).

### 10. Question redundant content

When a diff touches prose, math, or code, check for content that could be
consolidated without losing completeness or generality -- a claim or
explanation restated in two places, a formula re-derived as a special case
the general form already covers, duplicated logic across functions/files.
Flag it only when nothing would be lost by merging; genuinely distinct
content that merely looks similar should stay separate. This is a global
standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/workflow/challenge-redundant-content.md`).

### 11. Write and recommend tidy, concise code

Beyond style-guide compliance, check whether the diff's code is genuinely
tidy -- no leftover debug output, no dead branches, no function doing three
unrelated things at once. In R code specifically, flag verbose base R or
`{rlang}` constructs where a concise tidyverse equivalent (`dplyr`, `purrr`,
the `{{ }}` embrace) does the same job more clearly, unless the tidyverse
form would pull in a heavy dependency for a one-liner, the surrounding file
is consistently base-R, or a hot loop needs base R's performance. This is a
global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/coding/tidy-code.md`).

### 12. Reuse function documentation and argument lists

Flag R code that copy-pastes a `@param` description or a prose section
between roxygen blocks instead of using
[roxygen2's tag-reuse tags](https://roxygen2.r-lib.org/reference/tags-reuse.html)
(`@inheritParams`, `@inheritDotParams`, `@inheritSection`) -- reused docs stay
in sync when the source function's docs change; copy-pasted docs silently
drift. Also flag a wrapper function that manually re-declares and relays
arguments it never touches itself instead of forwarding
[`...`](https://adv-r.hadley.nz/functions.html?q=dot-dot#fun-dot-dot-dot)
straight to the subfunction (documented via `@inheritDotParams`). This is a
global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/coding/reuse-docs-and-args.md`, added in
[ai-config#474](https://github.com/Morrison-Lab/ai-config/pull/474)).

### 13. Flag skipped steps in math derivations

When a diff touches a mathematical derivation (an algebraic manipulation, a
proof, a statistical argument), check that every step is shown -- no two or
more operations (distribution, cancellation, substitution, applying a named
identity or assumption) combined into a single displayed line. When a step is
missing, name the exact gap (the last line before the jump and the first line
after it), name the specific operation that closes it, and draft the missing
line(s) where feasible rather than only flagging "skipped steps" in general.
This is distinct from item 8's derivation-validity check (whether each
*stated* step follows correctly) -- this one catches a step that isn't
stated at all. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/math-derivation-steps.md`).

### 14. Don't reinvent the wheel

When a diff adds a new function or feature, check whether that
functionality has already been done -- in one of the lab's own repos
(the lab packages, this repo's reusable workflows and actions), or in a
trustworthy external source the code could depend on instead (base R,
[r-lib](https://github.com/r-lib),
[tidyverse](https://github.com/tidyverse), a focused, well-maintained
CRAN package, a vetted, well-maintained GitHub Actions marketplace
action -- SHA-pinned per `README.md`'s "Pinning third-party actions"
subsection). Flag a hand-rolled
equivalent of functionality that already exists: name the existing
implementation, and prefer depending on it --
or forking and/or contributing to it --
over re-building from scratch. Accept the custom
version when the existing option is genuinely unfit (wrong API,
unmaintained, license-incompatible, or a heavy dependency for a
one-liner), and ask for a note in the PR description or a code comment --
"checked existing options, nothing fit" --
when it's missing. This is a global standing rule from the

[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/coding/prefer-packaged-functions.md` states the R-function
case); its umbrella statement lives at
`shared/principles/dont-reinvent-wheel.md` there, added in
[ai-config#603](https://github.com/Morrison-Lab/ai-config/pull/603).
