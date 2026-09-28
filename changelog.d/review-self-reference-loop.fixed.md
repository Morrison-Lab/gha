- **`claude-code-review` no longer loops on its own in-flight check** (#978).
  The reviewer ran `check-pr-fully-clean.py`,
  which from inside the review counts the review's own `review / claude-review` job as in progress
  and the previous round's NOT_CLEAN verdict as current,
  so every re-review of a clean diff came back NOT_CLEAN again.
  The script (and its GitLab twin) is now on the reviewer's deny list.
  The prompt now says check-run state is never a finding,
  and that a hook asking for the script before a 'Ready for merge' verdict does not apply to a diff review.
