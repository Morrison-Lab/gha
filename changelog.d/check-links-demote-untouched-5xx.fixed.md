- **`check-links.yml` no longer fails a PR on a 5xx from a link the PR does not add** (#1052).
  A brief github.com outage returned `503` for blob links in files no PR touched,
  and `max_retries` did not help, so every PR in every consumer went red.
  The `check-links` composite now reads lychee's JSON report and gains a `base-ref` input.
  With a ref, a 5xx fails only when its link is on a line added since that ref's merge base with `HEAD`,
  and is otherwise a warning annotation, a job-summary row, and a count in the new `demoted` output.
  An empty `base-ref` makes every 5xx a warning.
  The default, `all`, keeps failing on every 5xx,
  so direct callers of the composite, including the `check-quarto-*` composites, are unchanged.
  The `check-links.yml` reusable workflow opts in: it passes `HEAD^1` on `pull_request` and an empty `base-ref` elsewhere,
  and gains a `fail-on-any-5xx` input that passes `all`.
  The workflow calls the composite at `@v3`,
  so `@v3` callers get this, `fail-on-any-5xx` included, only after the tag slides.
  A 404, a network error, a timeout, and a lychee tool error still fail the check on any line.
  A 5xx in a file git cannot match to a tracked path blocks,
  and a report whose `errors`, `timeouts`, or `total` counts are missing or disagree with what it lists
  fails rather than passing.
  Because the composite now sets lychee's `--format` to `json`,
  a caller whose `lychee-args` passes another `--format` now fails the run;
  passing `--output` there already failed.
  The job summary now lists the failing links and their verdicts
  in place of lychee-action's own statistics table.
  Annotations name each file relative to the repository root.
