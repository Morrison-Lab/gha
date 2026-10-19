- **`check-write-idiom`**
  ([#1121](https://github.com/Morrison-Lab/gha/issues/1121)):
  add a diff-scoped, warn-only composite action and reusable workflow that flags
  a line a pull request adds in a `.qmd` or `.md` file when it opens, after an optional list marker and label such as `(a)`,
  with `Write the `, `Write a ` or `Write an `.
  "Write ..." means derive, express, state or give,
  so the message asks for the action to be named literally
  ("Derive an expression for", "Express", "State", "Give").
  `Write $...$ for ...` (notation) and `Write down` pass,
  as do code fences and spans, HTML comments and front matter.
  Moved lines are exempt, and a run with no base to diff against skips with a warning.
