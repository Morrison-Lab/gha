- `check-definite-antecedents`:
  flag a bare demonstrative pronoun (`this`, `these`, `those`, `that` standing alone, such as "make this precise")
  as well as an unlinked definite div opener (gha#1460, Ezra, 2026-11-04),
  and fail by default instead of warning (gha#1458).
  The `fail` input default changes from `false` to `true`, in the action and the reusable workflow;
  a caller that wants warnings sets `fail: false`.
  `<!-- check-definite-antecedents: allow -->` on a line exempts it.
