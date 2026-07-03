- **`update-snapshots` now defaults `apt-packages` to the standard R
  system-deps list** instead of an empty string. The default installs the
  Linux libraries needed to build a typical R package's dependencies from
  source (Cairo, fonts, graphics, gettext, OpenMP), so R-package consumers no
  longer have to pass the same long list at every call site. Consumers that
  need a different set still pass their own list, and passing `''` skips the
  install step as before. This lets `ucdavis/bcs` drop the package list it
  currently duplicates across four call sites, since a local composite action
  can't be shared with an external `workflow_call` workflow (ucdavis/bcs#229).
