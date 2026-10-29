- **`check-macro-expansions`**
  ([#1218](https://github.com/Morrison-Lab/gha/issues/1218)):
  a diff-scoped check that flags math on lines a PR adds that writes out by hand
  what a shared macro already says, such as `\sum_{i=1}^n` where `\sumin` exists.
  The expansions come from the single-line definitions of the macros file
  (default `latex-macros/macros.qmd`) whose body has at least four tokens and is not an alias;
  a `#1` in a body is a wildcard, and a repeated `#1` must match the same text.
  A lone font wrapper such as `\mathcal{H}` is never flagged.
  `exclude` (default `hist`) drops macros whose expansion is also ordinary notation;
  `<!-- check-macro-expansions: allow -->` marks a derivation step that rewrites the chunk on purpose.
  Warn-only by default, as the other macro checks are.
  Companion to the psw rule in
  [psw#343](https://github.com/Morrison-Lab/psw/pull/343).
