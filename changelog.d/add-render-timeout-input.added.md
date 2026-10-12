- **`timeout-minutes` input on `preview.yml` and `quarto-publish.yml`**,
  defaulting to the current 45 so existing callers are unaffected.
  A caller cannot set `timeout-minutes` on a job that uses `uses:`, so the
  render job's cap was unreachable from the consumer repo, and a site whose
  full render (every page in every format) outgrew 45 minutes had its build
  cancelled with no way to raise the limit.
  It applies to the `build` job of both workflows;
  the `quarto-publish.yml` deploy job only pushes the staged site, so it keeps 45.
