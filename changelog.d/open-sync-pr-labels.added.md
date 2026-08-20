- **`open-sync-pr` accepts a `labels` input** (#525).
  Comma-separated label names are applied when the automation PR is opened or
  updated; unknown labels warn rather than failing the step.
  `bump-dev-version.yml` threads the value through as `pr-labels` so callers
  can set `no changelog` on recurring bump PRs that only touch `Version:`.
