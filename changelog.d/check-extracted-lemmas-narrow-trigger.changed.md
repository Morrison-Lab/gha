- `check-extracted-lemmas`:
  flag "for any/every/all" only before a kind of mathematical object
  (a real number, a random variable, a matrix, a function, and similar),
  and ignore inline code (gha#1480).
  A whole-tree run over lds, mds, pds, sds, and psw dropped from 152 findings to 23.
  About half of the remaining sample were still contrasts about one example, such as "6k = 3(2k) for every integer k",
  so the check stays warn-only.
