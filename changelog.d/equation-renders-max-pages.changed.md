- **`check-equation-renders` opens at most 2 pages at once by default, down
  from 4, and takes a new `max-pages` input** (#1509). Each open page costs
  a headless Chromium renderer, and four of them saturated a shared
  self-hosted runner host. Callers on a roomy runner can set `max-pages: '4'`
  to restore the old parallelism; large sites crawl more slowly at the new
  default. A `max-pages` value that is not a positive integer now logs a
  warning and falls back to 2.
