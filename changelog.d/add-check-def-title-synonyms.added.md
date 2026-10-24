- `check-def-title-synonyms`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags the title of a
  `#def-` div that lists synonyms with parentheses or "also called"
  ([psw#338](https://github.com/Morrison-Lab/psw/issues/338)).
  A title is a comma list with the primary term first, as in "Logistic function, sigmoid, expit".
  Math and a parenthetical that contains math are ignored, an untouched title keeps its form,
  and a run with no base to diff against is skipped; `whole-tree` measures a corpus.
