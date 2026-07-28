# Reverse Dependencies (Consumer Repos)

Repos that call `Morrison-Lab/gha` reusable workflows from their
`.github/workflows/`.

> **Note:** This list helps us notify consumers before moving the `@v1` tag in
> a breaking way (or cutting `@v2`). It is **not** authoritative — always
> verify with a code search across the consuming orgs (`d-morrison`,
> `ucdavis`, `UCD-SERG`, `UCLA-PHP`, `UCD-IDDRC`) when releasing a breaking
> change. Search **both** paths: a repo still on the old `d-morrison/gha` path
> has not migrated yet, and is currently broken rather than merely stale, since
> that path no longer resolves.
>
> **Do not rely on `gh search code` alone — it is demonstrably incomplete.**
> When the repo was renamed on 2026-07-28, a code search across all owners
> missed live consumers that an exhaustive scan found (e.g. `d-morrison/altdoc`).
> The reliable instrument enumerates every repo and reads its workflow files:
>
> ```bash
> # Requires an authenticated gh (run `gh auth login`, or set GH_TOKEN).
> for o in d-morrison ucdavis UCD-SERG UCLA-PHP UCD-IDDRC Morrison-Lab Lacaedemon; do
>   gh repo list "$o" --limit 1000 --no-archived --json nameWithOwner --jq '.[].nameWithOwner'
> done | while read -r r; do
>   gh api "/repos/$r/contents/.github/workflows" --jq '.[].path' 2>/dev/null | while read -r f; do
>     gh api "/repos/$r/contents/$f" -H "Accept: application/vnd.github.raw" 2>/dev/null \
>       | grep -q "gha/.github/workflows" && echo "$r $f"
>   done
> done
> ```
>
> Note this scans **default branches only**; open PR branches can still carry
> stale references that reappear on merge.

## How to register

If your repo calls a `gha` workflow, please open a PR adding it below (or file
an issue asking to be added). Similarly, if you stop using `gha`, open a PR or
issue to be removed.

**Only list a workflow in the table once the consumer is actually calling it**
-- i.e. once the migrating PR in the consumer repo has *merged*, not just
opened. A workflow the consumer plans to adopt but hasn't yet belongs under
"Notes" below as pending (citing the tracking issue/PR), not in the table,
which should read as present-tense fact. (gha#302: registered
`d-morrison/ai-config` as a `check-new-line-breaks` consumer while the
migrating PR, ai-config#703, was still open; caught by review and fixed
before merge.)

## Consumer list

Verified 2026-07-28 by an exhaustive scan of every non-archived repo across
`d-morrison`, `ucdavis`, `UCD-SERG`, `UCLA-PHP`, `UCD-IDDRC`, `Morrison-Lab`,
`Lacaedemon`, `ROBAS-UCLA`, `ucla-cisil`, and `ucjug` (947 repos). The
"Workflow files" column lists the consumer's own workflow filenames that
reference `gha`, which is not always the same as the `gha` workflow they call.

