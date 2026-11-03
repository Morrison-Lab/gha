- `check-unexplained-choices`:
  add a diff-scoped, warn-only composite action and reusable workflow that flags an analysis choice in code
  (`cut()`, `breaks=`, `bins=`, `set.seed()`, a bandwidth, a train/test split) in a figure, example or section
  whose prose gives no reason for it
  ([ai-config#4905](https://github.com/Morrison-Lab/ai-config/issues/4905)).
  Ezra's rule (2026-11-03) is that every arbitrary analysis choice is explained in detail in the prose.
  Whether an explanation is good cannot be checked by a script, so the check prompts the author and does not block by default.
  A reason word in the unit's prose clears it, and `<!-- check-unexplained-choices: allow -->` on a line exempts it.
  Like `check-unexplained-contrasts` it scopes to added lines and skips rather than scanning the whole tree without a base.
