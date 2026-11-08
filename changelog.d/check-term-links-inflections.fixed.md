- `check-term-links`:
  match an inflected plural of a defined term ("entropies", "matrices", "hypotheses", "maxima", "halves"), learn a title's parenthetical alias ("KL divergence") as its own term, and accept terms with a dash or an accented letter (gha#1630, gha#1631).
  A linked singular also covers a plural in the same div.
  Before, `finite entropies` passed unlinked on ids#88.
