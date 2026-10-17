- `check-term-links`:
  add a diff-scoped, warn-only composite action and reusable workflow that
  flags a defined technical term whose first use in a div, or in a paragraph
  outside a div, is plain text instead of a link to its definition, and a bold
  term that no definition div covers
  ([#1078](https://github.com/Morrison-Lab/gha/issues/1078)).
  The terms are learned from the scanned files themselves: the titles and bold
  terms of `::: {#def-...}` divs, and the text of any link whose target ends
  in `#def-...`, so a term defined on another site is known once it is linked.
  `terms-file` adds terms by hand and `allow-file` exempts ordinary English.
