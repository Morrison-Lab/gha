# `news.d/` — R package news fragments

Changelog entries for R packages live here as **one file per change**, not as direct
edits to [`NEWS.md`](../NEWS.md). Each pull request adds a new fragment file, so
two PRs in flight never touch the same lines and never conflict.

## Adding a fragment

Create a file named `<slug>.<category>.md`:

- `<slug>` — a short dash-separated description (no dots), e.g. `add-plot-function`.
- `<category>` — one of: `breaking`, `added`, `feature`, `fixed`, `bug`, `changed`, `minor`, `deprecated`, `removed`, `security`.

The file contents are one or more Markdown bullets describing the change:

```markdown
- Add `plot_results()` function for visualizing outputs ([#123](https://github.com/foo/bar/issues/123)).
```

Do not put section headings (like `## New features`) in the fragment — `assemble-news` groups and adds headings automatically when collating.

## Assembling at release time

At release time (before cutting a release tag), collate fragments into `NEWS.md` using the composite action:

```yaml
- uses: Morrison-Lab/gha/.github/actions/assemble-news@v2
  with:
    fragments-dir: news.d
    news-file: NEWS.md
```

This collates all fragments into `NEWS.md` under section headings (`## Breaking changes`, `## New features`, `## Bug fixes`, `## Minor improvements`) and removes the consumed fragment files.
See [`examples/assemble-news.yml`](../examples/assemble-news.yml) for a complete release workflow template.
