- `quarto-publish.yml`: give the `deploy` job its own `gh-pages-main` concurrency group,
  and deploy with `force: false`,
  so a stream of preview deploys can no longer cancel a pending main publish after a finished render.
  A newer main publish still supersedes an older pending one.
  Callers must not name a group `gh-pages-main` (gha#1759).
