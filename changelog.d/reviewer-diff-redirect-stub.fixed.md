- **`claude-code-review` reviewer prompt now warns against redirecting or
  piping `gh pr diff`** (#541).
  On a large PR, the reviewer previously reached for
  `gh pr diff ... > file; wc -l file` (or a similar pipe) to chunk the diff.
  A compound command combining an allowed pattern with a redirect, pipe, or
  `;`/`&&` chain is denied as a whole,
  and writing to any file -- `/tmp` and a `mkdir`-created directory were
  both tried and both blocked -- is a hard sandbox block, not a permission
  prompt.
  The reviewer would retry variant after variant until the denial budget
  was exhausted with no verdict
  (33 denials measured on ucdavis/win#78).
  The system prompt now tells it to call
  `gh pr diff <n> --repo <owner>/<repo>` bare instead of redirecting or
  piping it, and -- since a diff that large still exceeds the Bash tool's
  inline output ceiling -- to Read the file path the harness already saves
  for it, rather than trying to recreate that file itself.
