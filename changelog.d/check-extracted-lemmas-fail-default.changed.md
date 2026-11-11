- `check-extracted-lemmas` now blocks by default (`fail: true`); pass `fail: false` to keep warnings only (gha#1480).
  A whole-tree run on lds, mds, pds, sds, and psw found 2 bodies.
  One was a real violation (sds `sol-rss-gradient-vector`, the gradient of a linear function).
  The other was a denied claim ("not a floor for any particular function"), and a quantifier with a negation in the four words before it is no longer read as a general fact.
