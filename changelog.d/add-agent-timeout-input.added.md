- **`timeout-minutes` input on `claude.yml` and `claude-code-review.yml`**,
  defaulting to the current 60 so existing callers are unaffected.
  A caller cannot set `timeout-minutes` on a job that uses `uses:`, so the
  agent job's limit was previously unreachable from the consumer repo.
  Repos with a stricter policy can now express it:
  [`Morrison-Lab/qbt#28`](https://github.com/Morrison-Lab/qbt/issues/28) caps
  every job at 50 minutes, and these two were the only jobs it could not
  reach ([gha#879](https://github.com/Morrison-Lab/gha/issues/879)).
