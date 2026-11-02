- **`check-self-credits`: a term link to an own site is not a credit.**
  A link whose target ends in a term anchor (`#def-...`, `#thm-...` and the
  like) is the lab's required link to a prerequisite definition.
  It no longer counts as an own-site mention, so a sentence that says a vector
  is built from vectors orthogonal to another, with "orthogonal" linking to a
  prerequisite definition, is not flagged.
  A link to a page without a term anchor, and an own name in prose, still count
  (gha#1385).
