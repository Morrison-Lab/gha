- `check-heading-levels`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags a heading
  breaking its page's outline when a pull request adds the heading line:
  a heading more than one level deeper than the one before it, a page whose first heading
  (following its `include` shortcodes) is deeper than level 2, and a first heading that repeats the page title.
  Pages split out of larger pages kept the headings of the page they came from,
  and a shared `### Configuring R` include opened ten chapters one level too deep.
  Headings inside fenced divs (the `####` titles of definition and exercise divs), code fences,
  comments and front matter do not count, and `<!-- check-heading-levels: allow -->` exempts a line.
  Like `check-one-div-per-subfile` it scopes to added lines,
  skips rather than scanning the whole tree when there is no base to diff against,
  and has a `whole-tree` mode that measures how many headings a corpus carries.
