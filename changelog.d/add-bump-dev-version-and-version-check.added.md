- **New `bump-dev-version.yml` reusable workflow** bumps an R package's
  `DESCRIPTION` dev-version counter (the 4th `.90NN` component) after every
  merge to `main`, and opens (or auto-merges) a PR to carry it in (#388). Pairs
  with a **new `version-check.yml`**, which now fails a PR whose `Version:`
  differs from the base branch's at all -- the inverse of the old convention
  each repo copy-pasted from `RMI-PACTA/actions`' `R-semver-check.yml`
  (requiring a branch's version to *exceed* main's). Since a PR is never
  supposed to touch `Version:` anymore, two concurrent PRs no longer collide
  on that line, and `version-check` no longer flips red for no reason just
  because `main` caught up to a branch's version. Both depend on nothing but
  base R's `package_version` class, so neither needs an `install.packages()`
  step or a `rocker/verse` container. New composites:
  `.github/actions/bump-dev-version` and `.github/actions/check-dev-version`.
