- **`check-avoided-words`**
  ([psw#418](https://github.com/Morrison-Lab/psw/pull/418)):
  add a diff-scoped, warn-only composite action and reusable workflow that flags
  words a style source advises against on a line a pull request adds in a `.qmd` or `.md` file:
  `above` or `below` for a place in the document, `just`, `easy` and `easily`,
  and time-relative words such as `currently` and `recently`.
  The sources are the Google developer documentation style guide's word list and "Timeless documentation" page.
  A comparison such as "above the threshold" and `just before` pass,
  as do code fences and spans, HTML comments and front matter.
  Moved lines are exempt, and a run with no base to diff against skips with a warning.
