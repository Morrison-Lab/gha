- **A line whose only change is to its links now reads as moved**
  in every check that uses `check-common/diffscope.py`'s moved-line test
  (#2133).
  After a page split, repointing `old.qmd#id` to `new.qmd#id`,
  or wrapping an existing word in a link,
  leaves the prose as it was,
  but checks such as `check-geometric-figures` and
  `check-definite-antecedents` judged the line as new text
  and reported prose the PR never wrote (Morrison-Lab/mds#839).
  `parse_diff` now returns a `DeletedTexts` set:
  its contents are still the deleted lines as written,
  and `in` also passes an added line that equals a deleted one
  once every inline link is reduced to its link text.
  Image targets are kept, since changing an image changes the content.
  `spelling_only_lines` is unaffected.
