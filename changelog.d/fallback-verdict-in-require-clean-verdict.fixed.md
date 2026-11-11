- `claude-code-review.yml`: `require-clean-verdict` now looks up a fallback review itself, after a quota skip, instead of reading `find-fallback-verdict`'s outputs.
  "Re-run failed jobs" reused that job's stored `found=false`, so a fallback review posted after the skip was never seen (gha#1880).
  The `find-fallback-verdict` job stays, so a required check of that name still exists.
  Removing it is gha#1898.
