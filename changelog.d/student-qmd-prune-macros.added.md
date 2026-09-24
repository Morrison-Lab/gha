- `student-qmd` gains a `prune-macros` input (default `false`)
  that drops LaTeX macro definitions a student file never uses,
  directly or through another macro,
  so a course whose shared macro file defines thousands of macros
  no longer opens every student file with them (gha#927).
  Every definition of a used name is kept.
  A definition inside an answer-key-only div is refused.
  The check leaves definitions out of its comparison,
  so a needed definition that went missing still fails it
  through the math it changes.
  The check's difference message now names an empty block's type,
  such as `(an empty Div #refs)`, where it used to print `''`.
