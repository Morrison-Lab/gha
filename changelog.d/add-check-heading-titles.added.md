- `check-heading-titles`:
  add a diff-scoped, failing-by-default composite action and reusable workflow that flags a clickbait heading
  when a pull request adds it: a question, or a heading (or a phrase after a colon)
  that starts with who, whom, whose, what, when, where, why, how or which.
  The rule is in psw, "Subsection headings".
  Headings inside code fences, comments and front matter do not count,
  and `<!-- check-heading-titles: allow -->` exempts a line.
  Like `check-heading-levels` it scopes to added lines, so existing headings are not swept,
  skips rather than scanning the whole tree when there is no base to diff against,
  and has a `whole-tree` mode.
