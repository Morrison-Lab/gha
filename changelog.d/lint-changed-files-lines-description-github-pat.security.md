- **`lint-changed-files` and `lint-changed-lines` now export `GITHUB_PAT`
  on their DESCRIPTION-based `setup-r-dependencies` step** (#734).
  Both composites already set `GITHUB_PAT` on their renv path and on their
  own lint step, but the DESCRIPTION-based dependency setup lacked it, so a
  consumer whose `DESCRIPTION` carries GitHub `Remotes:` entries resolved
  them via unauthenticated GitHub API calls from shared runner IPs -- a
  rate-limit flake risk.
  `lint-changed-lines`'s setup steps are documented
  as paralleling `lint-changed-files`'s, so it carried the identical gap and
  is fixed alongside it here.
