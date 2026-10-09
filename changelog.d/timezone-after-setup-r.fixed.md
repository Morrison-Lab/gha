- **`timezone` now reaches the render in `preview` and `quarto-publish`.**
  The step that exports `TZ` ran before `r-lib/actions/setup-r`,
  which exports `TZ=UTC` itself,
  so any caller with `setup-r` enabled rendered in UTC whatever `timezone` said.
  The step now runs directly before the render
  (measured on [qmt#11](https://github.com/Morrison-Lab/qmt/pull/11),
  whose build steps listed `TZ: UTC` with `timezone: America/Los_Angeles` set).
