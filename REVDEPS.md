# Reverse Dependencies (Consumer Repos)

Repos that call `Morrison-Lab/gha` reusable workflows from their
`.github/workflows/`.

> **Note:** This list helps us notify consumers before moving a major tag in
> a breaking way (or cutting the next one).
> It is **not** authoritative --
> always verify with a code search when releasing a breaking change.
> Search **both** paths: a repo still on the old `d-morrison/gha` path has not
> migrated yet, and is currently broken rather than merely stale, since that
> path no longer resolves.
>
> **Run BOTH the unscoped and the owner-scoped per-workflow search, and
> take the union.**
> Neither is complete on its own, and neither says so.
> Measured 2026-09-07 against the 18 repositories pinning
> `claude-code-review.yml@v2`:
> the owner list this commit replaces
> (`d-morrison`, `ucdavis`, `UCD-SERG`, `UCLA-PHP`, `UCD-IDDRC`),
> whose names last changed 2026-06-18,
> returned 10 of them,
> silently missing 8 --- the 7 under `Morrison-Lab` and
> `Lacaedemon/sparta`.
> With those two owners added it returns all 18 --- under the PINNED,
> per-workflow query below, not under the broad fallback beside it.
>
> **But the unscoped form is not complete either.**
> Measured 2026-09-07, repeated and stable across three runs: the unscoped
> per-workflow query returned 28 hits across 17 repositories and omitted
> `d-morrison/rme`, a public, non-archived consumer whose caller does pin
> this workflow at `@v2`.
> The owner-scoped form returned 29 across 18 and included it.
> GitHub code search does not report that it dropped anything, and the
> truncation check below cannot see it: 28 never equals the cap.
> So take the union of the two, and treat 18 as a floor rather than a count.
> Scope by the workflow you are about to change anyway,
> and take the owners only as a fallback:
> an owner list is a thing someone has to remember to update,
> and a per-workflow search is not.
>
> **Do not prefix the query with `uses:`.**
> GitHub code search reads a leading `word:` as a search qualifier and drops
> the term, so `gh search code 'uses: Morrison-Lab/gha/...'` returns 0 hits
> under every owner list -- indistinguishable from having no consumers.
> Measured 2026-09-06: 0 with the prefix, 30 without.
>
> ```bash
> # Requires an authenticated gh (run `gh auth login`, or set GH_TOKEN).
> # Run both of the per-workflow forms and union the results; see above.
> # Derive the major tag rather than hard-coding it (see resolve-major-tag.sh).
> major=$(git ls-remote --tags origin 'v*.*.*' \
>   | sed 's#.*refs/tags/##; s/\^{}$//' \
>   | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -1 | cut -d. -f1)
> gh search code "Morrison-Lab/gha/.github/workflows/<name>.yml@$major" \
>   --json repository,path --limit 100
>
> # ... and the same query again with "${OWNERS[@]}" appended.
>
> # Broad sweep, owner-scoped. Keep this list current as orgs are added.
> OWNERS=(--owner Morrison-Lab --owner d-morrison --owner ucdavis \
>   --owner UCD-SERG --owner UCLA-PHP --owner UCD-IDDRC --owner Lacaedemon)
> # --limit matters more than it looks. The default is 30, and this broad
> # term is far bigger than that: measured 2026-09-07, --limit 100 returned
> # 100 hits across only 4 repositories, while --limit 1000 returned 304
> # across 28. A truncated result is silent, so set the cap above the real
> # count and re-raise it if the hit count equals the cap.
> gh search code 'Morrison-Lab/gha/.github/workflows' "${OWNERS[@]}" \
>   --json repository,path --limit 1000
> gh search code 'd-morrison/gha/.github/workflows' "${OWNERS[@]}" \
>   --json repository,path --limit 1000  # not yet migrated
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
