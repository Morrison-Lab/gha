# `changelog.d/` -- changelog fragments

Changelog entries live here as **one file per change**, not as direct edits to
[`CHANGELOG.md`](../CHANGELOG.md). Each pull request adds a new fragment file, so
two PRs in flight never touch the same lines and never conflict.

## Why fragments

Appending to a shared `## [Unreleased]` section makes sibling PRs collide on
adjacent lines. `.gitattributes` sets `CHANGELOG.md merge=union`, which resolves
those collisions -- but **only when git does the merge** (a local rebase, or CI
running git). GitHub's own mergeability check and web-merge button do **not**
apply custom merge drivers, so the PR still shows "conflicts must be resolved"
in the UI. A separate file per PR sidesteps the problem: new files never
conflict.

## Adding a fragment

Create a file named `<slug>.<category>.md`:

- `<slug>` -- a short dash-separated description (no dots), often the PR topic,
  e.g. `add-foo-input`.
- `<category>` -- one of: `breaking`, `added`, `changed`, `deprecated`,
  `removed`, `fixed`, `security`.

The file contents are one or more Markdown bullets in the same
[keepachangelog](https://keepachangelog.com/) style as `CHANGELOG.md` (reference
the PR/issue number where relevant):

```markdown
- **`some-workflow` gains a `foo` input** (#123). One or two sentences on what
  it does and why, matching the tone of existing `CHANGELOG.md` entries.
```

Do not put the `### Added` heading in the fragment -- the category comes from the
filename, and `assemble.sh` adds the heading when it collates.

## Releasing

At release time (before cutting a `vX.Y.Z` tag):

```bash
bash changelog.d/assemble.sh
```

This inserts every fragment under `## [Unreleased]` in `CHANGELOG.md`, grouped
into `### <Category>` subsections, and deletes the consumed fragment files.
Then review the diff, rename `## [Unreleased]` to `## [X.Y.Z] - <date>`, add a
fresh empty `## [Unreleased]` above it, and commit.

Keep `## [Unreleased]` **fragment-only** -- don't hand-edit entries into it -- so
`assemble.sh` never places a fragment under a heading that already exists there.
(Any entries currently sitting under `## [Unreleased]` from before this
convention are collated at the next release; merge them by hand that one time if
they share a category with a new fragment.)
