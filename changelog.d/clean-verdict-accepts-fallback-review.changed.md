- **`claude-code-review.yml`'s `require-clean-verdict` now passes on a quota skip when a clean fallback review of the current head is recorded on the PR.**
  The fallback is a separate-agent review posted as a PR comment.
  It counts only when its author is a repository owner, member or collaborator, it carries the agent-authorship marker, it names the full head sha in a `Reviewed-Commit:` line, and the classifier reads its verdict as clean.
  The newest such review of the head decides, so a later not-clean one withdraws an earlier clean one, and a push retires the comment.
  A quota skip with no such comment still fails, as gha#1019 requires.
  The lookup is a new `find-fallback-verdict` job that runs only on a quota skip and reads the comments when it runs, so after posting the fallback review, re-run the workflow's jobs to pick it up.
  It needs `pull-requests: read`, which every caller already grants through `pull-requests: write`, and `require-clean-verdict` keeps `permissions: {}`
  ([gha#1163](https://github.com/Morrison-Lab/gha/issues/1163)).
