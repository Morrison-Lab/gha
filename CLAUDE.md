# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Memory storage policy

- Persist standing notes and memories only in repo-tracked files
  (via commits/PRs); do not save them to non-repo local paths.

## About this repo

Central, reusable GitHub Actions for `d-morrison` / `UCD-SERG` / `ucdavis` R-package
and Quarto repositories (see [`README.md`](README.md)). Each capability ships as a
composite action plus a `workflow_call` reusable workflow. Consumers pin the
major tag each capability's own reference page documents (`@v1` for most,
`@v2` for `preview`, `preview-deploy`, `cleanup-pr-previews`, `quarto-publish`,
`test-coverage`, `check-equation-renders`, `check-bibliography-dois`,
`check-phi`, `check-links`, `check-non-standard-chars`, `claude`,
`claude-code-review`, `update-snapshots`, `lint-yaml`, `lint-markdown`,
`lint-qmd`, `lint-changed-lines`, `check-new-line-breaks`, `check-secrets`,
`request-dependabot-review`, `sync-upstream`, `check-news`,
`altdoc-multiversion-docs`, `report-failure`, `gemini`,
`gemini-code-review`, `antigravity-code-review`, `ai-code-review`, `bump-dev-version`, and
`version-check` -- see
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
  `preview/`, `quarto-publish/`, and `open-sync-pr/` are action-only (the last
  is the shared push-and-open-PR helper used by `bump-submodule`,
  `sync-shared-fragments`, and `sync-upstream`).
- `.github/workflows/` — the `workflow_call` reusable workflows that wrap the
  composites (one per consumer-facing capability — the shared internal
  `open-sync-pr` composite has no wrapper), plus the `claude.yml` and
  `claude-code-review.yml` reusable wrappers, and `_selftest.yml`, which
  exercises composites on every PR — local `./` refs for pre-release
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
  into a fork via `git merge --squash` — which stays out of a `MERGE_HEAD`
  state so `open-sync-pr`'s `git switch -C` works — then lets `open-sync-pr`
  commit the merge and open the PR);
  `request-dependabot-review.yml` similarly calls the internal
  `build-reviewer-args` composite (see below) for its reviewer-list
  split/trim logic; `slide-major-tag.yml` is dispatch-triggered and runs
  only in this repo.
- `.github/actions/checkout-submodules/` — a small shared composite reused by the
  reusable workflows.
- `.github/actions/parse-workflow-ref/` — a small composite action that parses a
  `github.workflow_ref`/`github.job_workflow_ref`-shaped string
  (`owner/repo/.github/workflows/<file>@ref`) into its `repo`/`path`/`ref` parts,
  shared by every `claude-code-review.yml` and `claude-review.yml` step that
  needs to pick one of these strings apart instead of duplicating the `sed`
  logic inline. It has to be a composite action rather than a plain checked-out
  script (like `check-review-execution.sh` below) because some call sites run
  before any checkout has happened — a composite action's own files are
  available via `uses:` regardless of checkout state, which a bare script path
  is not.
