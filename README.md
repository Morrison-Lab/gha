# Morrison-Lab/gha

Central, reusable GitHub Actions for d-morrison / UCD-SERG / ucdavis R-package
and Quarto repositories. Modeled on
[`r-lib/actions`](https://github.com/r-lib/actions) and
[`easystats/workflows`](https://github.com/easystats/workflows): repos call a
reusable workflow with a tiny stub instead of carrying their own copy.

This repo is **public** so it can be referenced from repositories across the
`d-morrison`, `ucdavis`, `UCD-SERG`, `UCLA-PHP`, and `UCD-IDDRC` owners.

## How it works

Each capability is shipped as two layers:

- **Composite action** (e.g. `check-bibliography-dois/action.yml`) -- bundles the
  real steps and any helper script. Referenced as
  `Morrison-Lab/gha/<name>@vN` (the major tag that capability currently
  recommends -- see [Versioning](#versioning) below).
- **Reusable workflow** (`.github/workflows/<name>.yml`, `on: workflow_call`) --
  wraps the composite, declares permissions, and checks out the caller's repo.
  This is what consumer repos target.

A consumer repo adds a small caller stub (see [`examples/`](examples)):

```yaml
name: Check Bibliography DOIs
on:
  push: { branches: [main] }
  pull_request:
  workflow_dispatch:
jobs:
  check:
    uses: Morrison-Lab/gha/.github/workflows/check-bibliography-dois.yml@v2
```

Pin to the major tag that capability currently recommends (`@v2` in the
example above) -- see [Versioning](#versioning) below for the full breakdown,
since it varies per capability rather than defaulting uniformly to `@v1`. Do
not reference `@main` from consumers.

## Available reusable workflows

| Workflow | Purpose | Key inputs |
|---|---|---|
| `check-ai-tells.yml` | Scan narrative prose in Markdown and Quarto files for AI-generated tell density and rhetorical markers | `paths`, `paths-ignore`, `base-ref`, `threshold`, `ignore-tells`, `fail` |
| `check-bibliography-dois.yml` | Validate book/article BibTeX entries have resolvable DOIs matching CrossRef metadata | `exclude-keys`, `install-quarto`, `no-metadata-check` |
| `check-junk-files.yml` | Fail when the repository **tracks** operating-system or editor detritus (`.DS_Store`, AppleDouble `._*`, `.Rhistory`, `.RData`, `Thumbs.db`), naming the `git rm --cached` fix and the global-gitignore / `usethis::git_vaccinate()` fix that stops it recurring | `patterns`, `paths-ignore`, `fail` |
| `check-non-standard-chars.yml` | Detect curly quotes, en/em dashes, and the multiplication sign in `.qmd`, `.R`, and `.md` files | `python-version`, `extensions` |
| `check-phi.yml` | Scan PRs (added lines only) for content that looks like PHI -- SSNs, medical record numbers, dates of birth, study/participant identifier literals, PHI column headers in data files | `detectors`, `paths-ignore`, `allowlist-file`, `fail` |
| `check-secrets.yml` | Scan the repository's git **history** for committed credentials (API tokens, private keys, high-entropy password assignments) with gitleaks | `version`, `checksums-sha256`, `config`, `paths-ignore`, `allowlist-file`, `log-opts`, `fail` |
| `check-links.yml` | lychee link check with bundled config, PR skip-label, and auto-issue on `main` | `lychee-config`, `lychee-args`, `fail`, `fail-if-empty`, `create-issue-on-main`, `skip-label` |
| `lint-yaml.yml` | yamllint over tracked YAML with a bundled config, plus a check that flags long `run:` script blocks as decomposition candidates | `python-version`, `config-file`, `paths-ignore`, `fail`, `max-script-lines`, `fail-on-long-scripts` |
| `lint-markdown.yml` | markdownlint-cli2 over tracked Markdown with a bundled config, plus checks for long fenced code blocks, list-item merge splices, and blank lines that split a table | `config-file`, `globs`, `paths-ignore`, `fail`, `max-code-block-lines`, `fail-on-long-code-blocks`, `base-ref`, `fail-on-item-splices`, `fail-on-table-splits` |
| `check-new-line-breaks.yml` | Diff-scoped check that flags newly-added Markdown lines packing more than one sentence/clause onto one source line | `python-version`, `globs`, `paths-ignore`, `fail`, `clause-breaks`, `clause-min-length` |
| `lint-qmd.yml` | markdownlint over the prose sections of tracked `.qmd` Quarto files (code chunks stripped, YAML front matter skipped natively) with a bundled default config; default 80-char line-length ceiling encourages semantic line breaks | `config-file`, `globs`, `paths-ignore`, `fail`, `max-line-length` |
| `lint-changed-lines.yml` | lintr over only the lines a PR adds or modifies (not whole changed files), so lint rules can be adopted or tightened incrementally | `path`, `install-quarto`, `extra-packages`, `install-package`, `fail` |
| `lint-workflows.yml` | actionlint (syntax/semantics) and zizmor (security) over the caller's GitHub Actions workflows and composite actions | `path`, `actionlint-version`, `actionlint-checksum`, `zizmor-version`, `python-version`, `pedantic`, `fail` |
| `spellcheck.yml` | Spellcheck an R package's prose -- `DESCRIPTION`'s `Title`/`Description`, `man/*.Rd`, vignette sources, and root `README`/`NEWS`/`CHANGES`/`index` Markdown -- with {spelling}, accepting the package's own `inst/WORDLIST` | `path`, `exclude`, `additional-options`, `install-quarto` |
| `summary.yml` | AI summary comment on newly opened issues | -- |
| `check-news.yml` | Enforce a `NEWS.md` changelog entry on PRs (wraps `UCD-SERG/changelog-check-action`) | `changelog`, `no-changelog-label` |
| `test-coverage.yml` | Measure R-package test coverage with `covr` and upload the Cobertura report to Codecov | `path`, `install-quarto`, `extra-packages`, `fail-ci-if-error`, `upload-test-results` |
| `update-snapshots.yml` | Regenerate testthat snapshots, accept the new output, commit, and push -- the workflow only verifies the suite passes against the accepted snapshots; their correctness is judged at PR review of the pushed commit | `ref`, `pr-mode`, `julia`, `extra-packages`, `apt-packages`, `commit-message` |
| `claude.yml` | Agent-mode Claude Code bot: responds to `@claude` mentions, edits files, opens/updates PRs | `setup-r`, `install-quarto`, `use-renv`, `apt-packages`, `pip-packages`, `checkout-submodules`, `link-skills`, `eager-pr`, `prompt-addendum`, `webfetch-allowlist-url`, `use-ai-config`, `plugin-marketplaces`, `plugins`, `reviewer`, `report-cost`, `trusted-bot-logins`, `dispatch-on-assignee` |
| `claude-code-review.yml` | Read-only Claude PR review (default stub runs on `workflow_dispatch` from `@claude review`; add `pull_request` in the caller for automatic reviews) | `pr-number`, `prompt-addendum`, `checkout-submodules`, `allowed-bots`, `track-progress`, `apt-packages`, `pip-packages`, `lab-manual`, `check-latex-macros`, `use-ai-config`, `plugin-marketplaces`, `plugins`, `report-cost`, `model` |
| `gemini.yml` | Agent-mode Gemini CLI bot: responds to `@gemini` and `@gemini-cli` mentions, edits files, opens/updates PRs | `setup-r`, `install-quarto`, `use-renv`, `renv-cache-version`, `r-extra-packages`, `apt-packages`, `pip-packages`, `checkout-submodules`, `eager-pr`, `reviewer`, `mark-ready-for-review`, `prompt-addendum`, `gemini-model`, `review-workflow-file` |
| `gemini-code-review.yml` | Read-only Gemini PR code review (default stub runs on `workflow_dispatch` from `@gemini review`; add `pull_request` in the caller for automatic reviews) | `pr-number`, `prompt-addendum`, `checkout-submodules`, `gemini-model` |
| `antigravity-code-review.yml` | Automated agentic code review, security audit, or test-suite generation via Google Antigravity SDK (`google-antigravity`) | `mode`, `pr-number`, `prompt-addendum`, `trigger-policy`, `checkout-submodules`, `model` |
| `cursor-code-review.yml` | Queue a Cursor Bugbot PR review via the Enterprise Bugbot API (`POST /bugbot/review`); success means queued | `pr-number`, `dry-run` |
| `opencode-code-review.yml` | Read-only OpenCode PR code review running the opencode CLI headless (default stub runs on `workflow_dispatch`; add `pull_request` in the caller for automatic reviews) | `pr-number`, `prompt-addendum`, `checkout-submodules`, `opencode-model`, `opencode-version`, `opencode-attempts` |
| `ai-code-review.yml` | Multi-agent PR review: picks one configured AI agent at random and dispatches its review workflow, falling through when one can't be dispatched or fails during execution | `agents`, `pr-number`, `claude-review-workflow-file`, `gemini-review-workflow-file`, `antigravity-review-workflow-file`, `cursor-review-workflow-file`, `opencode-review-workflow-file` |
| `small-model-agent.yml` | Small or self-hosted model PR agent: runs a small-model agent against a PR diff with bounded verification gates (`wai#39`, `ai-config#1292`) | `pr-number`, `endpoint-url`, `model`, `max-iterations`, `setup-r`, `install-quarto`, `apt-packages`, `pip-packages`, `checkout-submodules`, `run-gates`, `dry-run` |
| `request-dependabot-review.yml` | Request review from configured reviewers when a PR's author matches a bot actor (Dependabot by default) | `reviewers`, `bot-actor` |
| `quarto-publish.yml` | Render a Quarto site and deploy it to GitHub Pages | `path`, `setup-r`, `r-packages`, `use-renv`, `tinytex`, `apt-packages`, `output-dir`, `checkout-submodules`, `pre-render-artifact`, `pre-render-artifact-path`, `deploy` |
| `report-failure.yml` | File an issue when a watched job fails, or comment on the issue already open for that failure | `title`, `body`, `labels` |
| `preview.yml` | Build half of the PR-preview family: render a Quarto site in the (possibly fork) PR context and upload it + PR metadata as an artifact (read-only) | `path`, `r-version`, `apt-packages`, `use-renv`, `install-package`, `setup-chrome`, `submodules`, `render-profile` |
| `preview-deploy.yml` | Deploy half: on `workflow_run` completion of the build, publish the artifact to `gh-pages` and comment the preview link (base-repo context) | -- |
| `check-equation-renders.yml` | On the same `workflow_run` completion, crawl the build artifact with a headless browser and fail on equations MathJax can't render | `fail` |
| `cleanup-pr-previews.yml` | Housekeeping: delete `gh-pages` preview directories for PRs that are no longer open, and (optionally) orphan-squash `gh-pages` to one commit so deleted snapshots stop bloating the repo | `preview-dir`, `compact-history` |
| `altdoc-multiversion-docs.yml` | Render an altdoc-based R package's Quarto docs and deploy multiple versions side by side on `gh-pages` (`/dev/`, `/latest-tag/`, `/vX.Y.Z/`, plus PR previews and a root redirect) | `r-packages`, `needs`, `apt-packages`, `setup-julia`, `checkout-submodules`, `default-branch`, `quarto-config-path`, `docs-base-url`, `preview-branch`, `timeout-minutes`, `rewrite-pr-preview-links`, `rewrite-issue-links`, `dispatch-version`, `dispatch-release-tag`, `legacy-paths`, `version-dropdown-title-template`, `version-in-navbar-title` |
| `bump-submodule.yml` | Update a named submodule to its upstream HEAD and open a PR when the pointer moves | `submodule-path`, `remote-branch`, `base-branch`, `pr-branch` |
| `sync-shared-fragments.yml` | Vendor files from an upstream repo (pinned to a commit, recorded in a manifest) and open a PR when they change -- avoids a recursive mutual submodule | `source-repo`, `source-ref`, `source-paths`, `dest-dir`, `manifest-path` |
| `sync-upstream.yml` | Merge an upstream repo's branch into a fork and open a PR when the merge brings changes -- keeps a fork current while preserving its own changes | `upstream-repo`, `upstream-branch`, `base-branch`, `pr-branch`, `fail-on-conflict` |
| `bump-dev-version.yml` | Bump an R package's `DESCRIPTION` dev-version counter after every merge to `main`, and open/auto-merge a PR to carry it in -- so PRs never need to touch `Version:` themselves | `description-path`, `base-branch`, `pr-branch`, `auto-merge`, `dry-run`, `pr-labels` |
| `version-check.yml` | Fail a PR whose `DESCRIPTION` `Version:` differs from the base branch's -- pairs with `bump-dev-version.yml` | `description-path`, `no-version-increment-label`, `bump-branch` |

## Permissions

A called reusable workflow cannot hold more `GITHUB_TOKEN` permissions than the
caller grants, and most repos default to a **read-only** token. So workflows
that need to write must have the **caller** grant it on the calling job:

- `check-links` (opens an issue on `main` failures) → grant `issues: write`,
  `pull-requests: read`, `contents: read`.
- `report-failure` (files or updates the issue tracking a failing workflow) →
  grant `issues: write` on the reporting job only; the job it watches keeps
  its own permissions.
- `summary` (comments on issues, calls the models API) → grant `issues: write`,
  `models: read`, `contents: read`.

- <!--readonly-workflows:begin-->`check-ai-tells`, `check-bibliography-dois`,
  `check-equation-renders`, `check-junk-files`,
  `check-new-line-breaks`, `check-news`,
  `check-non-standard-chars`, `check-phi`, `check-secrets`,
  `cursor-code-review`, `lint-changed-lines`, `lint-markdown`, `lint-qmd`,
  `lint-workflows`, `lint-yaml`, `preview`, `spellcheck`, `test-coverage`,
  `version-check`<!--readonly-workflows:end--> → only
  `contents: read` (the default), so no `permissions:` block is needed.
  This list is checked against the workflows' own `permissions:` blocks by
  `.github/workflows/scripts/tests/run-permissions-docs-tests.py`; keep the
  markers around it.
  `test-coverage` additionally takes an optional `CODECOV_TOKEN` secret, and
  `cursor-code-review` a `CURSOR_API_KEY` secret, each passed through the
  caller's `secrets:` block.
- `update-snapshots` (pushes the snapshot-update commit back to the branch) →
  grant `contents: write`.
- `quarto-publish` (deploys to the `gh-pages` branch, which Pages serves) →
  grant `contents: write`, and set Settings → Pages → Source = "Deploy from a
  branch", branch `gh-pages` / `(root)` once. Grant `contents: write` even with
  `deploy: false` -- the deploy job is part of the workflow, so the caller must
  grant its permissions even when it is skipped.
- `altdoc-multiversion-docs` (deploys to `gh-pages`, comments PR previews, and
  rewrites rendered links) → grant `contents: write`, `pull-requests: write`,
  and `issues: write`, and set Settings → Pages → Source = "Deploy from a
  branch", branch `gh-pages` / `(root)` once.
- `claude` (pushes branches, opens PRs, dispatches the review workflow) → grant
  `contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`,
  `actions: write`, and add either the `CLAUDE_CODE_OAUTH_TOKEN` or
  `ANTHROPIC_API_KEY` secret.
  - **Optional:** if Claude will edit files under `.github/workflows/`, also add
    a `WORKFLOW_TOKEN` secret (a PAT or GitHub App token with `contents:write` +
    `workflows:write`). The integrated `GITHUB_TOKEN` cannot push workflow-file
    changes --
    GitHub rejects them without the `workflows` scope. Repos that never

    touch `.github/workflows/` can omit it; pushes fall back to `GITHUB_TOKEN`.
    Note that, unlike `GITHUB_TOKEN`, a PAT/App-token push **does** trigger other
    `push`-based workflows, so enabling `WORKFLOW_TOKEN` can set off extra CI runs.
    When the secret is absent and Claude does edit a workflow file, the rejected
    push is reported as an error naming this secret, and Claude's commits are
    posted to the thread as a `git format-patch` so they survive the run.
  - **Optional:** set `checkout-submodules: true` so Claude can read submodule
    contents. Public submodules clone anonymously; private ones additionally need
    a `SUBMODULES_TOKEN` secret.
- `gemini` (pushes branches, opens PRs, dispatches the review workflow) → grant
  `contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`,
  `actions: write`, and add the `GEMINI_API_KEY` secret.
  - **Optional:** if Gemini will edit files under `.github/workflows/`, also add
    a `WORKFLOW_TOKEN` secret.
  - **Optional:** set `checkout-submodules: true` so Gemini can read submodule
    contents. Public submodules clone anonymously; private ones additionally need
    a `SUBMODULES_TOKEN` secret.
- `claude-code-review` (read-only review) → grant `contents: read`,
  `pull-requests: write`, `issues: write`, `id-token: write`, and either the
  `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` secret.
  - **Optional:** set `checkout-submodules: true` so the reviewer can read
    submodule contents instead of reporting them as uninitialized. Public
    submodules clone anonymously; private ones additionally need a
    `SUBMODULES_TOKEN` secret.

- `cursor-code-review` (queues a Cursor Bugbot review) is read-only, above,
  but does need the `CURSOR_API_KEY` secret (Enterprise, `admin:*` scope).
  Bugbot posts with the Cursor GitHub App, so this workflow needs no write
  permission on the PR.

- `opencode-code-review` (read-only OpenCode PR review) → grant `contents: read`,
  `pull-requests: write`, `issues: write`, and set an `OPENCODE_API_KEY`
  secret (an [OpenCode Zen](https://opencode.ai/docs/zen/) API key; free-tier
  models are available).
  Without the secret, reviews skip gracefully with a warning comment on each
  PR.
  The agent runs with edit/bash/webfetch denied, reads the diff as an
  attachment and the checkout for context, and posts its review through the
  workflow -- it never touches git or `gh`.

  - **Optional:** set `checkout-submodules: true` so the reviewer can read
    submodule contents instead of reporting them as uninitialized.
    Public submodules clone anonymously; private ones additionally need a
    `SUBMODULES_TOKEN` secret.

- `preview-deploy` (deploy half, pushes `gh-pages` + comments) → grant
  `contents: write`, `pull-requests: write`, `actions: read`.
  The `preview` build half is read-only, above.

- `check-equation-renders` downloads the build artifact, so a caller that
  narrows below the read-only default token still needs `actions: read`
  alongside `contents: read`.

- `cleanup-pr-previews` (commits deletions to `gh-pages`) → grant
  `contents: write`, `pull-requests: read`.
- `bump-submodule`, `sync-shared-fragments`, `sync-upstream` (open a PR) → grant
  `contents: write`, `pull-requests: write`, and enable Settings → Actions →
  General → "Allow GitHub Actions to create and approve pull requests" so the
  integrated `GITHUB_TOKEN` can open the PR. For private submodules,
  `bump-submodule` also needs a `SUBMODULES_TOKEN` secret; `sync-upstream` takes
  an `UPSTREAM_TOKEN` for a private upstream. Add a `WORKFLOW_TOKEN` only to push
  to a protected branch; otherwise pushes fall back to `GITHUB_TOKEN`.
- `request-dependabot-review` (requests a reviewer on the PR) → grant
  `pull-requests: write`.
- `bump-dev-version` (opens/auto-merges a PR) → grant `contents: write`,
  `pull-requests: write`, and the same "Allow GitHub Actions to create and
  approve pull requests" setting as above; enable "Allow auto-merge" too for
  its default `auto-merge: true`. Add a `WORKFLOW_TOKEN` to push to a protected
  branch, and -- when `auto-merge` runs against required status checks -- to let
  the bump PR's checks run so it can merge at all (a `GITHUB_TOKEN`-authored PR's
  checks never report; see the reference page).
  A fine-grained PAT needs **Pull requests: Read and write** on that secret in
  addition to **Contents: write**.
  The workflow probes pull-request write access before any bump work.
  Its `version-check` counterpart is read-only, above.

The stubs in [`examples/`](examples) already include the right `permissions:`
blocks -- copy them as-is.

The two Claude workflows are a pair: an `@claude review` mention (or any commit
Claude pushes) routes through `claude.yml`, which dispatches `claude-code-review.yml`
via `workflow_dispatch`. Install both, and keep the review stub named
`claude-code-review.yml` (or set `claude.yml`'s `review-workflow-file` input to
match) so the dispatch resolves.

The `examples/claude-code-review.yml` stub defaults to this mention-triggered
path only (no automatic `pull_request` trigger). Add `pull_request` in that
stub if you want automatic review on each PR update.

Do not declare a top-level `concurrency:` block in caller stubs for review
workflows (`claude-code-review.yml`, `gemini-code-review.yml`,
`antigravity-code-review.yml`, `cursor-code-review.yml`,
`opencode-code-review.yml`, `ai-code-review.yml`).
The reusable workflows manage per-PR concurrency internally on their review
jobs.
A top-level `concurrency:` block in the caller with a PR-scoped group name
deadlocks GitHub Actions against the nested job's group and cancels the run
([gha#437](https://github.com/Morrison-Lab/gha/issues/437)).

You can also start a review **directly**, without waking the `@claude` agent, by
commenting `/review` at the start of a PR comment -- but that path is opt-in:
enable the `issue_comment` trigger in `examples/claude-code-review.yml` first.
Then `claude-code-review.yml` listens for that comment and re-dispatches its own
`workflow_dispatch` review of the PR, and it works for
`OWNER`/`MEMBER`/`COLLABORATOR` commenters once the workflow is on your default
branch (widen the caller `if:` with a bot-login allowlist if a GitHub App such
as `cursor[bot]` should be able to post `/review`.
App comments usually have `author_association: NONE`.
It's a slash command rather than an `@claude review` mention on
purpose: any `@claude` substring would also trigger `claude.yml`, so the slash
command keeps the direct path independent.

For `@claude` / `@claude review` from an App bot, pass the same logins to
`claude.yml`'s `trusted-bot-logins` input **and** mirror them in the caller
job `if:` -- the reusable gate alone never runs if the caller skips first.

That reasoning holds only while `claude.yml` is enabled.
If you have switched the agent **off**, nothing answers `@claude` at all, and a
mention produces a one-second run with every job skipped and no comment posted.
In that case do two things, not one: enable the `issue_comment` trigger in the
stub, and set the repository variable `CLAUDE_AGENT_DISABLED` to `true`.
`dispatch-on-comment` only ever runs on an `issue_comment` event, so the
variable on its own changes nothing, and you get the same silence.
With both in place the stub accepts `@claude review` alongside `/review`.
Leave the variable unset whenever the agent is live, or both workflows answer
the same mention and dispatch two paid reviews of possibly different heads.

## Claude session visibility

GHA sessions (both `claude.yml` and `claude-code-review.yml`) run as headless
CI jobs and **cannot be remote-controlled or observed** from the
[claude.ai](https://claude.ai) web interface. The CLI's "Join session" feature
requires a live interactive terminal; `anthropics/claude-code-action` has no
parameter to enable it, and GitHub Actions runners don't expose that hook.

The table below lists what is available instead. Its "Action argument" column
gives the argument passed to `anthropics/claude-code-action`; these are **not**
caller-facing `workflow_call` inputs unless the "Caller-configurable?" column
says so.

| Feature | Action argument | Caller-configurable? |
|---|---|---|
| Live progress tracking comment on the PR | `track_progress` | Yes -- driven by the `track-progress` input of `claude-code-review.yml` (default `false`; tag mode with tracking comment and inline-comment tool when `true`, agent/summary-only mode when `false`). Not used in `claude.yml`. See `track-progress` warning in the inputs table: tag mode exposes git write tools until anthropics/claude-code-action#1415 lands. |
| Full Claude SDK output in the job log | `show_full_output` | Yes -- driven by the `show-full-output` input of `claude-code-review.yml` (note the hyphen; off by default, turn on to diagnose silent auth / quota failures). Not surfaced in `claude.yml`. |
| Resume a prior session | `session_id` (internal step output of `anthropics/claude-code-action`) + `--resume` in `claude_args` | No -- neither reusable workflow declares `session_id` as a `workflow_call` output, so session resume is not available to consumers of `claude.yml` or `claude-code-review.yml`. |
| Dollar cost of the run | n/a (action *output*, not an argument) -- `total_cost_usd` on the execution output's `result` event | Yes, indirectly -- verified against `anthropics/claude-code-action` v1.0.162 (the SHA this repo pins): `src/entrypoints/format-turns.ts` writes the cost only to `GITHUB_STEP_SUMMARY`, and `src/github/operations/comment-logic.ts`'s comment builder receives `total_cost_usd` but never reads it when composing the comment. Both workflows extract that output and post it in a comment instead, gated on the `report-cost` input (default `true`). |

## PHI scanning (`check-phi`)

`check-phi` is a **heuristic tripwire, not a HIPAA compliance tool.** It flags
patterns that should almost never be committed -- US Social Security numbers,
medical record numbers, dates of birth, study/participant identifier literals,
and PHI-suggestive column headers in
delimited data files (`.csv`/`.tsv`/`.psv`) -- so a human reviews before the
data merges. It is tuned for high precision (few false positives), so it will
miss free-text PHI such as patient names. The `phone` and `email` detectors
exist but are **off by default** (too noisy in source); enable them via the
`detectors` input.

- **Diff-scoped on PRs.** Only lines *added* by the PR are scanned, so existing
  fixtures don't re-trip the check on unrelated edits. `push` runs scan the
  whole tracked tree (`git ls-files`).
- **Values are never printed.** A leaked identifier in a CI log is still a leak,
  so findings report only `file:line:col` and the detector name -- never the
  matched text. Findings appear as inline annotations on the PR.
- **Suppressing false positives** (e.g. synthetic test data): add a `phi-allow`
  comment on the line, or list a regex matching the value in an allowlist file
  (defaults to `.github/phi-allowlist.txt` when present; override with the
  `allowlist-file` input). Use `fail: false` to downgrade to warnings.

## Secret scanning (`check-secrets`)

`check-secrets` is `check-phi`'s counterpart for **credentials**.
`check-phi` detects identifiers and has no notion of a password or a token,
so a committed credential passes it cleanly.
This one runs [gitleaks](https://github.com/gitleaks/gitleaks) over the
repository,
catching API tokens, private keys, and high-entropy password assignments.

It shares `check-phi`'s stance in most respects,
and departs from it in three that matter.

- **It scans history, not the diff.**
  Every other check here is diff-scoped,
  so a fixture committed long ago does not re-trip it.
  That is the wrong default for a credential:
  a secret committed and then removed in a later commit is still exposed,
  because the orphaned commit stays fetchable through the GitHub API until
  the repository is garbage-collected.
  So the caller must check out with `fetch-depth: 0`,
  and a shallow clone is **refused** rather than reported clean on a partial
  scan.
  The scan reaches further than "history" suggests, too:
  gitleaks defaults to `git log -p -U0 --full-history --all`,
  so it covers **every ref** the checkout holds rather than only `HEAD`'s
  ancestry.
  A finding can therefore name a commit that is not an ancestor of the PR's
  own head,
  which is right for a credential -- an exposed one is exposed wherever it
  sits.
  Narrow it with `log-opts` only deliberately.
- **It blocks by default** (`fail: true`),
  where non-blocking prose checks only annotate.
  A leaked credential is not a style nit.
- **Its `paths-ignore` patterns are Go regexes, not globs**,
  because they become gitleaks allowlist entries directly,
  and gitleaks matches them **unanchored**.
  So `docs` suppresses every path containing that substring,
  `mydocs-secrets.env` included;
  anchor with `^` when that matters.
  Write `tests/fixtures/`, not `tests/fixtures/**`.
  The two glob forms fail differently, which is why the check warns rather
  than trusting you to notice:
  `**` does not compile, since Go rejects nested repetition,
  but a trailing `/*` is a perfectly valid regex that silently widens the
  match.

Otherwise it behaves as `check-phi` does.
**Values are never printed** -- a credential in a CI log is still a
credential -- so findings report only the rule, `file:line`, and the commit.
Suppress a false positive with a `gitleaks:allow` comment on the line,
a fingerprint in a `.gitleaksignore` file,
a regex in the `allowlist-file`
(defaults to `.github/secrets-allowlist.txt` when present;
one regex per line, and a comma there is regex syntax rather than a
separator, so a `{16,20}` quantifier is safe),
or a path in `paths-ignore`.
Site-specific credential formats the default ruleset does not know go in a
gitleaks TOML named by the `config` input (`.gitleaks.toml` by default),
which the generated config extends rather than replaces.

Two limits worth stating plainly.

**It complements GitHub's native secret scanning; it does not replace it.**
That is a repository setting,
it evaluates pushes rather than running as a PR check,
and no reusable workflow can supply it.
Enable both.

**Neither substitutes for rotating an exposed credential.**
Rewriting history does not un-expose one.
Treat any value this check names as compromised,
and rotate it before doing anything else.

### Why not `gitleaks/gitleaks-action`

The vendor's own action is proprietary:
its `action.yml` carries a commercial EULA header,
and its README states `GITLEAKS_LICENSE` is "required for organizations,
not required for user accounts".
Every consumer of this repo is an organization.
The gitleaks **CLI** is MIT,
so the composite installs the official release binary instead.
Integrity comes from one pinned constant:
the release's own `checksums.txt` is fetched and compared against the
`checksums-sha256` input,
and only then trusted to verify the platform tarball --
one value covering every architecture.
Bump `version` and `checksums-sha256` together.

## PR previews (`preview` family)

The PR-preview family publishes a rendered Quarto site for each open PR to a
`pr-preview/pr-<n>/` directory on `gh-pages`. It is **four** cooperating
workflows -- install all four stubs from [`examples/`](examples):

1. **`preview.yml`** (build) -- triggered on `pull_request`. Renders the site and
   uploads it plus the PR metadata as a `pr-preview-site` artifact. Runs
   **read-only** in the (possibly fork) PR context, so it can't write to the
   base repo.
2. **`preview-deploy.yml`** (deploy) -- triggered on `workflow_run` completion of
   the build. Downloads the artifact and publishes it to `gh-pages` in the
   **base-repo** context (where the token can write), then comments the preview
   link on the PR.
3. **`check-equation-renders.yml`** -- also triggered on `workflow_run`
   completion of the build. Downloads the same artifact and crawls it with a
   headless browser, failing when MathJax can't typeset an equation -- a failure
   mode invisible to the Quarto/pandoc build log, since MathJax only runs
   client-side.
   Runs independently of the deploy (no `gh-pages` write needed),

   not sequenced after it.
4. **`cleanup-pr-previews.yml`** (housekeeping) -- scheduled. Removes preview
   directories for PRs that have closed. Set `compact-history: true` to also
   orphan-squash `gh-pages` to a single commit each run, so the deleted
   snapshots don't accumulate and bloat the repo (branch-based Pages only).

The build/deploy split is a **trust boundary**: untrusted fork code only ever
runs in the read-only build half, while the privileged `gh-pages` push happens
in the deploy half against base-repo code. Don't collapse them into one job.

Two wiring requirements:

- The deploy stub's and the equation-check stub's `on: workflow_run: workflows:`
  value **must match the build stub's `name:`** (all default to `Quarto Preview
  Build` in the examples). That string is how `workflow_run` finds the build.
- `workflow_run` and `schedule` triggers only fire for the copy of the file on
  the **default branch**, so previews and cleanup don't take effect until the
  stubs are merged to `main`.

The build half is parameterized for non-rme consumers (R version, the apt
package list, renv on/off, `R CMD INSTALL .` on/off, Chrome, submodules, render
profile). Label-gated extras are preserved: add `preview:pdf`, `preview:docx`,
or `preview:revealjs` to a PR to render those formats too, and `clear freezer`
to bypass the Quarto freeze cache.

## Content sync (`bump-submodule`, `sync-shared-fragments`, `sync-upstream`)

Three workflows keep a repo current with content that lives elsewhere, without
hand-bumping.
The first two are the two directions of sharing single-source-of-

truth content between a pair of repos; the third tracks an upstream a fork was
cut from.

- **`bump-submodule`** -- for the side that vendors the other repo as a git
  submodule. A scheduled run advances the submodule to its upstream HEAD and
  opens a PR when it moved. (Used by `UCD-SERG/lab-manual`, which carries
  `Morrison-Lab/ai-config` as `.ai-config`.)
- **`sync-shared-fragments`** -- for the side that can't add a submodule because
  the other repo already submodules *it* (a mutual submodule would recurse).
  Instead it vendors a pinned **copy** of the named files into a `dest-dir`,
  records the source repo and commit in a JSON manifest, and opens a PR when the
  copy changes. (Used by `Morrison-Lab/ai-config` to vendor the lab manual's
  authored fragments.) Don't hand-edit the vendored copies -- edit them upstream
  and let the workflow refresh them; a consumer-side drift check can assert the
  copy matches the pinned commit.
- **`sync-upstream`** -- for a fork that tracks the project it was cut from. A
  scheduled run merges the upstream branch into a fork-owned automation branch
  and opens a PR when the merge brings changes, so the fork's own changes are
  preserved and upstream's updates are reviewed before they land. On a clean
  merge the PR is mergeable; on a conflict it carries the conflict markers for
  manual resolution (or set `fail-on-conflict` to fail the run instead). (Used
  by `d-morrison/altdoc`, a fork of `etiennebacher/altdoc`.)

All three reuse the `open-sync-pr` composite, which commits staged changes to a
reused automation branch and opens or updates one PR (no-op when nothing
changed). Schedule and `workflow_dispatch` triggers live in the caller stubs.
For `bump-submodule`/`sync-shared-fragments`, scope each side to the *other*
repo's shared content (not its own pointer/manifest) so the two auto-PRs don't
ping-pong.

## Versioning

Releases are tagged `vX.Y.Z`; the `vX` major tag moves to the latest compatible
release.
`@v1` was frozen at the pre-`2.0.0` snapshot when the breaking
`quarto-publish` change cut `@v2`, so any capability pinned there has picked up
no fixes since -- including non-breaking ones, like `cleanup-pr-previews`'s
`compact-history` input, which does not exist at `@v1` at all.
Pin

`preview.yml`, `preview-deploy.yml`, `cleanup-pr-previews.yml`, and
`quarto-publish.yml` to `@v2`; `test-coverage.yml`, `check-equation-renders.yml`,
`lint-yaml.yml`, `lint-markdown.yml`, `lint-qmd.yml`, `lint-changed-lines.yml`,
`check-new-line-breaks.yml`, `check-secrets.yml`, `check-junk-files.yml`,
`lint-workflows.yml`, and
`spellcheck.yml`
only ever shipped at `@v2` (too new to exist at the frozen `@v1` tag).
`quarto-publish.yml` additionally has a genuine

behavioral fork: `@v1` deploys via the GitHub Actions Pages artifact, while
`@v2` deploys to the `gh-pages` branch instead -- required alongside the
PR-preview family (`preview.yml` / `preview-deploy.yml`), since Pages can only
have one Source.
`check-bibliography-dois.yml`, `check-phi.yml`,

`check-links.yml`, `check-non-standard-chars.yml`, `claude.yml`,
`claude-code-review.yml`, and `update-snapshots.yml` also pin `@v2`: each
picked up a real fix since the freeze (a dependency-pin bump, a new input, or
a security fix) that a consumer still on `@v1` would miss (audited in
[gha#182](https://github.com/Morrison-Lab/gha/issues/182)).
`request-dependabot-review.yml` only ever shipped at `@v2` too (it postdates
the freeze -- see [gha#252](https://github.com/Morrison-Lab/gha/issues/252)), as
does `sync-upstream.yml` (added after the freeze -- see
[gha#254](https://github.com/Morrison-Lab/gha/issues/254)),
`altdoc-multiversion-docs.yml` (added after the freeze), and
`report-failure.yml` (added after the freeze -- see
[gha#325](https://github.com/Morrison-Lab/gha/issues/325)).
`bump-dev-version.yml` and `version-check.yml` postdate the freeze too (added
in [gha#388](https://github.com/Morrison-Lab/gha/issues/388)); pin both to
`@v2`.
`small-model-agent.yml` postdates the freeze too
(added in [gha#436](https://github.com/Morrison-Lab/gha/issues/436));
pin to `@v2`.
`check-ai-tells.yml` postdates the freeze too (added in
[gha#382](https://github.com/Morrison-Lab/gha/issues/382)); pin to `@v2`.
`cursor-code-review.yml` postdates the freeze too (added in
[gha#510](https://github.com/Morrison-Lab/gha/issues/510)); pin to `@v2`.
`opencode-code-review.yml` postdates the freeze as well
(added in [gha#586](https://github.com/Morrison-Lab/gha/issues/586)); pin to
`@v2`.
`summary.yml`, `bump-submodule.yml`, and `sync-shared-fragments.yml` were
audited in the same pass and found unchanged since the freeze, so `@v1`
remains current for them. `check-news.yml` was initially grouped with them,
but later gained the configurable `no-changelog-label` input at
[gha#143](https://github.com/Morrison-Lab/gha/issues/143) -- pin it to `@v2`
too. See [`CHANGELOG.md`](CHANGELOG.md) for
what changes as a major tag moves and for any breaking-change migration steps.

### Advancing a major tag

A major tag no longer slides automatically on every push to `main` -- merging a
change does not, by itself, change what any consumer pinned to `@v1`/`@v2`
picks up next. Advancing the tag is a deliberate, manual step, so a change can
be tried out before every consumer has to deal with it:

1. Merge the change to `main`.
2. Optionally, validate it against one or a few consumer repos first: point a
   consumer's `uses:` line at `@main`, at a specific commit SHA, or temporarily
   at a feature branch of this repo, then let that consumer's own CI run
   against the unreleased change.
3. Once you're confident, advance the shared major tag to `main`'s current tip
   -- either by running
   [`slide-major-tag.yml`](.github/workflows/slide-major-tag.yml) via
   `workflow_dispatch` (Actions tab → "Slide major-version tag" → Run workflow,
   from `main`), or with `git tag -f`/`git push --force` directly (the
   `ai-config` repo's `slide-tag` skill automates this). Every consumer pinned
   to that tag picks up the change the next time its CI runs.

**A brand-new capability's own PR merging to `main` does not make it usable
at `@v2` yet.** If a consumer repo's PR needs to reference
`Morrison-Lab/gha/.github/workflows/<new-workflow>.yml@v2` right after that
workflow's own PR merged here, check whether `@v2` has actually been
advanced past that merge first (`git log -1 refs/tags/v2` vs. `main`) --- a
consumer referencing `@v2` before the slide gets a workflow-not-found error,
not a stale-but-working reference. ([gha#300](https://github.com/Morrison-Lab/gha/pull/300)/[ai-config#703](https://github.com/Morrison-Lab/ai-config/pull/703), 2026-07-25:
`check-new-line-breaks` merged here, but `@v2` was still 11 commits behind;
the tag had to be slid via step 3 above before ai-config's own migration PR
could actually resolve it.)

**Tag drift staleness signal.**
To prevent the manual slide step from going unnoticed when `main` moves
ahead of the major tag, a tag drift check (`check-tag-drift`) runs as part of
CI to surface when `main` has unreleased commits ahead of the active major
tag (e.g. `v2`).
It emits a GitHub Actions notice and job summary pointing to
[`slide-major-tag.yml`](.github/workflows/slide-major-tag.yml) whenever tag
advancement is pending.

Changelog entries are added as fragment files under
[`changelog.d/`](changelog.d) (one per PR, so parallel PRs never conflict on the
shared changelog) and collated into `CHANGELOG.md` at release time -- see
[`changelog.d/README.md`](changelog.d/README.md).

### Pinning third-party actions

Every **third-party** action is pinned to a full commit SHA, with the
human-readable version in a trailing comment, e.g.:

```yaml
uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
```

This is GitHub's [recommended hardening posture](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions):
a SHA is immutable, so a re-pointed tag or a compromised upstream can't silently
change what runs -- which matters here because jobs like the preview deploy run
with `contents: write` + `pull-requests: write`. [`.github/dependabot.yml`](.github/dependabot.yml)
bumps these pins as upstreams publish releases, so they stay current instead of
freezing. When adding a new third-party action, pin it the same way.

First-party `Morrison-Lab/gha/*` self-references and most [`examples/`](examples/)
templates intentionally track the moving major tag (currently `@v1`, except
`preview.yml`, `preview-deploy.yml`, `cleanup-pr-previews.yml`,
`quarto-publish.yml`, `test-coverage.yml`, `check-equation-renders.yml`,
`check-bibliography-dois.yml`, `check-phi.yml`, `check-links.yml`,
`check-non-standard-chars.yml`, `claude.yml`, `claude-code-review.yml`,
`update-snapshots.yml`, `lint-yaml.yml`, `lint-markdown.yml`,
`lint-qmd.yml`, `lint-changed-lines.yml`, `check-new-line-breaks.yml`,
`check-secrets.yml`, `check-junk-files.yml`, `request-dependabot-review.yml`,
`sync-upstream.yml`, `check-news.yml`, `altdoc-multiversion-docs.yml`,
`report-failure.yml`, `gemini.yml`, `gemini-code-review.yml`,
`antigravity-code-review.yml`, `cursor-code-review.yml`, `opencode-code-review.yml`, `ai-code-review.yml`, `bump-dev-version.yml`,
`check-ai-tells.yml`, `version-check.yml`, `lint-workflows.yml`, and
`spellcheck.yml` at `@v2` -- see the
Versioning section above), and so are **not** SHA-pinned.

### Job timeouts

Every job that runs steps sets `timeout-minutes`, so a hung step fails in
minutes instead of occupying a runner until GitHub's six-hour default expires.
The values are deliberately generous -- roughly 10 minutes for gate and
dispatch jobs, 20 for checks and lints, 45 for builds and deploys, 60 for the
agent workflows -- because the goal is catching a hang, not budgeting a normal
run.

A job that calls a reusable workflow cannot set `timeout-minutes` itself
(GitHub rejects the key on a `uses:` job), so such a job inherits whatever
timeout the called workflow's own job declares.
`altdoc-multiversion-docs.yml` additionally exposes its timeout as a
`workflow_call` input, which is the pattern to follow if a consumer ever needs
to raise one.

## Reverse dependencies

[`REVDEPS.md`](REVDEPS.md) tracks repos that call these workflows, so consumers
can be notified before a breaking change. If your repo uses `gha`, please add
it there.

## Notes for private consumers

Reusable workflows in this public repo are callable from public repos
automatically. A **private** consumer must allow access to this repo under
*Settings → Actions → General → Access* before it can call these workflows.

## Scope

This started as the pilot set (the byte-identical / near-identical workflow
families) plus the PR-preview/publish family. Additional families (spell check,
lint-changed-files, pr-commands, R-CMD-check) may be added later.
