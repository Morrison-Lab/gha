- **`dest-files` input on `sync-shared-fragments.yml`**, a list of
  `source=destination` pairs for files that belong at explicit paths in the
  consumer repository, such as site scaffolding files at the repository root.
  Before, every file was flattened into one `dest-dir`, and the PR staged all of
  `dest-dir`, so a root-level destination would have staged the whole tree.
  Now only the written destinations and the manifest are staged.
  `source-paths` and `dest-dir` are optional so a caller sets either them or
  `dest-files`, and existing callers are unaffected
  ([gha#1796](https://github.com/Morrison-Lab/gha/issues/1796)).
