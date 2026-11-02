- **`check-self-credits`: a term link to an own site is not a credit.**
  A link whose target ends in a term anchor (`#def-orthogonal-matrix`,
  `#thm-...` and the like) is the lab's required link to a prerequisite
  definition.
  It no longer counts as an own-site mention, so a sentence such as
  "$w$ is built from vectors that $v$ is [orthogonal](https://morrison-lab.github.io/mds/...html#def-orthogonal-matrix) to"
  is not flagged.
  A link to a page without a term anchor, and an own name in prose, still count
  (gha#1385).
