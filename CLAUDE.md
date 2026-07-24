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
`lint-qmd`, `lint-changed-lines`, `request-dependabot-review`, `sync-upstream`,
and `altdoc-multiversion-docs` -- see
the Versioning section
of `README.md`).
`@v1` was frozen at the pre-`2.0.0` snapshot and has picked up no fixes since,
which is why the capabilities above moved to `@v2`.

### Layout

- Per-capability composite-action directories at the repo root, each with an
  `action.yml` and, for R/Python capabilities, a language-specific helper
  script — e.g. `check-bibliography-dois/` (R), `check-non-standard-chars/` and
  `check-phi/` (Python). `check-links/` bundles `lychee.default.toml`;
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
  `d-morrison/ai-config`);
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
  tried to locate that script by resolving d-morrison/gha's own repo/ref from
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
  and "Push branch and finalize PR for issue trigger") read the shared
  `steps.cost.outputs.cost` — a single extraction instead of duplicating the
  jq filter at both call sites (gha#219 review finding 1).
- `.github/actions/sum-costs/` — wraps `scripts/sum-costs.sh`, which sums two
  (each optionally empty) `total_cost_usd` values. `claude-code-review.yml`'s
  "Sum attempt costs" step calls it once, combining the initial attempt's
  cost with the gha#185 stub-retry attempt's cost when one ran, so the
  arithmetic has offline test coverage instead of being an inline `awk`
  one-liner only exercised by a live two-attempt review run (gha#219 review
  finding 5).
- `.github/actions/build-reviewer-args/` — wraps
  `scripts/build-reviewer-args.sh`, which splits a comma-separated reviewers
  list into a JSON array of trimmed, non-empty usernames.
  `request-dependabot-review.yml` calls it once to build its `gh api -f
  reviewers[]=...` arguments, so the split/trim logic has offline test
  coverage instead of only being exercised by a live Dependabot PR (gha#253
  review: a bare `IFS=',' read -ra` doesn't trim whitespace, so `"alice,
  bob"` sent an invalid `reviewers[]= bob` and failed the job).
- `.github/actions/generate-altdoc-version-dropdown/` and
  `.github/actions/generate-altdoc-landing-page/` - Python composites wrapping
  the two scripts `altdoc-multiversion-docs.yml` needs (rewrite the navbar
  "Versions" dropdown; generate the root redirect landing page). Ported from
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
  carrying its own copy.
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
that workflow calls `build-reviewer-args` via `d-morrison/gha/...@v2`, which
won't resolve until `@v2` is advanced past this capability's merge (the same
`test-coverage` bootstrapping gap the Layout section's `_selftest.yml`/
local-ref paragraph describes) — so `dependabot-review` tests the composite
directly, the same
"local composite, not the full reusable-workflow chain" precedent `coverage`
below uses for `test-coverage.yml` (gha#253 review: missing selftest coverage
for a new workflow with real side effects, precedented by the `sync-pr` job's
`open-sync-pr` no-op test).

The `altdoc-docs` job in `_selftest.yml` exercises
`generate-altdoc-version-dropdown`, `generate-altdoc-landing-page`, and
`resolve-altdoc-base-url` (see Layout above) directly against a throwaway
fixture: a separate git-init'd
package directory (not this checkout) with two release tags, asserting the
composite picks the correct latest/previous tags and dev version and rewrites
the navbar "Versions" block and root-redirect HTML correctly. It does not
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

This repo is `d-morrison/gha`, so MCP calls use `owner: d-morrison`, `repo: gha`.

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
calls `d-morrison/gha/.github/workflows/claude-code-review.yml@v2` — the
**released, floating tag**, not a local `./` ref (unlike `_selftest.yml`'s
handling of brand-new pre-release capabilities; see "About this repo" above).
`.github/workflows/claude-bot.yml` similarly calls
`d-morrison/gha/.github/workflows/claude.yml@v2`. `@v2` only advances to
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

**A third, more direct mechanism produces the identical symptom without
`@v2` even entering the picture.** `claude-code-review.yml`'s own `Skip
self-review when the PR edits this workflow` step compares the PR's changed
files against the CALLER's review-workflow path (derived from
`github.workflow_ref`) and, when the PR itself edits that file, skips every
downstream step — checkout, run review, post review comment. `review /
claude-review` and `review / require-review` both report `success`, but
every step past the guard shows `skipped`, and no verdict comment is ever
posted. This is deliberate (the action's own App-token exchange 401s on a
workflow file that doesn't match the default branch's content until merge —
see the guard's own comment), but a green `claude-review` check is easy to
mistake for a real review. Check the job's step list, not just its
conclusion, before trusting a green `claude-review` on a PR that touches
`claude-review.yml`/`claude.yml`/`examples/claude-code-review.yml`: every
step after the guard reading `skipped` means no review ran, regardless of
what `@v2` currently points at. (gha#286: an `@claude review` comment
produced only a `$0.60` cost comment, no verdict — the guard had set
`self_mod=true` and skipped straight through.)

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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus.
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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
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
the [`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
(`shared/writing/definition-crossrefs.md`).

The same problem also shows up as plain-text signposting — "as discussed
below", "in the following section", "we'll cover this later" — pointing at
content the reader hasn't reached yet, in *any* prose, not just documents
with crossref divs. Flag these too: confirm each hit is a genuine reference
(not an idiom like "values below the threshold") and that the target really
comes later, then suggest reordering the content earlier or rewording the
pointer into a working link. This is a global standing rule from the
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
(`shared/writing/forward-references.md`, added in
[ai-config#507](https://github.com/d-morrison/ai-config/pull/507)), with a
dedicated `fix-forward-references` (`ffr`) skill there that applies
the fix directly rather than only flagging it in review.

### 7. Suggest semantic line breaks in prose

When a diff touches prose (`README.md`, `CHANGELOG.md`, `website/`, action
descriptions), check that lines break at clause/sentence boundaries (roughly
60–80 characters) instead of reflowing into long unbroken lines — a semantic
break keeps a diff scoped to the changed sentence. Raise violations as a
suggestion, not a blocking requirement, and don't re-raise it if the author
declines. This is a global standing rule from the
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
(`shared/coding/fact-check-code-logic.md`, added in
[ai-config#455](https://github.com/d-morrison/ai-config/pull/455)).

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
from the [`d-morrison/ai-config`](https://github.com/d-morrison/ai-config)
corpus (`shared/workflow/challenge-unnecessary-complexity.md`).

### 10. Question redundant content

When a diff touches prose, math, or code, check for content that could be
consolidated without losing completeness or generality — a claim or
explanation restated in two places, a formula re-derived as a special case
the general form already covers, duplicated logic across functions/files.
Flag it only when nothing would be lost by merging; genuinely distinct
content that merely looks similar should stay separate. This is a global
standing rule from the
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
(`shared/coding/reuse-docs-and-args.md`, added in
[ai-config#474](https://github.com/d-morrison/ai-config/pull/474)).

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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
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
[`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) corpus
(`shared/coding/prefer-packaged-functions.md` states the R-function
case); its umbrella statement lives at
`shared/principles/dont-reinvent-wheel.md` there, added in
[ai-config#603](https://github.com/d-morrison/ai-config/pull/603).
