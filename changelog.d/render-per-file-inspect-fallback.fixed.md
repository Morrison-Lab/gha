- **`per-file-formats` no longer fails when `quarto inspect` does.**
  `quarto inspect` resolves a nested include from the including file's
  directory, so a project that writes includes through a self-symlink
  (`mds -> .`, as mds and pds do) rendered but failed after the whole render.
  `render-per-file.py` now shows the inspect error, then falls back to the
  project's `render:` globs and each file's front matter
  ([gha#1214](https://github.com/Morrison-Lab/gha/issues/1214)).
