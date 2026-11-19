- `check-tautological-equations`:
  add a diff-scoped, blocking composite action and reusable workflow that
  expands the shared macros on each side of an equality in math a pull request
  touches, and fails when both sides render identically.
  Ezra asked for it on 2026-11-19 after
  [Morrison-Lab/mds#835](https://github.com/Morrison-Lab/mds/pull/835)
  defined `\bform{\matr{A}}{\vx}{\vy} \eqdef \tp{\vx} \matr{A} \vy`,
  whose left side expands to its right, so the reader saw a tautology.
  `<!-- check-tautological-equations: allow -->` exempts a deliberate
  reflexivity example, and `paths-ignore` exempts whole paths.
