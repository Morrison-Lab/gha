- **`check-bibliography-dois` no longer installs the caller package's
  `Suggests`.**
  The check reads only the caller's `.bib` files, but it ran
  `setup-r-dependencies` with the default `dependencies = "all"`, so a
  `Suggests` package listed under `Remotes` in a private repository (the
  workflow token cannot read it) failed the check with `Can't find GitHub
  repo` before any DOI was examined.
  It now installs `Depends`, `Imports` and `LinkingTo` only.
  It also skips `setup-r-dependencies`' pandoc probe, which resolved the
  caller's whole `DESCRIPTION` (including `Suggests` and `Remotes`) a second
  time and failed in the same way.
