# Reverse Dependencies (Consumer Repos)

Repos that call `Morrison-Lab/gha` reusable workflows from their
`.github/workflows/`.

> **Note:** This list helps us notify consumers before moving the `@v1` tag in
> a breaking way (or cutting `@v2`). It is **not** authoritative -- always
> verify with a code search when releasing a breaking change.
> Search **both** paths: a repo still on the old `d-morrison/gha` path has not
> migrated yet, and is currently broken rather than merely stale, since that
> path no longer resolves.
>
> **Prefer the UNSCOPED, per-workflow search.**
> An owner-scoped list goes stale silently.
> Measured 2026-09-06 against the 18 repositories then pinning
> `claude-code-review.yml`:
> the pre-2026-09-06 owner list
> (`d-morrison`, `ucdavis`, `UCD-SERG`, `UCLA-PHP`, `UCD-IDDRC`)
> returned 10 of them,
> silently missing the 6 under `Morrison-Lab` and `Lacaedemon`
> plus 2 more.
> Scope by the workflow you are about to change instead,
> and take the owners only as a fallback.
>
> **Do not prefix the query with `uses:`.**
> GitHub code search reads a leading `word:` as a search qualifier and drops
> the term, so `gh search code 'uses: Morrison-Lab/gha/...'` returns 0 hits
> under every owner list -- indistinguishable from having no consumers.
> Measured 2026-09-06: 0 with the prefix, 30 without.
>
> ```bash
> # Requires an authenticated gh (run `gh auth login`, or set GH_TOKEN).
> # Primary: every caller of the workflow being changed, whatever the owner.
> # Derive the major tag rather than hard-coding it (see resolve-major-tag.sh).
> major=$(git ls-remote --tags origin 'v*.*.*' \
>   | sed 's#.*refs/tags/##; s/\^{}$//' \
>   | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1 | cut -d. -f1)
> gh search code "Morrison-Lab/gha/.github/workflows/<name>.yml@$major" \
>   --json repository,path --limit 100
>
> # Fallback: broad, owner-scoped. Keep this list current as orgs are added.
> OWNERS=(--owner Morrison-Lab --owner d-morrison --owner ucdavis \
>   --owner UCD-SERG --owner UCLA-PHP --owner UCD-IDDRC --owner Lacaedemon)
> gh search code 'Morrison-Lab/gha/.github/workflows' "${OWNERS[@]}"
> gh search code 'd-morrison/gha/.github/workflows' "${OWNERS[@]}"  # not yet migrated
> ```

## How to register

If your repo calls a `gha` workflow, please open a PR adding it below (or file

an issue asking to be added). Similarly, if you stop using `gha`, open a PR or
issue to be removed.

**Only list a workflow in `Workflows used` once the consumer is actually
calling it** -- i.e. once the migrating PR in the consumer repo has *merged*,
not just opened. A workflow the consumer plans to adopt but hasn't yet is
still worth noting, but belongs in the Notes column as pending (citing the
tracking issue/PR), matching the `qwt` row's existing `summary`/Claude-workflows
Notes-column pattern -- not in `Workflows used`, which should read as present-tense
fact. (gha#302: registered `Morrison-Lab/ai-config` as a `check-new-line-breaks`
consumer while the migrating PR, ai-config#703, was still open; caught by
review and fixed to match the `qwt` pattern before merge.)

## Consumer list

| Repo | Workflows used | Notes |
|------|----------------|-------|
| [`Morrison-Lab/qwt`](https://github.com/Morrison-Lab/qwt) | `check-bibliography-dois`, `check-non-standard-chars`, `check-links` | Quarto website template (propagates to downstream books via "Use this template"). Phase 1 migration ([qwt#115](https://github.com/Morrison-Lab/qwt/pull/115)); `summary` + the Claude workflows pending parity ([qwt#116](https://github.com/Morrison-Lab/qwt/issues/116)). |
| [`d-morrison/rme`](https://github.com/d-morrison/rme) | `preview`, `preview-deploy`, `cleanup-pr-previews` | The original motivation for the PR-preview family (see [#33](https://github.com/Morrison-Lab/gha/issues/33)/[#34](https://github.com/Morrison-Lab/gha/pull/34)). Migrated its three inlined preview workflows to the gha family in [rme#942](https://github.com/d-morrison/rme/pull/942) ([#75](https://github.com/Morrison-Lab/gha/issues/75)). |
| [`Lacaedemon/sparta`](https://github.com/Lacaedemon/sparta) | `check-links`, `claude`, `claude-code-review`, `summary`, `quarto-publish` | Godot game; docs site published via `quarto-publish` (injects recorded gameplay clips through `pre-render-artifact`). |
| [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) | `quarto-publish` (`@v2`), `preview`, `preview-deploy`, `cleanup-pr-previews`, `check-new-line-breaks` | Portable AI agent config docs site; pure markdown, so the preview family's R/renv inputs are all disabled ([ai-config#401](https://github.com/Morrison-Lab/ai-config/issues/401)). `check-new-line-breaks` was built (gha#300) specifically to replace ai-config's own local script of the same purpose; migrated in [ai-config#702](https://github.com/Morrison-Lab/ai-config/issues/702)/[#703](https://github.com/Morrison-Lab/ai-config/pull/703). |
