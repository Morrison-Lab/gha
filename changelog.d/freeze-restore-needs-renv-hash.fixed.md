- `preview` and `quarto-publish` no longer restore a Quarto freeze cache built under a different `renv.lock`.
  The last restore key omitted the lock's hash,
  so a render after a dependency change served results computed under the old package versions
  (gha#1871, Morrison-Lab/rme#1085).
  A repository without `renv.lock` is unaffected.
