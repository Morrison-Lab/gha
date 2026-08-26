- **New `check-typos` capability** (composite action + `check-typos.yml`
  reusable workflow) (#557).
  Spellchecks the files `spellcheck.yml` cannot see -- a Quarto site's
  non-vignette `.qmd` pages, `CONTRIBUTING.md`-class Markdown, `docs/`,
  YAML, code comments, and repositories that are not R packages --
  with [crate-ci/typos](https://github.com/crate-ci/typos), a
  corrections-list checker rather than a dictionary checker.
  Separate from `spellcheck.yml` because the two tools have different
  vocabularies and config formats, and because this repo is not an R
  package and can dogfood `check-typos`.
  Diff-scoped by default (only lines a PR adds), like
  `check-new-line-breaks`, so a first run over an existing repo does not
  reflag years of drift; pass `base-ref: all` to scan the whole tree.
  The CLI is installed from a pinned GitHub release rather than wrapping
  the official `crate-ci/typos` action, which has no line-level diff
  filter, so the diff filter and the fail-closed `fail` gate have
  offline tests.
