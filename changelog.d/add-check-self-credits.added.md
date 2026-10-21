- `check-self-credits`:
  add a diff-scoped composite action and reusable workflow that flags a formal
  credit to the group's own work in `.qmd` and `.md` files, since a link to
  another of our sites is fine but we do not acknowledge content borrowed from
  ourselves ([#1076](https://github.com/Morrison-Lab/gha/issues/1076)).
  It flags an added line that cites a bibliography entry marked as own, and an
  added line that has a credit phrase ("adapted from", a `Source:` line or div)
  in the same paragraph as the name or URL of one of the group's sites.
  The consumer lists its own sites, names, authors, keys and allowed keys in
  `.github/own-works.yml`, so credits to people outside the group never match,
  and links for further reading are never flagged.
  Like `check-redundant-citations` it is warn-only by default (`fail: false`),
  scopes to added lines (a moved line is not new), skips rather than scanning
  the whole tree when there is no base to diff against, and has a `whole-tree`
  mode.
