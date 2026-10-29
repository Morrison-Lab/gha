- `check-restated-results`:
  also warn when the theorem that restates a derived result is proved only by citing the solution,
  meaning its `.proof` div cites `@sol-...` and displays no equation of its own.
  The same `<!-- restated-ok: reason -->` comment exempts it, and the check stays diff-scoped and warn-only.
