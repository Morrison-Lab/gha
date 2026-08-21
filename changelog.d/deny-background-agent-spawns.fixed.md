- `claude-code-review`: deny background `Agent`/`Task` spawns mechanically
  rather than only asking for synchronous calls in the prompt
  ([#532](https://github.com/Morrison-Lab/gha/issues/532)).

  A background spawn in a headless CI run ends the reviewer's turn waiting for
  completion notifications no later turn will deliver, so the run finishes with
  no verdict after real spend.
  The prompt already asked for `run_in_background: false`; that request was
  live and verbatim when the failure recurred.

  `Agent(run_in_background:true)` and its `Task` alias are now in
  `--disallowedTools`, using Claude Code's parameter-scoped rule form.
  This is narrower than denying `Agent` outright, which would also break the
  review plugin's legitimate synchronous fan-out.

  It closes one of two routes rather than both: a call that omits the parameter
  still backgrounds by default, and an omitted parameter never matches a rule.
  The prompt instruction stays, and covers that half.

  That the `--disallowedTools` flag parses the parameter-scoped rule form at
  all was measured on Claude Code 2.1.238 rather than assumed, against a
  known-unparseable rule as a negative control.
