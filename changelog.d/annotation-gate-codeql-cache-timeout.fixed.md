- `annotation-gate` now allows the warning CodeQL's default setup emits when its cache download times out
  (`Failed to restore: Aborting cache download as the download time exceeded the timeout.`).
  The analysis still runs without the cache,
  and a default-setup CodeQL run cannot be re-run,
  so the warning blocked a PR until a new commit landed (gha#2167).
