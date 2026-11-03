- `check-unexplained-choices`:
  add a diff-scoped composite action and reusable workflow that fails when a binning choice in code
  (`cut()`, `breaks=`, `bins=`, `binwidth=`) sits in a figure, example or section
  whose prose gives no reason for it
  ([ai-config#4905](https://github.com/Morrison-Lab/ai-config/issues/4905)).
  Ezra's rule (2026-11-03) is that every arbitrary analysis choice is explained in detail in the prose.
  Whether an explanation is good cannot be checked by a script, so the check asks only that a reason exists.
  It fails by default, because an agent ignores a warning.
  It recognizes only binning, to keep false positives low.
  `fail: false` warns instead.
  A reason word in the unit's prose clears it, and `<!-- check-unexplained-choices: allow -->` on a line exempts it.
  Like `check-unexplained-contrasts` it scopes to added lines and skips rather than scanning the whole tree without a base.
