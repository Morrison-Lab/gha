- **`update-snapshots`, `r-cmd-check`, and `preview`** list `libtiff-dev` instead of the Ubuntu-only `libtiff5-dev` in their default apt packages,
which exists on Debian and on every supported Ubuntu release.
`update-snapshots` also continues, with a warning that names the packages, when dpkg does not list them and the runner has no passwordless sudo,
so a runner that provides the libraries by another route is no longer stopped by the probe (gha#1697).
