- **`check-proof-statements`**
  ([gha#1351](https://github.com/Morrison-Lab/gha/issues/1351), [psw#426](https://github.com/Morrison-Lab/psw/pull/426)):
  add a warn-only composite action and reusable workflow for two proof rules.
  A proof inside a `content-hidden` wrapper for `revealjs` is flagged in any `.qmd` or `.md` file a pull request touches,
  because every proof is shown on slides.
  The words "so", "because", "hence", "therefore", "thus" and "since" are flagged on a line a pull request adds
  inside a `#thm-`, `#lem-`, `#cor-` or `#prp-` statement, outside its proof,
  because a statement gives the result and the proof gives the reasoning.
  There is no sweep: a file the pull request does not change is never reported.
  `check-write-idiom`'s engine gains a `wants_scope` option, so a scanner can read the added-line set itself.
