- **Reviews on closed or merged pull requests no longer claim a clean verdict** (#932).
  Previously, a review dispatched onto an already-closed or merged PR
  posted a `### Verdict: No action -- PR is closed/merged` prose conclusion
  alongside a structured `review-data` payload asserting `"verdict": "CLEAN"`.
  `classify-review-verdict.sh` trusted that payload on its fast path,
  and its prose scanner classified the `No action` prefix as ready for merge,
  while `claude-code-review.yml` stamped a trailing `Reviewed commit:` line
  for a commit the reviewer never inspected.
  `classify-review-verdict.sh` now recognizes the `SKIPPED` payload verdict
  and skips `CLEAN` payloads whose commit is unknown,
  and its prose scanner classifies closed, merged, and skipped verdicts
  as `verdict=skipped` (`clean=false`).
  The reviewer prompt now instructs Claude to use `"verdict": "SKIPPED"`
  when skipping a closed or merged PR,
  `claude-code-review.yml` omits the `Reviewed commit:` stamp on skips,
  and dispatch gates (`dispatch-review.sh`, `resolve-pr-info.sh`,
  `claude-review.yml`, and `dispatch-guard` across review workflows)
  now reject closed and merged PRs before launching review runs.
