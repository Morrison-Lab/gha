- **`_selftest.yml`: macOS leg for the `credential-shape` suite** --
  the job now runs on a `[ubuntu-latest, macos-latest]` matrix, so a
  reintroduction of the BSD/GNU `wc` padding bug (#688) fails CI instead
  of only failing on maintainer machines
  ([#690](https://github.com/Morrison-Lab/gha/issues/690)).
