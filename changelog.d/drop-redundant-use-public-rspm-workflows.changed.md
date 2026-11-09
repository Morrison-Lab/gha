- The workflows no longer pass `use-public-rspm: true` to `r-lib/actions/setup-r`.
  That input defaults to `true` at the pinned `v2.14.0`, so removing it changes no behavior (gha#1595).
