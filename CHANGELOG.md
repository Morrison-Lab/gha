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

### Changed

- **`claude-code-review` grants the reviewer `Bash(python3:*)`.** The review
  agent could previously only trace a Python script's logic by eye, since its
  `--allowedTools` covered just the inline-comment tool plus the action's
  base allowlist (Read/Glob/Grep and narrow git-read Bash) — no way to
  actually execute the script under review (rme#970). The job's sandbox is
  already read-only (`contents: read`, no git-write tools), so letting it run
  Python doesn't widen what it can persist or push; it can now verify a
  script's behavior instead of guessing from source alone (#154).

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

- **`test-coverage`'s R runtime image now includes Python** (#146). R sessions
  spawned from `setup-r` previously had no `python3` on `PATH`, so any
  package invoking `reticulate` failed at coverage time. Adds a
  `python-version` input (default `'3.11'`) and an `actions/setup-python`
  step before `setup-r`, run only when `use-renv` is false (renv resolves its
  own Python via `renv::use_python()`), consistent with `r-lib/actions`'
  `check-standard.yaml` pattern.
