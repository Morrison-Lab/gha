- **`check-equation-renders` no longer fails on slow page loads** (#1150).
  The crawl waits for the `load` event instead of `networkidle`,
  which timed out on large pages and failed the check for reasons unrelated to the equations.
  It also retries a failed page load once before reporting it.
