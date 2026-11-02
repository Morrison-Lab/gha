- `check-heading-siblings`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a heading
  a pull request adds to a group of more than 7 sibling headings,
  meaning headings of the same level under the same parent heading,
  with `include` shortcodes expanded and the top-level headings of a page counted as siblings.
  The lab's guideline is to aim for about five and to split or group past seven,
  so a reader scanning the headings can hold them in mind
  (Ezra, 2026-11-02; psw "Keep sibling headings to about five").
  Like `check-page-length` it scopes to touched groups, skips rather than scanning the whole tree
  when there is no base to diff against, and has a `whole-tree` mode that measures a corpus.
  `<!-- check-heading-siblings: allow -->` exempts a page.
