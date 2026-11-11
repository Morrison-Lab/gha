- `check-bibliography-dois` at `@v2` now treats any 2xx answer from `doi.org` as a resolved DOI,
  so a publisher that answers a bot with 202 (IEEE, De Gruyter) no longer fails the check.
  This backports the behavior already on `main` (gha#1139).
