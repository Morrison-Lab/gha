- `check-one-div-per-subfile` no longer counts a proof or solution div.
  A proof may share a subfile with its claim, and a solution with its exercise (Ezra, 2026-10-23, [gha#1176](https://github.com/Morrison-Lab/gha/issues/1176)).
  A div counts as a proof or solution when its class is `proof`, `sol` or `solution`, or its id starts with `prf-` or `sol-`.
