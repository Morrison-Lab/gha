- **Diff-scoped checks no longer raise a warning annotation on a push run** (#1152).
  The reusable workflows pass `base-ref` only on `pull_request`, so a consumer that also triggers on `push` got
  `::warning::Skipping the ... check for this run (no base-ref given ...)` on every push to its default branch,
  and the annotation gate failed the run
  (Morrison-Lab/lds, run 39751842970).
  The thirteen diff-scoped checks (`check-definite-antecedents`, `check-typos`, `check-quarto-prose`,
  `check-write-idiom`, `check-self-credits`, `check-redundant-citations`, `check-new-line-breaks`,
  `check-wikipedia-further-reading`, `check-fform-paren`, `check-typed-output`, `check-local-macros`,
  `check-one-div-per-subfile` and `check-literal-math-letters`) now print the skip as a plain log line when no `base-ref`
  was given, since that skip is expected.
  A `base-ref` that is given but cannot be resolved still raises the warning.
  Callers at `@v3` get this only after the tag slides.
