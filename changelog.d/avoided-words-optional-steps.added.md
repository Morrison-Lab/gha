- `check-avoided-words` warns on a line a pull request adds
  where a sentence opens "In another language", "In other languages" or "Optionally,",
  or where a bare "(optional)" appears
  (psw#493; psw#490, phrase optional steps as conditions).
  "Otherwise," is left out: a whole-tree run over mds, pds, psw and sds flagged it 5 times, all in proofs.
  The rule is warn-only while it is new, like the Gaussian rule.
