- **`check-bibliography-dois` skips `.bib` files inside git submodules.**
  It scanned every `*.bib` under the workspace, so a book without a DOI in a
  submodule's bibliography failed the caller's check, and the verdict depended
  on the runner: a self-hosted runner that reuses its work directory still held
  the submodule's files from an earlier job (the checkout step reports
  `submodules: false` and then lists the submodule), while a fresh runner did
  not.
  The same commit passed on one runner and failed on another.
  Submodules are read from the index (gitlinks), so a missing `.gitmodules`
  does not hide one.
  The new `include-submodules` input (default `false`) restores the old
  behavior for a caller that wants a submodule's bibliography checked.