- `.github/actions/run-review-guard/` — a thin composite-action wrapper around
  `check-review-execution.sh` (below), invoked from `claude-code-review.yml`'s
  "Fail the check if the review did not complete (attempt 1)" step (and again
  from its retry counterpart — see `run-claude-review-attempt` below). #191
  tried to locate that script by resolving Morrison-Lab/gha's own repo/ref from
  `github.job_workflow_ref` and checking it out into a side directory, but
  that context var came back empty at runtime on real consumer runs even
  though the calling step passed it correctly (gha#196) — the #191 fix was
  only unit-tested via the sed-parsing logic in isolation, never exercised
  end-to-end. `github.action_path` doesn't have that failure mode: a composite
  action's own files are always reachable through it regardless of how the
  calling reusable workflow was invoked, the same reasoning `parse-workflow-ref`
  itself relies on.
- `.github/actions/run-claude-review-attempt/` — wraps the single
  `anthropics/claude-code-action` call `claude-code-review.yml` uses to review
  a PR (allowedTools/disallowedTools, the review prompt). Extracted into a
  composite action so `claude-code-review.yml` can invoke it a second time,
  unchanged, as a same-prompt retry when the first attempt completes without
  an SDK error but never states a verdict — the "stub review" signature
  (gha#185): `check-review-execution.sh` surfaces this specific case via a
  `stub_review` output (through `run-review-guard`), and the workflow retries
  once before failing the check for real. Keeping the `claude-code-action`
  call itself in one place (rather than duplicating its ~100-line `with:`
  block between two near-identical steps) follows this file's own DRY
  guidance below. `claude-code-review.yml`'s "Resolve final review outcome"
  step is the single point that decides which attempt's output to use and the
  only step that actually fails the job when neither attempt produces a
  usable review — both "Fail the check" steps are `continue-on-error: true`
  so a recovered retry doesn't leave the job red.
- `.github/actions/upload-review-execution/` — resolves claude-code-action's
  `execution_file` output (with its temp-path fallback) and uploads it as a
  workflow artifact, in one composite action shared between attempt 1 and the
  `run-claude-review-attempt` retry above — the same DRY rationale that
  motivated extracting that (much larger) composite action, just at a
  smaller scale (gha#201 review).
- `.github/actions/extract-total-cost/` — wraps
  `scripts/extract-total-cost.sh`, which extracts `total_cost_usd` from a
  claude-code-action execution-output file's last `result` event. `claude.yml`
  calls it once, right after "Run Claude Code", and both its
  comment-posting steps ("Post Claude's response if no code was committed"
  and "Finalize PR for issue trigger") read the shared
  `steps.cost.outputs.cost` — a single extraction instead of duplicating the
  jq filter at both call sites (gha#219 review finding 1).
- `.github/actions/sum-costs/` — wraps `scripts/sum-costs.sh`, which sums two
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
  Three things constrain any change to that stripper.
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
  It lives in its own script rather than inline because the same constructs
  gate whether the agent runs at all (gha#342).
- `.github/actions/detect-bot-mention/` -- wraps
  `scripts/detect-bot-mention.sh`, which decides whether a body carries an
  `@claude` mention that is actually addressed to the bot rather than quoted
  while writing about it.
  `claude.yml` calls it once, early, for all four reactive events, and feeds
  the result into its "Decide whether this run should proceed" step.
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
  Note what it does **not** fix: `claude-bot.yml`'s job-level `if:` still
  tests the raw body, because a GitHub expression cannot strip Markdown, so
  the job still starts and the runner still spins up.
  What is avoided is the billed agent run and the review re-dispatch, which
  are the two costs gha#342 actually names.
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
  CLAUDE.md's "A canceled review can red-X require-review" documents for
  `claude-code-review.yml` -- a canceled run there fails `require-review`
  outright, which is expected and not a code bug. (Added after the "Default
  Gemini Project" API-key suspension incident, 2026-07-30, gha#379 -- see the
  Tests section below for the offline coverage and the `_selftest.yml`
  end-to-end proof.)
- `.github/actions/build-reviewer-args/` — wraps
  `scripts/build-reviewer-args.sh`, which splits a comma-separated reviewers
  list into a JSON array of trimmed, non-empty usernames.
  `request-dependabot-review.yml` calls it once to build its `gh api -f
  reviewers[]=...` arguments, so the split/trim logic has offline test
  coverage instead of only being exercised by a live Dependabot PR (gha#253
  review: a bare `IFS=',' read -ra` doesn't trim whitespace, so `"alice,
  bob"` sent an invalid `reviewers[]= bob` and failed the job).
- `.github/actions/open-failure-issue/` — wraps two scripts:
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
  file a new issue. `report-failure.yml` calls it;
  `check-links.yml`'s own inline `gh issue create` is its intended second
  caller, deferred to gha#327 for the sequencing reason below. Two behaviors
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
- `examples/` — caller stubs consumers copy into their own repos.
- `README.md`, `CHANGELOG.md` — top-level project docs;
  `REVDEPS.md` — lists registered downstream consumer repos. Every PR that
  changes user-facing behavior should add a **changelog fragment** under
  `changelog.d/` (a `<slug>.<category>.md` file — see `changelog.d/README.md`)
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
can look like a superset of the bespoke version it replaces — more inputs,
more hardening, more edge-case handling — while still missing one specific
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
serocalculator's bespoke `test-coverage.yaml` — same coverage measurement,
same testthat-output and failure-artifact steps — but was missing the
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
dogfood job were both cut from that PR for this reason and moved to gha#327,
after `links / link-checker` went red on exactly this.)

**A brand-new capability that ships at a tag newer than `@v1`** (because `@v1`
was frozen before it existed — see `slide-major-tag.yml` / the Versioning
section of `README.md`) needs its major tag updated at two distinct kinds of
site, not just the obvious one:

1. **Capability-specific refs** — the new capability's own caller stub
   (`examples/<name>.yml`) and reference-page example
   (`website/reference/<name>.qmd`).
2. **Blanket-rule prose** — any general "pin every reference to `@v1`"
   statement elsewhere (`README.md`'s Versioning section,
   `website/workflows.qmd`) needs an exception clause, even though it never
   names the new capability.

Grep the repo for `@v1` rather than relying on memory of where it appears.
Missing either kind surfaces as a workflow-not-found error for consumers who
copy that spot literally (gha#148, caught across two review rounds).

**When narrowing an already-fixed blanket claim, re-grep the WHOLE repo after
every edit — not just the files you already know about.** The same versioning
convention gets restated in multiple, independently-worded spots: not just
once per file, but in separate sections of the *same* file (e.g. `README.md`'s
`## Versioning` section and its nested `### Pinning third-party actions`
subsection both needed the same `@v1`/`@v2` exception clause), and across sibling
pages that all describe the tag scheme (`website/index.qmd`'s nav blurb,
`website/versioning.qmd`, `website/workflows.qmd`, `CLAUDE.md`'s own "About
this repo"). Fixing the first instance you find and moving on invites the
reviewer to find the next one in a later round — gha#181 took six review
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
2. **`website/workflows.qmd`**'s equivalent table row — a separate table, not
   generated from `README.md`, so it drifts independently.
3. **`website/reference/<name>.qmd`**'s Inputs table, plus a commented usage
   line in its `## Example` block.

Grep the repo for the workflow's filename (e.g. `claude-code-review.yml`)
across `README.md`, `website/workflows.qmd`, and `website/reference/` rather
than assuming only one needs the update. Caught across four review rounds on
gha#161 — the fix for round 2's finding (missing composite) surfaced round
3's finding (docs out of sync), whose fix left one more untouched table row
that round 3 flagged as out-of-scope, fixed anyway before round 4 confirmed
clean.

**Widening a job's trusted-author `if:` gate to admit a new event type needs
a downstream-step audit, not just the gate itself.** `claude.yml`'s and
`claude-code-review.yml`'s steps read event-shaped context
(`github.event.issue.number`, `github.event.comment.body`, etc.) that only
exists for the event types the gate used to admit. A step that looks safely
scoped — e.g. gated on a `steps.dedup.outputs.skip != 'true'` flag — can still
run and fail under the newly-admitted event, because that flag was never set
for it either; the flag and the missing context are two independent gaps, and
fixing the top-level `if:` closes neither. After widening a job `if:`, grep
the same job for every step whose `if:`/`env:` reads event-shaped context and
add the same admit condition (or an explicit exclusion) to each one — don't
assume a step's existing conditional already covers the new event just
because it looks gated. (gha#245/#246: widening `claude.yml`'s job `if:` to
admit `workflow_dispatch`/`schedule` left two post-steps —
`Acknowledge @claude mention` and `Post Claude's response if no code was
committed` — still ungated for those events; both ran and attempted
`gh issue comment ""` on every unattended run, one failing visibly, contrary
to the PR's own prompt text claiming no post-step would post a reply. Caught
by review, not by the author's own initial self-check.)

### Tests

`check-phi/tests/test_detectors.py` is a pytest suite pinning each PHI detector's
positive and negative behavior. Run it with `python3 -m pytest check-phi/tests/ -q`;
CI runs it as the `phi-tests` job in `_selftest.yml`. There's no broader unit-test
harness — most capabilities are validated end-to-end by `_selftest.yml`, running
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
exercise -- but `main()` returns 0 on every path unless `NLB_FAIL` is set, so
the step stays green whether the input arrives, is dropped, or was never
declared at all (an undeclared composite input is only an Actions warning).
What actually pins the `env var -> main() -> exit code` path is a set of
pytest cases that set `NLB_FAIL=true` around a real `main()` call on a
throwaway git repo, asserting exit 1 with the clause check on and exit 0 both
with `NLB_CLAUSE_BREAKS=false` and with the length gate raised past the line.
Each was confirmed to fail when the corresponding env read is stubbed out.
(gha#337 review round 2: the step's original comment, and this paragraph,
both claimed the step proved the plumbing; neither could.)
Round 3 added the converse caveat, since "cannot prove the input arrived" is
not "proves nothing": the step still pins that `action.yml` parses and that
the opt-out code path runs to completion, which is why it stayed rather than
being deleted as dead weight.
Round 5 narrowed that caveat in turn -- it had also claimed the step pins
that the input is *declared*, contradicting this paragraph's own point two
sentences earlier that an undeclared input is only a warning.
Declaration is pinned by the defaults-agreement test instead, which reads
each YAML file for the input's `default:` and fails outright when there is
none (gha#337 review round 5).

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
Note also that gha#389 leaves the lookahead half still missing sentences, so
3398 is itself an undercount and the true hidden share is lower still --- which
is an argument about the size of the number, not about whether it is worth
fixing.
gha#389 is the lookahead requiring ``[A-Z"'`*\[]``, which misses a sentence
starting with a lowercase identifier.
So when either half is widened, ask what the *other* half now blocks before
concluding the construction is covered -- and pair the widening with a
negative case, since the two halves are also each other's guard rails
(#397's `*` is safe to add precisely because the lookahead still refuses a
following lowercase word).
The whole regex is duplicated in `Morrison-Lab/ai-config`'s
`scripts/semantic-line-breaks.py`, the reformatter this check is the detector
half of, so a fix to either is owed to the other.

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
the expected pass/fail/skip/fail-stub outcome (`fail-stub` — gha#185 — is a
`fail` fixture that must ALSO write `stub_review=true`, the signature
`claude-code-review.yml` retries on); CI runs it as the `review-fail-check`
job in `_selftest.yml`. These fixtures ARE committed rather than generated at
runtime — unlike the R-package/PHI-shaped fixtures the rule above warns
about, they're plain JSON execution-output data with no content that would
trip the `bib` or `phi` jobs' repo-wide scans (gha#174).

`.github/actions/parse-workflow-ref/tests/run-tests.sh` exercises the
extracted `parse-workflow-ref.sh` (see Layout above) offline against a tag, a
branch, and a full-SHA ref; CI runs it as a step in the same
`review-fail-check` job in `_selftest.yml` (gha#191).

`review-fail-check` also runs `run-review-guard` (see Layout above) itself via
a real `uses: ./.github/actions/run-review-guard` step against the
`genuine-finished-review.json` fixture, asserting it produces a non-empty
`review_text_file` output — and a second such step against a stub fixture,
asserting the `stub_review` output comes back `true`. Unlike the fixture
tests above (which invoke `check-review-execution.sh` directly), these prove
the composite action's `github.action_path`-relative resolution of that
script, and its output passthrough wiring, actually work — a gap that let
gha#191's `job_workflow_ref` regression (gha#196) go unnoticed: the
sed-parsing logic was unit-tested, but nothing exercised the real `uses:`
call end-to-end. `run-claude-review-attempt` (see Layout above) has no
equivalent selftest coverage — it wraps a live `anthropics/claude-code-action`
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
"review", `reviewer` as a whole different word), and a multi-body call.
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
local-ref paragraph describes) — so `dependabot-review` tests the composite
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
— the same `github.action_path`-resolution proof the `run-review-guard` /
`build-reviewer-args` e2e steps give, and the reason `dry-run` exists at all:
without it the only end-to-end call would file an issue on this repo every
selftest run. As with `request-dependabot-review`, the `report-failure.yml`
reusable-workflow layer above the composite is not covered — it calls the
action via `Morrison-Lab/gha/...@v2`, which does not resolve until `@v2` is
advanced past this capability's merge — so the job tests the composite
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

The `altdoc-docs` job in `_selftest.yml` exercises
`generate-altdoc-version-dropdown`, `generate-altdoc-landing-page`, and
`resolve-altdoc-base-url` (see Layout above) directly against a throwaway
fixture: a separate git-init'd
package directory (not this checkout) with two release tags, asserting the
composite picks the correct latest/previous tags and dev version and rewrites
the navbar "Versions" block and root-redirect HTML correctly.

It calls `generate-altdoc-version-dropdown` three times, over two fixtures.
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
access. Skills and built-in commands that tell you to "use `gh`" — `/review`,
`/code-review --comment`, `/security-review`, `/verify`, PR babysitting, PR
creation — only work if their GitHub steps are translated to the GitHub MCP tools
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

**Some of these sessions have no local git checkout at all** (not just a missing
`gh` CLI) — there is no working tree to run `git commit`/`git push` against, so
every change (branch, file edit, PR) must go through the MCP write tools below.
Editing a file means: `mcp__github__get_file_contents` first to get its current
blob `sha` (required on every update, not just the first — re-fetch it after
each write since it changes on every commit), then
`mcp__github__create_or_update_file` with the **full** new file content (it
replaces the whole file, there is no patch/diff mode) and that `sha`. A stale
`sha` (from before another commit landed) fails the write — re-fetch and retry
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
| read inline review comments | `mcp__github__pull_request_read` (`method: get_review_comments`) — also returns `threadId`s |
| post a top-level PR comment | `mcp__github__add_issue_comment` |
| post inline review comments | `mcp__github__pull_request_review_write` (`method: create`, no `event`) → `mcp__github__add_comment_to_pending_review` per comment → `mcp__github__pull_request_review_write` (`method: submit_pending`) |
| reply to a review comment | `mcp__github__add_reply_to_pull_request_comment` |
| approve / request changes | `mcp__github__pull_request_review_write` (`method: create` with `event`) |
| resolve a review thread | `mcp__github__pull_request_review_write` (`method: resolve_thread`, `threadId: <id from get_review_comments>`) |
| `gh issue list` / `gh issue view <n>` | `mcp__github__list_issues` / `mcp__github__issue_read` |
| read a file / repo contents | `mcp__github__get_file_contents` |
| create/edit a file (no local checkout) | `mcp__github__create_or_update_file` — needs the target branch, full new file content, and the file's current blob `sha` (from `get_file_contents`) if it already exists |
| create a branch (no local checkout) | `mcp__github__create_branch` |
| CI runs & job logs | `mcp__github__actions_list`, `mcp__github__actions_get`, `mcp__github__get_job_logs` |
| watch / stop watching PR activity | `mcp__github__subscribe_pr_activity` / `mcp__github__unsubscribe_pr_activity` |
| `glab mr ...` (GitLab) | N/A — this repo is on GitHub; use the tools above |

Posting inline comments requires a **pending review to already exist** before
`mcp__github__add_comment_to_pending_review`; create the pending review first, add
each comment, then submit once at the end. Watch and respond to PR activity with
`mcp__github__subscribe_pr_activity` / `mcp__github__unsubscribe_pr_activity` (not
`gh pr checks --watch`).

### Reading repos outside the session's MCP scope

A task often needs files from a *sibling* repo (e.g. `d-morrison/qwt`) that the
session's GitHub MCP tools aren't scoped to — those calls fail with
`Access denied: repository … is not configured for this session`. **Don't report
the repo as inaccessible from that alone.** First try the raw HTTP URL directly:
any **public** repo's files are fetchable with `curl` (or `WebFetch`) at
`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>`, which works
even when `gh` and the MCP tools don't. (This is how qwt's standalone workflows
were obtained to port them faithfully into the reusable workflows for #44/#45.)
Only fall back to "can't access it" — or to whatever session tooling can add a
repo to scope, if any — after the raw fetch also fails (private repo, or the
network policy blocks the host).

**A 403 from a *rendered* docs site is not the same as the content being
inaccessible.** A GitHub Pages / Quarto-rendered site (e.g.
`ucd-serg.github.io/lab-manual/coding-style.html`) can reject `WebFetch` (for
reasons unclear — possibly anti-scraping) even though the *source* file it
was built from is a plain file in a public repo. Don't conclude the content is
unreachable — find the source path (often the same repo, e.g.
`coding-style.qmd` for `coding-style.html`, sometimes with `_`-prefixed
included fragments) and raw-fetch that instead using the same
`<path>`-includes-its-extension template above, e.g.
`https://raw.githubusercontent.com/<owner>/<repo>/<branch>/coding-style.qmd`.
(Confirmed this way that `ettbc`'s `.lintr.R` predates
`UCD-SERG/lab-manual`'s move to a shared `lms` linter package (source:
[`UCD-SERG/lab-manual/.lintr.R`](https://github.com/UCD-SERG/lab-manual/blob/main/.lintr.R),
which calls `lms::default_linters()` from a package defined in that repo's own
`lms/` subdirectory) — the manual's own docs page 403'd, but its `.qmd`
source and the referenced `.lintr.R` file both fetched cleanly.)

## A canceled review can red-X require-review — don't chase it as a code bug

`claude-code-review.yml`'s `claude-review` job is concurrency-grouped per PR
(`claude-review-<PR>`, `cancel-in-progress: true`) across BOTH the automatic
`pull_request`-triggered review and claude.yml's comment-triggered (`@claude
review`) re-dispatch. When a push and an `@claude review` comment land close
together — or claude.yml's agent run finishes and re-dispatches a review a
minute or two later, landing on top of the next push's auto-review — the two
reviews race and one cancels the other.

The `require-review` gate job asserts `claude-review`'s result is `success`;
a *canceled* run (not skipped) makes that assertion fail, so `require-review`
shows red right after a push even though the surviving review is fine. Before
treating a post-push `require-review` failure as a real problem: check
whether `claude-review`'s conclusion is `cancelled` rather than `failure`. If
so, it's this race, not a code issue — wait for (or re-trigger) an
uncontested review instead of debugging the diff. To avoid causing it: don't
post `@claude review` immediately after pushing a commit on a PR using this
workflow; let the automatic review run alone, or wait for any in-flight
dispatched review to finish first. (See the `claude-review` job's
`concurrency:` comment in `.github/workflows/claude-code-review.yml` for the
full mechanism.)

**The same race fires from two plain pushes close together, not just a push
plus an `@claude review` comment.** Pushing two commits back-to-back (e.g. a
code fix, then a small follow-up doc/memory commit) triggers two separate
`pull_request`-type review runs; the second cancels the first via the same
concurrency group. Don't chase this either — and don't bother "fixing" the
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
commit — skip straight to "wait for the head commit's review" instead of
spending a tool call fetching the workflow run to confirm `cancelled` vs
`failure`. This shortcut is scoped to the two jobs that actually run under
`cancel-in-progress: true` (`claude-review`/`preview`) — `_selftest.yml`'s
jobs (`check-links`, `phi-tests`, `bib`, `coverage`, `review-fail-check`,
etc.) have no `concurrency:` block, so a `failure` there on a non-head SHA
is a real result the reader hasn't re-checked yet, not this race; don't
apply the shortcut outside `claude-review`/`require-review`/`preview`.
(`Lacaedemon/sparta` PR #780, 2026-07-12: two pushes 3 minutes apart
triggered exactly this on `require-review`; confirmed via `actions_get`
`get_workflow_run` that the failing check's conclusion was `cancelled` on
the non-head SHA, matching this pattern.)

## A PR fixing claude-code-review.yml (or claude.yml) itself can't self-verify before merge

This repo's own dogfood workflow (`.github/workflows/claude-review.yml`)
calls `Morrison-Lab/gha/.github/workflows/claude-code-review.yml@v2` — the
**released, floating tag**, not a local `./` ref (unlike `_selftest.yml`'s
handling of brand-new pre-release capabilities; see "About this repo" above).
`.github/workflows/claude-bot.yml` similarly calls
`Morrison-Lab/gha/.github/workflows/claude.yml@v2`. `@v2` only advances to
include a fix once that fix's PR merges to `main` and `slide-major-tag.yml`
runs.

So a PR that fixes a bug **in** either reusable workflow cannot exercise its
own fix via this repo's automatic review or agent dispatch — every review
(or agent re-dispatch) of that PR runs the **pre-fix** version, and will keep
hitting the exact bug being fixed until after merge. Seeing `review /
claude-review` or `review / require-review` fail on such a PR with the bug's
own signature is expected, not a regression in the diff; don't debug the new
code as the cause. The current workaround is to re-trigger the review (push,
or `@claude review` — see the race-avoidance note above) as many times as
needed, or just proceed to merge on the strength of a manual/offline review
once CI's other jobs and a careful read of the diff are clean. (Hit on
gha#201, whose diff fixed `claude-code-review.yml`'s stub-review bug
directly: every review of the PR itself failed with that exact signature —
`is_error:false`, a low `permission_denials_count`, no verdict — right up
until merge. gha#202 (a different fix, allowlisting `WebFetch`/`Bash(curl:*)`)
hit the identical signature as a bystander while it still edited
`claude-code-review.yml`'s inline `claude_args` block directly, before a
rebase onto #201 relocated that edit into the new `run-claude-review-attempt`
composite action — confirmed via that run's own execution output:
`permission_denials_count:1`, no verdict. Once `@v2` picked up #201's fix,
both PRs' subsequent reviews went clean.

The `claude.yml` side of this hit on gha#286, fixing gha#285's
`gh workflow run`-without-`--ref` bug: a plain `@claude review` comment on
PR #286 dispatched through `claude-bot.yml`'s `claude.yml@v2` — the
released, pre-fix tag — and reproduced the exact #285 symptom live
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
`contents:write` + `workflows:write` scope for this repo — it is not a bug in
`claude.yml`'s own token-resolution code. `claude.yml` already resolves
`PUSH_TOKEN` as `${{ secrets.WORKFLOW_TOKEN || secrets.GITHUB_TOKEN }}`, and
`claude-bot.yml` already passes `WORKFLOW_TOKEN` through; `GITHUB_TOKEN` alone
can never push a `.github/workflows/` change, so the fallback reproduces this
exact rejection whenever `WORKFLOW_TOKEN` isn't configured with the right
scope. Only someone with admin access to this repo's Settings -> Secrets and
variables -> Actions can fix it (a classic PAT with `repo` + `workflow`
scopes, or an equivalent GitHub App installation token) — an `@claude` session
has no path to set repository secrets itself. If you hit this, don't debug
`claude.yml`'s `PUSH_TOKEN` wiring; recover by pushing the already-committed
local branch from a differently-credentialed session/human, and flag that
`WORKFLOW_TOKEN` needs to be (re)configured. (Hit twice on 2026-07-24: PR #286
fixing #285, and PR #290 fixing #289, both editing `.github/workflows/*.yml`
— both required manual recovery; see gha#292.)

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
`github.workflow_ref`) and, when an automatic `pull_request` run edits that
file, skips every downstream step — checkout, run review, post review comment.
(Explicit mentions like `@claude review` or `workflow_dispatch` runs bypass
this skip so on-demand reviews still run.) `review / claude-review` and
`review / require-review` both report `success`, but on automatic runs every
step past the guard shows `skipped`, and no verdict comment is ever posted. This
is deliberate (the action's own App-token exchange 401s on an automatic workflow
file that doesn't match the default branch's content until merge — see the guard's
own comment), but a green `claude-review` check is easy to mistake for a real
review.

**The guard checks exactly one path, so it doesn't trip for every file this
section's title mentions.** `WF_PATH` comes from `github.workflow_ref` — in a
`workflow_call` run that's the CALLER's own workflow file, which in this
repo's dogfooding setup is `.github/workflows/claude-review.yml` (for a
downstream consumer, their own copy of the caller stub). Only an automatic PR
run that touches that one file trips `self_mod=true`. `claude.yml` is a separate
reusable workflow (the agent, not the reviewer) with no analogous self-mod
check — editing only `claude.yml` doesn't trip this guard at all (see the
`@v2`-tag paragraph above for that file's own self-verify gap).
`examples/claude-code-review.yml` lives under `examples/`, not
`.github/workflows/`, so it never actually executes as a workflow in this
repo and `github.workflow_ref` can never resolve to it either. Check the
job's step list, not just its conclusion, before trusting a green
`claude-review` on a PR that touches `.github/workflows/claude-review.yml`:
every step after the guard reading `skipped` means no review ran, regardless
of what `@v2` currently points at.

**This section's title says "a PR fixing" the review workflow, but the guard
does not check intent -- it checks whether `claude-review.yml` is in the
changed-file list on automatic runs.** So it also fires on an automatic PR run
that has nothing to do with the review system and touches that file only
incidentally: a repo-wide sweep, a lint fix, a formatting pass, a dependency bump.
(Mentioning `@claude review` explicitly will force a review on such PRs.)
That case is the dangerous one, because the two cases above at least give you
a reason to be suspicious of a green `claude-review`.
Here nothing prompts the thought -- the PR is "about" something else
entirely, `claude-review.yml` is one file among dozens, and the check is
green.

Before trusting a green `claude-review`, run
`git diff --name-only origin/main | grep claude-review.yml` rather than
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
  neither, so they resolved cleanly -- rather than from reasoning about
  which ones "probably" moved.

**A wall of access failures is not evidence that something cannot be
investigated.** In the same work, `get_check_run` returned `301`, the
MCP tools refused the new owner as out of scope, and the agent proxy
returned `403` for `api.github.com` -- three failures in a row, after which
a plain public `https://github.com/...` URL answered the question
immediately. Exhausting the authenticated routes is a reason to try an
unauthenticated one, not a reason to report the question as unanswerable.
The same principle already appears above for reading files out of
repositories this session is not scoped to.

## Code review guidelines

When reviewing a pull request (e.g. via `/review`, `/code-review`, or as a Claude
PR bot), evaluate the diff against **all** of the following, in addition to
correctness:

### 1. The SERG lab manual

The [UCD-SERG lab manual](https://ucd-serg.github.io/lab-manual/) is the lab's
authority on coding conventions. Hold changes to its standards, especially:

- [Coding style](https://ucd-serg.github.io/lab-manual/coding-style.html) —
  object naming, line breaks/formatting, function documentation, comments,
  message/communication style, and Quarto code-reference conventions (backticked
  `pkg::fn()`, markdown package links — no raw HTML in `.qmd`).
- [Coding practices](https://ucd-serg.github.io/lab-manual/coding-practices.html) —
  function decomposition and length limits, testing requirements, the QA
  checklist, documentation, `{here}` for paths, and tidyverse idioms.
- [Code repositories](https://ucd-serg.github.io/lab-manual/code-repositories.html) —
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
  ecosystem's conventions — idiomatic R (tidyverse), idiomatic YAML/GitHub
  Actions, idiomatic shell. Prefer the standard, well-known way over a clever or
  bespoke one. Match existing naming, structure, and formatting in the file.
- Keep these front-of-mind: surface modularity and idiom issues even when the
  code is otherwise correct.

Be specific and cite the relevant manual section or principle when raising a
point. Distinguish blocking issues from optional suggestions.

### 3. Challenge ambiguous phrasing and terminology

Flag ambiguous terms and phrasing rather than accepting a plausible-sounding
reading — a name that could mean more than one thing, a claim that cites a
value or construct without confirming it exists in the actual code. This is a
global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus.
Ambiguity accepted at face value is how a factually wrong claim (e.g.
documentation citing a nonexistent enum value) slips through review
unchallenged.

### 4. Fact-check prose against domain knowledge and external sources

When a diff touches prose (`README.md`, `CHANGELOG.md`, `website/`, action
descriptions), assess the accuracy and clarity of its claims — check each
against domain knowledge and, where checkable, an external source (the
referenced tool's own docs, a linked spec) — and check any document-internal
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
descriptions), scan it for the telltale signs of AI/LLM authorship —
overused vocabulary (delve, leverage, robust, seamless, tapestry,
testament…), the "it's not just X, it's Y" antithesis, mechanical
rule-of-three lists, hedging stacks, signposting filler, em-dash overuse,
bold-leading bullets, emoji headers, and promotional register. Flag each
tell found with its location and a de-slopped suggested revision — weigh
clustering, not an isolated instance. This is a global standing rule from
the [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/ai-tells.md`).

### 6. Hyperlink technical terms/results; no forward references

When a diff touches prose that defines technical terms or named results via
Quarto's theorem-like crossref divs (`::: {#def-...}`, `{#thm-...}`,
`{#lem-...}`, `{#cor-...}`, `{#prp-...}`, `{#cnj-...}`, `{#exm-...}`,
`{#exr-...}`), check that every mention of a term or result links to the
div that defines it, and that the div appears *before* its first mention in
reading order — a link to a definition the reader hasn't reached yet is a
forward reference. This scope is per rendered file: cross-chapter ordering
in a multi-file Quarto book is out of scope, check it manually. This is a
global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/definition-crossrefs.md`).

The same problem also shows up as plain-text signposting — "as discussed
below", "in the following section", "we'll cover this later" — pointing at
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
60–80 characters) instead of reflowing into long unbroken lines — a semantic
break keeps a diff scoped to the changed sentence. Raise violations as a
suggestion, not a blocking requirement, and don't re-raise it if the author
declines. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/semantic-line-breaks.md`).

### 8. Check code and math for strategic and tactical correctness

Beyond style, check whether the diff's code — and any math or statistics
embedded in it — is *right*, not just correctly styled:

- **Strategic correctness.** Is this the right algorithm or design for the
  problem? A clean implementation of the wrong approach (wrong data
  structure for the scale, a statistical method whose assumptions don't
  hold for this data, a concurrency strategy prone to races) is still
  wrong.
- **Tactical correctness.** Given the chosen approach, does the code
  correctly execute it — no off-by-one errors, sign errors, wrong
  comparison operators, mis-transcribed formulas, unit/dimension
  mismatches, or numerical instability.
- **Math/stats in code.** Verify a formula, statistical test, or model
  against its source (a paper, a spec, a package's reference
  implementation) with the same rigor that item 4 applies to a derivation
  in prose.

Distinguish a strategic finding (needs a different approach) from a
tactical one (needs a correction within the existing approach) — the fix
differs. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/coding/fact-check-code-logic.md`, added in
[ai-config#455](https://github.com/Morrison-Lab/ai-config/pull/455)).

### 9. Challenge unnecessary complexity

When reviewing prose, math, or code, check whether it is more complex than
the problem requires — not just whether it's correct or clear. Flag
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
consolidated without losing completeness or generality — a claim or
explanation restated in two places, a formula re-derived as a special case
the general form already covers, duplicated logic across functions/files.
Flag it only when nothing would be lost by merging; genuinely distinct
content that merely looks similar should stay separate. This is a global
standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/workflow/challenge-redundant-content.md`).

### 11. Write and recommend tidy, concise code

Beyond style-guide compliance, check whether the diff's code is genuinely
tidy — no leftover debug output, no dead branches, no function doing three
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
(`@inheritParams`, `@inheritDotParams`, `@inheritSection`) — reused docs stay
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
proof, a statistical argument), check that every step is shown — no two or
more operations (distribution, cancellation, substitution, applying a named
identity or assumption) combined into a single displayed line. When a step is
missing, name the exact gap (the last line before the jump and the first line
after it), name the specific operation that closes it, and draft the missing
line(s) where feasible rather than only flagging "skipped steps" in general.
This is distinct from item 8's derivation-validity check (whether each
*stated* step follows correctly) — this one catches a step that isn't
stated at all. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/writing/math-derivation-steps.md`).

### 14. Don't reinvent the wheel

When a diff adds a new function or feature, check whether that
functionality has already been done — in one of the lab's own repos
(the lab packages, this repo's reusable workflows and actions), or in a
trustworthy external source the code could depend on instead (base R,
[r-lib](https://github.com/r-lib),
[tidyverse](https://github.com/tidyverse), a focused, well-maintained
CRAN package, a vetted, well-maintained GitHub Actions marketplace
action — SHA-pinned per `README.md`'s "Pinning third-party actions"
subsection). Flag a hand-rolled
equivalent of functionality that already exists: name the existing
implementation, and prefer depending on it — or forking and/or
contributing to it — over re-building from scratch. Accept the custom
version when the existing option is genuinely unfit (wrong API,
unmaintained, license-incompatible, or a heavy dependency for a
one-liner), and ask for a note in the PR description or a code comment
— "checked existing options, nothing fit" — when it's missing. This is a global standing rule from the
[`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) corpus
(`shared/coding/prefer-packaged-functions.md` states the R-function
case); its umbrella statement lives at
`shared/principles/dont-reinvent-wheel.md` there, added in
[ai-config#603](https://github.com/Morrison-Lab/ai-config/pull/603).