| Repo | Workflow files referencing `gha` |
|------|----------------------------------|
| [`d-morrison/altdoc`](https://github.com/d-morrison/altdoc) | `claude-code-review`, `claude`, `sync-upstream`, `test-coverage` |
| [`d-morrison/d-morrison.github.io`](https://github.com/d-morrison/d-morrison.github.io) | `cleanup-pr-previews` |
| [`d-morrison/psw`](https://github.com/d-morrison/psw) | `check-links`, `claude-code-review`, `claude`, `summary` |
| [`d-morrison/qbt`](https://github.com/d-morrison/qbt) | `check-bibliography-dois`, `check-links`, `check-non-standard-chars`, `claude-code-review`, `claude`, `summary` |
| [`d-morrison/qwt`](https://github.com/d-morrison/qwt) | `check-bibliography-dois`, `check-links`, `check-non-standard-chars` |
| [`d-morrison/rme`](https://github.com/d-morrison/rme) | `check-equation-renders`, `claude-code-review`, `cleanup-pr-previews`, `preview-deploy`, `preview` |
| [`d-morrison/rpt`](https://github.com/d-morrison/rpt) | `summary` |
| [`d-morrison/wai`](https://github.com/d-morrison/wai) | `bump-ai-config`, `check-bibliography-dois`, `check-links`, `check-non-standard-chars` |
| [`Lacaedemon/sparta`](https://github.com/Lacaedemon/sparta) | `check-links`, `check-non-standard-chars`, `claude-code-review`, `claude`, `demo-video`, `opposition-research`, `publish-site`, `refresh-benchmark-baseline`, `summary`, `website-preview-cleanup`, `website-preview-deploy`, `website-preview` |
| [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) | `claude-bot`, `claude-review`, `preview-cleanup`, `preview-deploy`, `preview`, `publish`, `sync-from-wai`, `validate` |
| [`UCD-SERG/lab-manual`](https://github.com/UCD-SERG/lab-manual) | `bump-ai-config`, `check-non-standard-chars`, `claude-code-review`, `claude`, `cleanup-pr-previews` |
| [`UCD-SERG/serocalculator`](https://github.com/UCD-SERG/serocalculator) | `claude-code-review`, `claude`, `docs`, `lint-changed-lines`, `news` |
| [`UCD-SERG/serodynamics`](https://github.com/UCD-SERG/serodynamics) | `bump-submodule`, `claude-code-review`, `claude`, `cleanup-pr-previews` |
| [`UCD-SERG/shigella`](https://github.com/UCD-SERG/shigella) | `claude-code-review`, `claude`, `news` |
| [`ucdavis/bcs`](https://github.com/ucdavis/bcs) | `R-CMD-check`, `check-non-standard-chars`, `claude-code-review`, `claude`, `cleanup-pr-previews`, `lint-markdown`, `news`, `pr-commands`, `update-snapshots` |
| [`ucdavis/epi204`](https://github.com/ucdavis/epi204) | `claude-code-review`, `claude`, `cleanup-pr-previews`, `summary` |
| [`ucdavis/ettbc`](https://github.com/ucdavis/ettbc) | `claude-code-review`, `claude`, `news` |
| [`ucdavis/fxtas.bds2`](https://github.com/ucdavis/fxtas.bds2) | `claude-code-review`, `claude` |
| [`ucdavis/fxtas`](https://github.com/ucdavis/fxtas) | `cleanup-pr-previews` |
| [`ucdavis/language.revitalization`](https://github.com/ucdavis/language.revitalization) | `cleanup-pr-previews` |
| [`ucdavis/mic.sim`](https://github.com/ucdavis/mic.sim) | `check-links`, `check-non-standard-chars`, `claude-code-review`, `claude` |
| [`ucdavis/win`](https://github.com/ucdavis/win) | `claude-code-review`, `claude`, `quarto-publish` |

### Notes

- [`d-morrison/qwt`](https://github.com/d-morrison/qwt) -- Quarto website
  template (propagates to downstream books via "Use this template"). Phase 1
  migration ([qwt#115](https://github.com/d-morrison/qwt/pull/115)); `summary`
  plus the Claude workflows pending parity
  ([qwt#116](https://github.com/d-morrison/qwt/issues/116)).
- [`d-morrison/rme`](https://github.com/d-morrison/rme) -- the original
  motivation for the PR-preview family (see
  [#33](https://github.com/d-morrison/gha/issues/33)/[#34](https://github.com/d-morrison/gha/pull/34)).
  Migrated its three inlined preview workflows in
  [rme#942](https://github.com/d-morrison/rme/pull/942)
  ([#75](https://github.com/d-morrison/gha/issues/75)).
- [`Lacaedemon/sparta`](https://github.com/Lacaedemon/sparta) -- Godot game;
  docs site published via `quarto-publish` (injects recorded gameplay clips
  through `pre-render-artifact`).
- [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) --
  portable AI agent config docs site; pure markdown, so the preview family's
  R/renv inputs are all disabled
  ([ai-config#401](https://github.com/d-morrison/ai-config/issues/401)).
  `check-new-line-breaks` was built (gha#300) to replace ai-config's own local
  script of the same purpose; migrated in
  [ai-config#702](https://github.com/d-morrison/ai-config/issues/702)/[#703](https://github.com/d-morrison/ai-config/pull/703).
