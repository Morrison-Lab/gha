- **New `annotation-gate` capability** (composite action +
  `annotation-gate.yml` reusable workflow)
  ([#1097](https://github.com/Morrison-Lab/gha/issues/1097)).
  A job that `needs:` the caller's other jobs reads their annotations
  through the check-runs API and fails the run on any `notice`, `warning`
  or `failure` annotation not matching an allow pattern.
  Annotations on a green job were ignored by agents and authors.
  GitHub's runner-image migration notice and the forced-Node deprecation
  warning are allowed by default; callers add tracked exceptions through
  `allow-patterns`.
  Callers grant `actions: read` and `checks: read`.
