- `summary`: pin `actions/ai-inference` back to v2.
  Dependabot's gha#828 bumped it to v3, which removed the `endpoint` input
  outright and switched to a Copilot-CLI-only provider the runner must
  install and authenticate first.
  `summary.yml` passes `endpoint`, passes a non-Copilot `model`, and
  installs no CLI, so the bump broke it (gha#834).
  On a real run that failure would be silent --
  the step is `continue-on-error` and the only handling is a warning --
  so `summary-tests` was the sole detector, and it went red on `main`.
  Dependabot now ignores majors for that action.
  That is a freeze rather than a deferral:
  upstream removed `github-models` support entirely in v3,
  so migrating is an architecture change, tracked in gha#835.
