# Reverse Dependencies (Consumer Repos)

Repos that call `d-morrison/gha` reusable workflows from their
`.github/workflows/`.

> **Note:** This list helps us notify consumers before moving the `@v1` tag in
> a breaking way (or cutting `@v2`). It is **not** authoritative — always
> verify with a code search across the consuming orgs (`d-morrison`,
> `ucdavis`, `UCD-SERG`, `UCLA-PHP`, `UCD-IDDRC`) when releasing a breaking
> change. A GitHub code search for `d-morrison/gha/.github/workflows` across
> those owners is the quickest way to find current callers:
>
> ```bash
> # Requires an authenticated gh (run `gh auth login`, or set GH_TOKEN).
> gh search code 'uses: d-morrison/gha/.github/workflows' --owner d-morrison --owner ucdavis --owner UCD-SERG --owner UCLA-PHP --owner UCD-IDDRC
> ```

## How to register

If your repo calls a `gha` workflow, please open a PR adding it below (or file
an issue asking to be added). Similarly, if you stop using `gha`, open a PR or
issue to be removed.

**Only list a workflow in `Workflows used` once the consumer is actually
calling it** -- i.e. once the migrating PR in the consumer repo has *merged*,
not just opened. A workflow the consumer plans to adopt but hasn't yet is
still worth noting, but belongs in the Notes column as pending (citing the
tracking issue/PR), matching the `qwt` row's `summary`/Claude-workflows
precedent below -- not in `Workflows used`, which should read as present-tense
fact. (gha#302: registered `d-morrison/ai-config` as a `check-new-line-breaks`
consumer while the migrating PR, ai-config#703, was still open; caught by
review and fixed to match the `qwt` pattern before merge.)

## Consumer list

| Repo | Workflows used | Notes |
|------|----------------|-------|
| [`d-morrison/qwt`](https://github.com/d-morrison/qwt) | `check-bibliography-dois`, `check-non-standard-chars`, `check-links` | Quarto website template (propagates to downstream books via "Use this template"). Phase 1 migration ([qwt#115](https://github.com/d-morrison/qwt/pull/115)); `summary` + the Claude workflows pending parity ([qwt#116](https://github.com/d-morrison/qwt/issues/116)). |
| [`d-morrison/rme`](https://github.com/d-morrison/rme) | `preview`, `preview-deploy`, `cleanup-pr-previews` | The original motivation for the PR-preview family (see [#33](https://github.com/d-morrison/gha/issues/33)/[#34](https://github.com/d-morrison/gha/pull/34)). Migrated its three inlined preview workflows to the gha family in [rme#942](https://github.com/d-morrison/rme/pull/942) ([#75](https://github.com/d-morrison/gha/issues/75)). |
| [`Lacaedemon/sparta`](https://github.com/Lacaedemon/sparta) | `check-links`, `claude`, `claude-code-review`, `summary`, `quarto-publish` | Godot game; docs site published via `quarto-publish` (injects recorded gameplay clips through `pre-render-artifact`). |
| [`d-morrison/ai-config`](https://github.com/d-morrison/ai-config) | `quarto-publish` (`@v2`), `preview`, `preview-deploy`, `cleanup-pr-previews` | Portable AI agent config docs site; pure markdown, so the preview family's R/renv inputs are all disabled ([ai-config#401](https://github.com/d-morrison/ai-config/issues/401)). `check-new-line-breaks` (built in gha#300 specifically to replace ai-config's own local script of the same purpose) is pending: [ai-config#702](https://github.com/d-morrison/ai-config/issues/702)/[#703](https://github.com/d-morrison/ai-config/pull/703). |
