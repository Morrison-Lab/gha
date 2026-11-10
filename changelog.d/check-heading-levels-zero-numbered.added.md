- `check-heading-levels`:
  flag a numbered heading below level 1 that no numbered level-1 heading precedes,
  such as `## A` after `# Overview {.unnumbered}`,
  which Quarto numbers 0.1 under `number-sections: true`.
  The page-starts-too-deep rule saw only the first heading, so an unnumbered `#` opening a page hid every 0.x section after it.
