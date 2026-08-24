- **New `check-junk-files` capability** ([#605](https://github.com/Morrison-Lab/gha/issues/605)).
  Fails when a repository **tracks** operating-system or editor detritus --
  `.DS_Store`, AppleDouble `._*` sidecars, `.Rhistory`, `.RData`, `Thumbs.db`,
  `desktop.ini`.
  The failure names each file,
  gives the `git rm --cached` line that clears it,
  and points at the per-machine fix that stops it recurring everywhere else:
  a global gitignore, or `usethis::git_vaccinate()` for R users.
  Matching is `git ls-files -i -c -X`,
  so `patterns` is ordinary gitignore syntax,
  and `paths-ignore` exempts paths as git pathspecs.
  Scans tracked files rather than the diff,
  because a `.DS_Store` committed long ago is still a live defect.
