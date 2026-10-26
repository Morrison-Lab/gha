- **`check-equation-renders` no longer fails when a page navigates just after it loads.**
  Since the crawl waits for `load` rather than `networkidle`, a page whose script reloads or redirects right away
  could fail with `Execution context was destroyed, most likely because of a navigation`.
  The crawl now waits briefly for the network to settle, and retries the whole page once on any failure.
