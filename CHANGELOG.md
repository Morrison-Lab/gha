# Changelog

All notable changes to `d-morrison/gha` are documented here.

This repo uses a **moving major tag** (`v1`) for consumers, following the
[`r-lib/actions`](https://github.com/r-lib/actions) convention: the `v1` tag
moves forward as non-breaking fixes land, and consumers pin to `@v1`. Each
release is also tagged with a full `vX.Y.Z` so a specific point can be pinned
if needed. Breaking changes bump the major tag (`v2`, …) and are called out
below with migration steps.

## [Unreleased]

### Added

- **`test-coverage` — R-package test coverage with Codecov upload** (#147). A new
  composite (`test-coverage/action.yml`) and reusable workflow
  (`.github/workflows/test-coverage.yml`) that set up R and dependencies, run
  `covr::package_coverage()`, and upload the Cobertura report with
  `codecov/codecov-action`. Adapts the canonical `r-lib/actions`
  `test-coverage.yaml` example into the repo's composite-plus-wrapper shape.
  Inputs: `path` (package root, defaults to repo root), `install-quarto`,
  `extra-packages`, and `fail-ci-if-error` (`'auto'` by default, applying the
  r-lib heuristic -- fail on non-PR events, and on PRs only when a token is set,
  since tokenless PR uploads are flaky -- or force `'true'`/`'false'`); the
  optional `CODECOV_TOKEN` secret is passed through the caller's `secrets:`
  block. See `examples/test-coverage.yml` for the caller stub.

- **`check-equation-renders` — catch equations MathJax can't render in PR previews**
  (#159). A new fourth leg of the PR-preview family: a composite
  (`check-equation-renders/action.yml`) that crawls a built Quarto/HTML site with a
  headless Chromium (Playwright), lets MathJax finish typesetting each page, and
  fails on either of the two ways MathJax signals a broken formula: a hard parse
  error (a `[data-mjx-error]` node), or an undefined macro, which MathJax renders
  as literal, unresolved `\command` text rather than a hard error (no error node
  to find, so the check looks for the raw command name surviving into the
  rendered output instead). Wired into
  the family as a reusable workflow (`.github/workflows/check-equation-renders.yml`)
  triggered the same way as `preview-deploy.yml` (`workflow_run` on the build
  workflow's completion), downloading the `pr-preview-site` artifact directly rather
  than depending on the deploy. Motivated by a broken equation
  (`d-morrison/rme#954`) that shipped silently: Quarto's `html-math-method: mathjax`
  embeds raw TeX unchanged in the static HTML, and MathJax only parses it
  client-side, so a bad equation produces no warning in the Quarto/pandoc build log.
  Ships at `@v2` (too new for the frozen `@v1` tag), like `test-coverage`. See
  `examples/check-equation-renders.yml` for the caller stub.

### Changed

- **`claude-code-review` now honors an explicit review request on a draft PR.**
  A dispatched review (an `@claude review` comment routed here by `claude.yml`,
  `claude.yml`'s post-push re-dispatch, the issue-trigger draft PR, or a manual
  dispatch) already bypassed the workflow's draft-skip `if:` gate, but the
  code-review skill's *own* don't-review-drafts stop condition still made the
  agent refuse ("currently a draft … I will not proceed"), so an explicit
  `@claude review` on a draft produced a refusal instead of a review. The
  dispatched-run prompt now overrides that stop condition so an
  explicitly-requested review runs even on a draft. Automatic `pull_request`
  reviews still skip drafts (their `if:` gate never reaches the agent on a
  draft), so this only widens the dispatched path.

- **`claude-code-review` no longer flags cosmetic source-only formatting that
  renders identically** (#261). The review prompt now tells the reviewer to skip
  raw-source line-wrap position and line-length nits on Markdown/text prose when
  the rendered output is unchanged, and to flag only genuine prose problems
  (ambiguity, meaning-changing grammar, broken links or markup, factual errors).
  This cuts review-round churn from cosmetic wrapping nits.

## [2.0.0] - 2026-06-25

### Breaking

- **`quarto-publish` now deploys to the `gh-pages` branch** instead of the
  GitHub Pages artifact (#118, #120). Consumers must set Settings → Pages →
  Source = "Deploy from a branch", branch `gh-pages` / `(root)`, and grant the
  caller `contents: write` (dropping `pages: write` + `id-token: write`) — still
  required with `deploy: false`. This makes `quarto-publish` compatible with the
  branch-based PR-preview family, so a repo can ship both a main site and PR
  previews. Full migration steps are in the `quarto-publish` entry under Added.
  `@v1` stays frozen on the Pages-artifact deploy for consumers not ready to
  migrate.

### Added

- Dark mode for the documentation website (#114) — `website/_quarto.yml` now
  pairs the `cosmo` light theme with the `darkly` dark theme, so the site renders
  a light/dark toggle in the navbar and respects the reader's system preference.
- Documentation website (#100) — a Quarto site under `website/` that documents
  every reusable workflow (overview, a per-action reference page with full input
  tables, permissions, and versioning). It is built and shipped by the repo's own
  actions: `quarto-publish` deploys it to GitHub Pages on `main`, and the
  `preview` family renders a per-PR preview.
- `preview` gains a `path` input (#100) — the project directory to render
  (the dir holding `_quarto.yml`), defaulting to the repo root. This brings
  `preview` to parity with `quarto-publish` and lets a site that lives in a
  subdirectory (like this repo's `website/`) get a PR preview. Backward
  compatible: existing callers that render the repo root need no change.
- Shared-content sync family (#57) — keeps guidance shared between repos current
  in both directions, via two reusable workflows and a shared helper:
  - `bump-submodule.yml` — update a named submodule to its upstream HEAD and open
    a PR when the pointer moves (one direction; e.g. the lab manual tracking
    `.ai-config`).
  - `sync-shared-fragments.yml` — vendor a set of files from an upstream repo,
    pinned to a commit and recorded in a JSON manifest, and open a PR when they
    change (the other direction; avoids a recursive mutual submodule).
  - `open-sync-pr` composite — the commit-and-open-PR helper both workflows
    reuse: commits staged changes to a reused automation branch and opens or
    updates the PR, no-op when nothing changed. First consumers:
    `UCD-SERG/lab-manual` and `d-morrison/ai-config`.
- `quarto-publish` — render a Quarto site and deploy it to the `gh-pages`
  branch, which GitHub Pages serves. A composite (`quarto-publish/action.yml`)
  sets up Quarto (optionally R/renv and TinyTeX) and renders a project at a
  given `path` into `<path>/<output-dir>` (default `_site`). The reusable
  workflow (`quarto-publish.yml`) deploys that output to `gh-pages` with
  `clean-exclude: pr-preview/`, so a main-site deploy never wipes the preview
  family's per-PR sites; it also offers optional submodule init and a
  `pre-render-artifact` input so a caller can inject build-time assets (e.g.
  recorded media) before render. Callers grant `contents: write` (still
  required with `deploy: false`, since the deploy job is part of the workflow)
  and set Pages Source = "Deploy from a branch", branch `gh-pages`. First
  consumer: `Lacaedemon/sparta` (#37).

  **Breaking change for early `@v1` adopters (#117).** An earlier interim
  version deployed via `actions/deploy-pages` and needed Pages Source =
  "GitHub Actions". That is incompatible with the PR-preview family, which is
  branch-based, so previews 404'd. Switching `quarto-publish` to a `gh-pages`
  deploy makes publish and preview consistent. To migrate: (1) set Settings ->
  Pages -> Source = "Deploy from a branch", branch `gh-pages` / `(root)`; and
  (2) change the caller's job permissions from `pages: write` + `id-token:
  write` to `contents: write` (see `examples/quarto-publish.yml`).
- PR-preview / publish family (#33) — centralizes the three-workflow preview
  pipeline rme carried inline:
  - `preview` composite action + `preview.yml` reusable workflow — build half;
    renders the Quarto site read-only in the (possibly fork) PR context and
    uploads it + PR metadata as an artifact. Parameterized for non-rme
    consumers (R version, apt packages, renv on/off, local-package install,
    Chrome, submodules, render profile). Writes PR metadata **after** checkout
    so `git clean -ffdx` can't wipe it from the artifact (d-morrison/rme#913),
    and keeps the `preview:pdf`/`preview:docx`/`preview:revealjs` and
    `clear freezer` label gates.
  - `preview-deploy.yml` reusable workflow — deploy half; on `workflow_run`
    completion publishes the artifact to `gh-pages` in the base-repo context
    and comments the preview link. Kept split from the build half so untrusted
    fork code never holds write permissions (the trust boundary).
  - `cleanup-pr-previews.yml` reusable workflow — scheduled housekeeping that
    deletes preview directories for closed PRs.
- `check-phi` — scans pull requests (added lines only; whole tree on `push`)
  for content that looks like PHI: US Social Security numbers, medical record
  numbers, dates of birth, and PHI-suggestive column headers in delimited data
  files. Matched values are never printed to the log; false positives are
  suppressed via a `phi-allow` line comment or a regex allowlist file. The
  `phone`/`email` detectors are available but off by default.
- `CHANGELOG.md` (this file) — records what changes as the `@v1` tag moves, so
  consumers can see what they picked up.
- `REVDEPS.md` — tracks repos that consume these workflows so breaking changes
  can be announced. See the file for how to register.
- `.github/actions/checkout-submodules` composite action — centralizes the
  submodule-init logic (the `SUBMODULES_TOKEN` `insteadOf` rewrite and the
  anonymous-clone fallback) shared by the `claude` and `claude-code-review`
  reusable workflows (#25).

### Changed

- Multi-line `run:` blocks in the composite actions and reusable workflows now
  declare `set -euo pipefail` explicitly. GitHub already runs `shell: bash`
  with `-eo pipefail`; the net new protection is `nounset` (unset-variable
  typos now fail fast), plus consistency with the rest of the script logic.
- `claude` and `claude-code-review` no longer carry duplicate `Checkout
  submodules` steps; both call the shared `checkout-submodules` action instead,
  so the token-rewrite logic lives in one place (#25).
- `check-bibliography-dois` now collects `.bib` files NUL-delimited into a bash
  array, so bibliography paths containing spaces are passed to the checker as
  intact single arguments instead of word-splitting (#30).
- `claude-code-review`'s prompt now instructs the reviewer to watch for AI
  hallucinations — fabricated functions/arguments/APIs, invented references,
  DOIs, or URLs, plausible-but-unreal file paths and constants, and comments
  that describe behavior the code doesn't implement — and to verify questionable
  symbols against the codebase rather than assuming they exist (#56).
- `claude` now reproduces qwt's late-comment dedup so a follow-up `@claude`
  comment absorbed by a still-running session isn't double-handled by the
  duplicate run it also queued: a "Skip if this comment was already handled"
  pre-step bows out when the triggering comment already carries a github-actions
  🚀 marker, the agent emits a `<!-- claude-absorbed: … -->` marker listing the
  comments it absorbed by polling, and a post-step reacts 🚀 to each so their own
  queued runs short-circuit. A companion step re-dispatches a review for a late
  `@claude review` that a deduped run would otherwise have dropped. Additive —
  no consumer input changes (#44, ported from qwt #73/#90/#95).
- `claude-code-review` gained an `allowed-bots` input (default
  `github-actions[bot]`, previously hard-coded) so a consumer can widen the
  accepted dispatch actors (e.g. `github-actions[bot],claude`), and a
  "Skip self-review when the PR edits this workflow" step that detects (via
  `github.workflow_ref`) a PR modifying the caller's review workflow and skips
  the review — which would otherwise 401 on the action's workflow-validation
  until merged — instead of posting a failed check (#45, ported from qwt).

### Fixed

- **Example caller stubs now pass secrets explicitly instead of `secrets:
  inherit`.** GitHub only inherits org/repo secrets into a reusable workflow
  owned by the *same* org/user, so a cross-owner consumer (e.g. a `UCD-SERG`-org
  repo calling these `d-morrison`-user-owned workflows) inherited an empty
  `CLAUDE_CODE_OAUTH_TOKEN` and every `@claude` run failed env-validation
  ("… is required when using direct Anthropic API"). `examples/claude.yml` and
  `examples/claude-code-review.yml` now pass `CLAUDE_CODE_OAUTH_TOKEN` (and the
  optional `SUBMODULES_TOKEN` / `WORKFLOW_TOKEN`) explicitly, which resolves
  caller-side and works regardless of owner. Existing consumers copied from the
  old stubs must make the same change (#49).
- `claude-code-review` now sets `allowed_bots: github-actions[bot]`, so the
  review `claude.yml` re-dispatches after an `@claude` run pushes commits can
  actually run. The action's agent mode (used by `workflow_dispatch`) blocks
  bot actors by default, so dispatched reviews previously failed with "Workflow
  initiated by non-human actor" — and, having entered the per-PR concurrency
  group, canceled the parallel `synchronize` auto-review on their way out,
  leaving the push with no review at all.
- `claude-code-review`'s "collapse previous review comments" step is no longer
  gated to `pull_request`, so a dispatched (`workflow_dispatch`) review that
  wins the per-PR concurrency race also folds earlier pushes' review comments as
  OUTDATED instead of leaving them expanded.

### Security

- **All third-party actions are now pinned to full commit SHAs** (with the
  human-readable version in a trailing comment), following GitHub's
  [recommended hardening posture](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions).
  A SHA is immutable, so a re-pointed tag or a compromised upstream can no longer
  silently change what runs — most important for the `preview-deploy` job, which
  runs in the base-repo context with `contents: write` + `pull-requests: write`.
  Added [`.github/dependabot.yml`](.github/dependabot.yml) (`github-actions`
  ecosystem, weekly, grouped, covering `.github/workflows/` and each composite
  action) so the pins are auto-bumped as upstreams publish releases instead of
  freezing. First-party `d-morrison/gha/*@v1` self-references and the
  `examples/` templates intentionally still track the `@v1` major tag (#48).

## [v1] — initial pilot set

Reusable workflows + composite actions:

- `check-bibliography-dois` — validate book/article BibTeX entries have
  resolvable DOIs matching CrossRef metadata.
- `check-links` — lychee link check with bundled config, PR skip-label, and
  auto-issue on `main`.
- `check-non-standard-chars` — detect curly quotes / en–em dashes in `.qmd`
  and `.R` files.
- `check-news` — enforce a `NEWS.md` changelog entry on PRs (wraps
  `UCD-SERG/changelog-check-action`).
- `summary` — AI summary comment on newly opened issues.

[Unreleased]: https://github.com/d-morrison/gha/compare/v1...main
[v1]: https://github.com/d-morrison/gha/releases/tag/v1
