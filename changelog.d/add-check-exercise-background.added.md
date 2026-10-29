- `check-exercise-background`:
  add a diff-scoped, warn-only composite action and reusable workflow
  that flags an exercise (`#exr-` div) when a PR adds a line of it
  and its title has a content word that the body never mentions
  (Ezra, 2026-10-29, [psw#417](https://github.com/Morrison-Lab/psw/pull/417)).
  An exercise titled "Maximizing a gamma-family kernel" says in its body what a gamma kernel is and why anyone maximizes one.
  A word counts as present when a body word shares its first five letters,
  and generic task verbs such as find, compute and classify are never reported.
  It is a heuristic: a synonym in the body is reported too, so it warns by default (`fail: true` blocks).
  `whole-tree` measures a corpus.
