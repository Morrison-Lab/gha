# `news.d/` -- R package news fragments

Changelog entries for R packages live here as **one file per change**, not as direct
edits to `NEWS.md`. Each pull request adds a new fragment file, so
two PRs in flight never touch the same lines and never conflict.

## Adding a fragment

Create a file named `<slug>.<category>.md`:

- `<slug>` -- a short dash-separated description (no dots), e.g. `add-plot-function`.
- `<category>` -- one of: `breaking`, `added`, `feature`, `fixed`, `bug`, `changed`, `minor`, `deprecated`, `removed`, `security`, unless the repo defines its own set (see [Custom headings](#custom-headings) below).

A fragment whose category is outside the active set fails the assemble step rather than
being skipped, so a mistyped category is caught instead of silently dropping the entry.

The file contents are one or more Markdown bullets describing the change:

```markdown
- Add `plot_results()` function for visualizing outputs ([#123](https://github.com/foo/bar/issues/123)).
```

Do not put section headings (like `## New features`) in the fragment -- `assemble-news` groups and adds headings automatically when collating.

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

## Custom headings

A repo whose `NEWS.md` uses a different taxonomy passes its own map through the
`headings` input, as newline-separated `category = Heading` pairs:

```yaml
- uses: Morrison-Lab/gha/.github/actions/assemble-news@v2
  with:
    fragments-dir: news.d
    headings: |
      breaking = Breaking changes
      added = New features
      fixed = Bug fixes
      infrastructure = Infrastructure
      docs = Documentation
```

When set, this **replaces** the built-in map rather than extending it:
it defines both the complete set of recognized categories
and the order the headings are written in.
Several categories may map to the same heading -- as `added` and `feature` do
by default -- and that heading then takes the position of its first-listed
category.
Leaving the input empty keeps the built-in behavior.
A `#` comments out a line only when it **starts** the line,
so a heading may contain one (`csharp = C# interop`).
A category may not contain a dot:
it is a single segment of `<slug>.<category>.md`,
and a dotted one collates the same fragment twice
when its suffix is also configured.
