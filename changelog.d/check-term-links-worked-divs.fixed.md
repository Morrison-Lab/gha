- `check-term-links`:
  check an exercise, solution, result, proof or remark div even when its file also holds the term's definition (gha#1316, gha#1539).
  Only a source callout (`#rem-source-`, or a plain callout) beside the definition stays exempt.
  Before, a `#sol-` div in the defining file was never checked, so its unlinked terms passed.
