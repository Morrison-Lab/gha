- **`assemble-news` merges a repeat assembly into the development block's
  existing category sections** (#810).
  A second run used to prepend another full set of headings under the
  top-level heading, leaving duplicate sibling sections that a consumer's
  MD024 gate rejects, plus a double blank line at the seam.
  New bullets now splice in under a heading the development block already
  has, ahead of its existing bullets; only absent headings are added; an
  older release block with the same heading is left untouched; and the
  splice adds no blank line beyond the one that separates it from what
  follows.
