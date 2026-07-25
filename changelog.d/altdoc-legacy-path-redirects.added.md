- **`altdoc-multiversion-docs.yml` gains a `legacy-paths` input** (#301),
  forwarded to the `generate-altdoc-landing-page` composite. Takes comma- or
  newline-separated `old=new` pairs (e.g. `main=dev`) and generates a
  site-root `404.html` that redirects any request under `old/` to the same
  path under `new/`. Keeps links alive for a site migrating from a scheme
  that published the default branch's docs to `/<branch>/` -- the
  `insightsengineering/r-pkgdown-multiversion` layout -- to this workflow's
  `/dev/`. GitHub Pages serves a site-root `404.html` for any unresolved
  path, so deep links such as `/main/reference/index.html` are covered,
  which a per-directory `index.html` meta-refresh would miss. Redirection
  requires JavaScript; without it the page renders as a plain not-found
  notice linking to the docs root. Empty (the default) generates no
  `404.html`, so existing callers are unaffected.
