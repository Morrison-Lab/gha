- `install-quarto` installs TinyTeX from the release cache when `tinytex` is true and Quarto came from the cache.
  The bundle is pinned in `install-tinytex-pins.txt` with its SHA-256, unpacked into `~/.TinyTeX` without sudo, and an existing install is kept.
  Any other platform, an unpinned version, or a failed cache install falls back to `quarto install tinytex` (gha#1705).
