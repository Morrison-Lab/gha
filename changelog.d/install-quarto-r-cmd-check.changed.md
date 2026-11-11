- `r-cmd-check.yml`'s hard-dependencies job installs Quarto through the internal `install-quarto` composite, so on a runner that sees the group-share release cache it reads the pinned Quarto 1.11.9 from there, and elsewhere it falls back to `quarto-dev/quarto-actions/setup` (gha#1678, gha#1846).
  The job used to take the setup action's default, the latest Quarto release.
  The OS matrix job keeps the setup action, since it also runs on macOS and Windows.
