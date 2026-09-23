- **`restore-default-branch-workflows.sh` succeeds when default branch has no workflows** (#904).
  When a repository adopts workflows for the first time,
  the restore step now removes the PR's untrusted copy,
  places the `.restored-from-default-branch` marker,
  and succeeds with an empty workflows directory,
  allowing Claude Code Review to run instead of failing closed with a skip.
