- **Documentation URLs now point at `Morrison-Lab`** for the two repositories
  that moved there, `gha` and `ai-config` (#351 follow-up).
  Issue links were broken rather than merely stale: GitHub redirects
  `/blob/`, `/tree/`, and `/pull/` paths after a transfer, but an
  `/issues/<n>` path under the old owner returns a bare 404 with no redirect,
  so the link check failed on 20 of them.

  Link labels naming a moved repository were updated alongside their targets,
  so no link reads `d-morrison/gha` while pointing at `Morrison-Lab/gha`.

  Plain-text self-references were swept too, not just URLs.
  Several had become outright false rather than merely stale: `CLAUDE.md` and
  `README.md` described workflows as calling
  `d-morrison/gha/...@v2` when those files had already been changed to
  `Morrison-Lab/gha/...@v2`.
  The MCP guidance in `CLAUDE.md` now also records that a session's GitHub
  access is pinned to the repository name it was scoped with, so a session
  started on the old name must keep using it -- passing the new one is
  rejected, and `add_repo` will not bridge the two.

  Repositories that did not move -- `qwt`, `rme`, `rpt` -- are untouched, as
  are the plugin-marketplace identifiers (`ai-config@d-morrison` and the
  `d-morrison/ai-config.git` clone URL), which are names rather than URLs and
  still match the workflows that use them.
  Historical entries in `CHANGELOG.md` and `changelog.d/` keep the name the
  repository had when they were written.
