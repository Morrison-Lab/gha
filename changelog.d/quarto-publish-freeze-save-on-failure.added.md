- **`freeze-cache-save-on-failure` input on `quarto-publish.yml` and the
  `quarto-publish` composite**, defaulting to `false` so existing callers are
  unaffected.
  When it is `true`, a failed render still saves the Quarto `_freeze`
  directory, so the next run executes only the pages the failed run did not
  reach.
  A cold render that is cancelled otherwise leaves no cache, and the next run
  starts cold again
  ([gha#1141](https://github.com/Morrison-Lab/gha/issues/1141)).
  A run killed outright, by a timeout or a lost runner, may not get to save.
