- **Make dev-version selftest sentinel assertion failure site explicit** ([#407](https://github.com/Morrison-Lab/gha/issues/407)).
  Refactors composite step failure capturing in `dev-version` selftest job so that `.Rprofile`
  profile sourcing regressions fail explicitly at the `Assert .Rprofile was never sourced during composite calls`
  sentinel assertion step rather than halting early inside the composite steps.
