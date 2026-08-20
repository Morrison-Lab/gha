- **`claude-code-review` no longer defers on session-lock claim comments** (#527).
  Comments such as "Driving this PR to clean - back off until done" block
  parallel write sessions (pushes), not read-only automated review. The
  reviewer prompt now says to proceed anyway, and `check-review-execution.sh`
  fails a "Deferred - author requested reviewers hold off" verdict that
  stopped without reviewing.
