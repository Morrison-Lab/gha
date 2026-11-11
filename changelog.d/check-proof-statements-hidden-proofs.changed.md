- `check-proof-statements`:
  flag a proof hidden from the slides again, when a PR touches its file.
  gha#1491 removed that rule and recorded hiding a proof as a deliberate choice,
  on a paraphrase that Ezra did not confirm (2026-11-11).
  psw's rule is to show every proof on the slides and to remove a wrapper when the file is edited,
  so the rule fails by default like the statement rule.
  A caller that wants warnings sets `fail: false`.
