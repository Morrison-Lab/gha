- **`update-snapshots` now defaults `apt-packages` to the standard R
  system-deps list** instead of an empty string. The default installs the
  Linux libraries needed to build a typical R package's dependencies from
  source (curl, TLS, XML, compression, fonts, graphics, Cairo, gettext,
  OpenMP, and a C/C++ build toolchain), so R-package consumers no longer have
  to pass the same long list at every call site. Consumers that need a
  different set still pass their own list, and passing `''` skips the install
  step as before. Because the default now runs an apt install where the old
  empty default skipped it, consumers who relied on the skip take on that
  step's runtime and its (small) chance of a transient apt failure; pass `''`
  to keep the old behavior. This lets `ucdavis/bcs` drop the package list it
  currently duplicates across four call sites, since a local composite action
  can't be shared with an external `workflow_call` workflow (ucdavis/bcs#229).
