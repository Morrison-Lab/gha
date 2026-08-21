- **README's capability table renders as a table again** (#558).
  A blank line left between two rows in `cacf1df` ended the GFM table early,
  so roughly 40 of its 46 rows had been rendering as literal pipe-delimited
  text on GitHub since 2026-08-18.
  No check could see it:
  markdownlint's table rules apply within a table block,
  and a blank line means the rows after it are not one.
  #558 tracks adding a detector to `lint-markdown`,
  alongside the other supplements it already carries for defects
  markdownlint structurally cannot catch.
