- **`incremental` input on `preview.yml` and the `preview` composite**
  ([gha#1526](https://github.com/Morrison-Lab/gha/issues/1526)).
  A PR preview restores a cached `_site`, `.quarto`, and `_freeze`,
  and `preview/plan-incremental-render.py` lists the pages the PR can affect:
  each changed page, each page that includes a changed file,
  and each page that names a changed data file.
  Only those pages are rendered.
  The preview renders the whole site instead
  when there is no cache,
  when a path that can affect every page changed
  (`_quarto*.yml`, `_extensions/`, `filters/`, themes, the bibliography, macros, `tools/`),
  when a changed path is not reachable from any page,
  when a page was deleted,
  or when more than `incremental-max-pages` pages are stale.
  The `preview` composite also takes `incremental-full-render-paths`, `incremental-ignore-paths`, and `incremental-max-pages`;
  `preview.yml` forwards only `incremental`.
  Unchanged pages keep their old navigation, search entry, and cross-reference numbers.
  It defaults to false, so existing callers are unaffected.
