- **`claude-code-review` now hands the reviewer the PR diff as a file**
  (#543, #567).
  #541 told the reviewer, in the system prompt, to call `gh pr diff` bare
  rather than redirecting or piping it.
  That instruction was live at `@v2` and the reviewer redirected anyway,
  eight times, on gha#555 --
  spending $4.95 on a run that produced no verdict.
  The reason is that the instruction removed the only route to what the
  reviewer actually wanted:
  the diff in a file, so it can chunk or count a large one.
  A compound command is denied as a whole,
  and the agent cannot write a file itself,
  so there was nothing left to reach for.
  A new step now writes the diff to the workspace before the agent starts,
  and the prompt names that absolute path --
  absolute because Claude Code's `Read` tool requires one --
  telling the reviewer to read it,
  to ignore it when listing changed files,
  and to fall back to `gh pr diff` only for something the file does not
  contain.
  `Bash(gh pr diff:*)` stays allowed,
  so a denial afterwards means something has genuinely gone wrong,
  which is what the stub-retry threshold is trying to measure.
  Failure to save the diff is not fatal:
  the partial file is removed, the path is left empty,
  and the reviewer keeps the route it has today.
