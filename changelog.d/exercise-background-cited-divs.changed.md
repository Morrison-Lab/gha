- `check-exercise-background` reads the text of every div an exercise cites or links (`@exr-`, `@def-`, `@thm-`, `@sol-`, and the rest, followed transitively) as part of its body, without a cited exercise's solutions,
  and skips an exercise that cites an exercise the scanned files do not hold (gha#1481).
