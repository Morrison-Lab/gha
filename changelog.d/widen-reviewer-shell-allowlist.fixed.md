- **The Claude reviewer gets a general shell, so it can verify claims instead
  of only reasoning about them**
  ([#566](https://github.com/Morrison-Lab/gha/issues/566),
  [#572](https://github.com/Morrison-Lab/gha/issues/572)).
  `run-claude-review-attempt`'s allowlist named `python3`, `maxima`, `curl` and
  six read-only `gh` subcommands.
  Bash is allowlist-gated, so everything else was refused -- no `git` at all,
  no `bash`, not even a `for` loop -- and five measured runs died that way
  without producing a verdict, at 11 to 37 denials and $4.68 to $9.87 each.
  `Bash` is now granted whole, and `Write` is allowed under `/tmp` so the
  reviewer can stage a scratch script.
- **The deny list grew to match, preserving every write restriction the narrow
  allowlist used to imply.**
  `gh pr merge`, `gh pr edit`, `gh issue comment`, `gh api` and their siblings
  were unreachable only because they were absent from the allowlist; a blanket
  `Bash` grant would newly permit them, so they are denied by name and pinned
  by `run-reviewer-allowlist-tests.py`.
  `Bash(python3 -m:*)` is no longer denied, since
  `python3 -m pytest check-phi/tests/` is how this repo's own docs say to run
  its Python suites.
- **The reviewer prompt no longer tells the reviewer it cannot redirect, pipe,
  or write files.**
  Those instructions were true when written and would have defeated the grant.
  Correcting them also corrected the recorded mechanism: Claude Code splits a
  command on shell operators and matches each segment, so a chained call was
  never rejected "as a whole", and the blocked file writes were permission
  denials rather than a sandbox limit.
- **The verdict instruction no longer invites a doubled heading**
  ([#564](https://github.com/Morrison-Lab/gha/issues/564)).
  Asking for the conclusion under a `### Verdict` heading put the marker inside
  the backticked literal, so a model could read it as the heading text and emit
  `### ### Verdict`.
  The instruction now names the heading level and its text separately.
