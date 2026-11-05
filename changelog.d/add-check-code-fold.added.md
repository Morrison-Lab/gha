- `check-code-fold`:
  add a diff-scoped composite action and reusable workflow
  that fails a pull request adding `#| code-fold: false` to an executed code chunk
  (Ezra, 2026-11-05, [gha#1515](https://github.com/Morrison-Lab/gha/issues/1515)).
  A chunk is `show` when the prose mentions the code and `true` when it does not.
  An untouched chunk keeps its option, and a run with no base to diff against is skipped.
  `whole-tree` measures a corpus.
  It fails by default (`fail: false` warns).
