# d-morrison/gha

Central, reusable GitHub Actions for d-morrison / UCD-SERG / ucdavis R-package
and Quarto repositories. Modeled on
[`r-lib/actions`](https://github.com/r-lib/actions) and
[`easystats/workflows`](https://github.com/easystats/workflows): repos call a
reusable workflow with a tiny stub instead of carrying their own copy.

This repo is **public** so it can be referenced from repositories across the
`d-morrison`, `ucdavis`, `UCD-SERG`, `UCLA-PHP`, and `UCD-IDDRC` owners.

## How it works

Each capability is shipped as two layers:

- **Composite action** (e.g. `check-bibliography-dois/action.yml`) — bundles the
  real steps and any helper script. Referenced as
  `d-morrison/gha/<name>@v1`.
- **Reusable workflow** (`.github/workflows/<name>.yml`, `on: workflow_call`) —
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
    uses: d-morrison/gha/.github/workflows/check-bibliography-dois.yml@v1
```

Pin to `@v1` (a moving major tag updated as fixes land). Do not reference
`@main` from consumers.

## Available reusable workflows

| Workflow | Purpose | Key inputs |
|---|---|---|
| `check-bibliography-dois.yml` | Validate book/article BibTeX entries have resolvable DOIs matching CrossRef metadata | `exclude-keys`, `install-quarto`, `no-metadata-check` |
| `check-non-standard-chars.yml` | Detect curly quotes / en–em dashes in `.qmd` and `.R` files | `python-version` |
| `check-phi.yml` | Scan PRs (added lines only) for content that looks like PHI — SSNs, medical record numbers, dates of birth, PHI column headers in data files | `detectors`, `paths-ignore`, `allowlist-file`, `fail` |
| `check-links.yml` | lychee link check with bundled config, PR skip-label, and auto-issue on `main` | `lychee-config`, `lychee-args`, `fail`, `fail-if-empty`, `create-issue-on-main`, `skip-label` |
| `summary.yml` | AI summary comment on newly opened issues | — |
| `check-news.yml` | Enforce a `NEWS.md` changelog entry on PRs (wraps `UCD-SERG/changelog-check-action`) | `changelog` |
| `test-coverage.yml` | Measure R-package test coverage with `covr` and upload the Cobertura report to Codecov | `path`, `install-quarto`, `extra-packages`, `fail-ci-if-error` |
| `claude.yml` | Agent-mode Claude Code bot: responds to `@claude` mentions, edits files, opens/updates PRs | `setup-r`, `install-quarto`, `use-renv`, `apt-packages`, `pip-packages`, `checkout-submodules`, `link-skills`, `eager-pr`, `prompt-addendum`, `webfetch-allowlist-url`, `reviewer` |
| `claude-code-review.yml` | Read-only Claude PR review (runs the `code-review` plugin; inline findings on `pull_request` runs, consolidated summary on dispatched runs) | `pr-number`, `prompt-addendum`, `checkout-submodules`, `allowed-bots`, `apt-packages`, `pip-packages` |
| `quarto-publish.yml` | Render a Quarto site and deploy it to GitHub Pages | `path`, `setup-r`, `r-packages`, `use-renv`, `tinytex`, `apt-packages`, `output-dir`, `checkout-submodules`, `pre-render-artifact`, `pre-render-artifact-path`, `deploy` |
| `preview.yml` | Build half of the PR-preview family: render a Quarto site in the (possibly fork) PR context and upload it + PR metadata as an artifact (read-only) | `path`, `r-version`, `apt-packages`, `use-renv`, `install-package`, `setup-chrome`, `submodules`, `render-profile` |
| `preview-deploy.yml` | Deploy half: on `workflow_run` completion of the build, publish the artifact to `gh-pages` and comment the preview link (base-repo context) | — |
| `cleanup-pr-previews.yml` | Housekeeping: delete `gh-pages` preview directories for PRs that are no longer open, and (optionally) orphan-squash `gh-pages` to one commit so deleted snapshots stop bloating the repo | `preview-dir`, `compact-history` |
| `bump-submodule.yml` | Update a named submodule to its upstream HEAD and open a PR when the pointer moves | `submodule-path`, `remote-branch`, `base-branch`, `pr-branch` |
| `sync-shared-fragments.yml` | Vendor files from an upstream repo (pinned to a commit, recorded in a manifest) and open a PR when they change — avoids a recursive mutual submodule | `source-repo`, `source-ref`, `source-paths`, `dest-dir`, `manifest-path` |

## Permissions

A called reusable workflow cannot hold more `GITHUB_TOKEN` permissions than the
caller grants, and most repos default to a **read-only** token. So workflows
that need to write must have the **caller** grant it on the calling job:

- `check-links` (opens an issue on `main` failures) → grant `issues: write`,
  `pull-requests: read`, `contents: read`.
- `summary` (comments on issues, calls the models API) → grant `issues: write`,
  `models: read`, `contents: read`.
- `check-bibliography-dois`, `check-non-standard-chars`, `check-phi`,
  `test-coverage` → only `contents: read` (the default), so no `permissions:`
  block is needed. `test-coverage` additionally takes an optional
  `CODECOV_TOKEN` secret, passed through the caller's `secrets:` block.
- `quarto-publish` (deploys to the `gh-pages` branch, which Pages serves) →
  grant `contents: write`, and set Settings → Pages → Source = "Deploy from a
  branch", branch `gh-pages` / `(root)` once. Grant `contents: write` even with
  `deploy: false` — the deploy job is part of the workflow, so the caller must
  grant its permissions even when it is skipped.
- `claude` (pushes branches, opens PRs, dispatches the review workflow) → grant
  `contents: write`, `pull-requests: write`, `issues: write`, `id-token: write`,
  `actions: write`, and add the `CLAUDE_CODE_OAUTH_TOKEN` secret.
  - **Optional:** if Claude will edit files under `.github/workflows/`, also add
    a `WORKFLOW_TOKEN` secret (a PAT or GitHub App token with `contents:write` +
    `workflows:write`). The integrated `GITHUB_TOKEN` cannot push workflow-file
    changes — GitHub rejects them without the `workflows` scope. Repos that never
    touch `.github/workflows/` can omit it; pushes fall back to `GITHUB_TOKEN`.
    Note that, unlike `GITHUB_TOKEN`, a PAT/App-token push **does** trigger other
    `push`-based workflows, so enabling `WORKFLOW_TOKEN` can set off extra CI runs.
  - **Optional:** set `checkout-submodules: true` so Claude can read submodule
    contents. Public submodules clone anonymously; private ones additionally need
    a `SUBMODULES_TOKEN` secret.
- `claude-code-review` (read-only review) → grant `contents: read`,
  `pull-requests: write`, `issues: write`, `id-token: write`, and the
  `CLAUDE_CODE_OAUTH_TOKEN` secret.
  - **Optional:** set `checkout-submodules: true` so the reviewer can read
    submodule contents instead of reporting them as uninitialized. Public
    submodules clone anonymously; private ones additionally need a
    `SUBMODULES_TOKEN` secret.
- `preview` (build half, read-only) → only `contents: read` (the default).
- `preview-deploy` (deploy half, pushes `gh-pages` + comments) → grant
  `contents: write`, `pull-requests: write`, `actions: read`.
- `cleanup-pr-previews` (commits deletions to `gh-pages`) → grant
  `contents: write`, `pull-requests: read`.
- `bump-submodule`, `sync-shared-fragments` (open a PR) → grant `contents: write`,
  `pull-requests: write`, and enable Settings → Actions → General → "Allow
  GitHub Actions to create and approve pull requests" so the integrated
  `GITHUB_TOKEN` can open the PR. For private submodules, `bump-submodule` also
  needs a `SUBMODULES_TOKEN` secret. Add a `WORKFLOW_TOKEN` only to push to a
  protected branch; otherwise pushes fall back to `GITHUB_TOKEN`.

The stubs in [`examples/`](examples) already include the right `permissions:`
blocks — copy them as-is.

The two Claude workflows are a pair: an `@claude review` mention (or any commit
Claude pushes) routes through `claude.yml`, which dispatches `claude-code-review.yml`
via `workflow_dispatch`. Install both, and keep the review stub named
`claude-code-review.yml` (or set `claude.yml`'s `review-workflow-file` input to
match) so the dispatch resolves.

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
| Live progress tracking comment on the PR | `track_progress` | No — hardcoded to `'true'` on `pull_request` events in `claude-code-review.yml` (`'false'` otherwise); not a `workflow_call` input, so callers cannot override it. Not used in `claude.yml` (agent mode manages its own progress comments). |
| Full Claude SDK output in the job log | `show_full_output` | Yes — driven by the `show-full-output` input of `claude-code-review.yml` (note the hyphen; off by default, turn on to diagnose silent auth / quota failures). Not surfaced in `claude.yml`. |
| Resume a prior session | `session_id` (internal step output of `anthropics/claude-code-action`) + `--resume` in `claude_args` | No — neither reusable workflow declares `session_id` as a `workflow_call` output, so session resume is not available to consumers of `claude.yml` or `claude-code-review.yml`. |

## PHI scanning (`check-phi`)

`check-phi` is a **heuristic tripwire, not a HIPAA compliance tool.** It flags
patterns that should almost never be committed — US Social Security numbers,
medical record numbers, dates of birth, and PHI-suggestive column headers in
delimited data files (`.csv`/`.tsv`/`.psv`) — so a human reviews before the
data merges. It is tuned for high precision (few false positives), so it will
miss free-text PHI such as patient names. The `phone` and `email` detectors
exist but are **off by default** (too noisy in source); enable them via the
`detectors` input.

- **Diff-scoped on PRs.** Only lines *added* by the PR are scanned, so existing
  fixtures don't re-trip the check on unrelated edits. `push` runs scan the
  whole tracked tree (`git ls-files`).
- **Values are never printed.** A leaked identifier in a CI log is still a leak,
  so findings report only `file:line:col` and the detector name — never the
  matched text. Findings appear as inline annotations on the PR.
- **Suppressing false positives** (e.g. synthetic test data): add a `phi-allow`
  comment on the line, or list a regex matching the value in an allowlist file
  (defaults to `.github/phi-allowlist.txt` when present; override with the
  `allowlist-file` input). Use `fail: false` to downgrade to warnings.

## PR previews (`preview` family)

The PR-preview family publishes a rendered Quarto site for each open PR to a
`pr-preview/pr-<n>/` directory on `gh-pages`. It is **three** cooperating
workflows — install all three stubs from [`examples/`](examples):

1. **`preview.yml`** (build) — triggered on `pull_request`. Renders the site and
   uploads it plus the PR metadata as a `pr-preview-site` artifact. Runs
   **read-only** in the (possibly fork) PR context, so it can't write to the
   base repo.
2. **`preview-deploy.yml`** (deploy) — triggered on `workflow_run` completion of
   the build. Downloads the artifact and publishes it to `gh-pages` in the
   **base-repo** context (where the token can write), then comments the preview
   link on the PR.
3. **`cleanup-pr-previews.yml`** (housekeeping) — scheduled. Removes preview
   directories for PRs that have closed. Set `compact-history: true` to also
   orphan-squash `gh-pages` to a single commit each run, so the deleted
   snapshots don't accumulate and bloat the repo (branch-based Pages only).

The build/deploy split is a **trust boundary**: untrusted fork code only ever
runs in the read-only build half, while the privileged `gh-pages` push happens
in the deploy half against base-repo code. Don't collapse them into one job.

Two wiring requirements:

- The deploy stub's `on: workflow_run: workflows:` value **must match the
  build stub's `name:`** (both default to `Quarto Preview Build` in the
  examples). That string is how `workflow_run` finds the build.
- `workflow_run` and `schedule` triggers only fire for the copy of the file on
  the **default branch**, so previews and cleanup don't take effect until the
  stubs are merged to `main`.

The build half is parameterized for non-rme consumers (R version, the apt
package list, renv on/off, `R CMD INSTALL .` on/off, Chrome, submodules, render
profile). Label-gated extras are preserved: add `preview:pdf`, `preview:docx`,
or `preview:revealjs` to a PR to render those formats too, and `clear freezer`
to bypass the Quarto freeze cache.

## Shared-content sync (`bump-submodule` + `sync-shared-fragments`)

Two repos can share single-source-of-truth content and keep both copies current
without hand-bumping. The pair handles the two directions:

- **`bump-submodule`** — for the side that vendors the other repo as a git
  submodule. A scheduled run advances the submodule to its upstream HEAD and
  opens a PR when it moved. (Used by `UCD-SERG/lab-manual`, which carries
  `d-morrison/ai-config` as `.ai-config`.)
- **`sync-shared-fragments`** — for the side that can't add a submodule because
  the other repo already submodules *it* (a mutual submodule would recurse).
  Instead it vendors a pinned **copy** of the named files into a `dest-dir`,
  records the source repo and commit in a JSON manifest, and opens a PR when the
  copy changes. (Used by `d-morrison/ai-config` to vendor the lab manual's
  authored fragments.) Don't hand-edit the vendored copies — edit them upstream
  and let the workflow refresh them; a consumer-side drift check can assert the
  copy matches the pinned commit.

Both reuse the `open-sync-pr` composite, which commits staged changes to a
reused automation branch and opens or updates one PR (no-op when nothing
changed). Schedule and `workflow_dispatch` triggers live in the caller stubs.
Path-filter or scope each side to the *other* repo's shared content (not its own
pointer/manifest) so the two auto-PRs don't ping-pong.

## Versioning

Releases are tagged `vX.Y.Z`; the `vX` major tag moves to the latest compatible
release. Consumers reference `@v1`, except `test-coverage.yml`, which ships at
`@v2` (too new for the frozen `@v1` tag). See [`CHANGELOG.md`](CHANGELOG.md) for
what changes as a major tag moves and for any breaking-change migration steps.

### Pinning third-party actions

Every **third-party** action is pinned to a full commit SHA, with the
human-readable version in a trailing comment, e.g.:

```yaml
uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
```

This is GitHub's [recommended hardening posture](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions):
a SHA is immutable, so a re-pointed tag or a compromised upstream can't silently
change what runs — which matters here because jobs like the preview deploy run
with `contents: write` + `pull-requests: write`. [`.github/dependabot.yml`](.github/dependabot.yml)
bumps these pins as upstreams publish releases, so they stay current instead of
freezing. When adding a new third-party action, pin it the same way.

First-party `d-morrison/gha/*@v1` self-references and the [`examples/`](examples/)
templates intentionally track the `@v1` major tag (so consumers ride the moving
major), and so are **not** SHA-pinned.

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
