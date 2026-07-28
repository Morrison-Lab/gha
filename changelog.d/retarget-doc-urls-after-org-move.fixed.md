- **Documentation URLs now point at `Morrison-Lab`** for the two repositories
  that moved there, `gha` and `ai-config` (#351 follow-up).
  Issue links were broken rather than merely stale: GitHub redirects
  `/blob/`, `/tree/`, and `/pull/` paths after a transfer, but an
  `/issues/<n>` path under the old owner returns a bare 404 with no redirect,
  so the link check failed on 20 of them.

  Link labels naming a moved repository were updated alongside their targets,
  so no link reads `d-morrison/gha` while pointing at `Morrison-Lab/gha`.
  Repositories that did not move -- `qwt`, `rme`, `rpt` -- are untouched, as
  are the plugin-marketplace identifiers in the workflows, which are not URLs.
