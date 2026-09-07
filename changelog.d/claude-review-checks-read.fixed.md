- `claude-code-review`: the `claude-review` job no longer requests
  `checks: read`.
  A called workflow cannot request a permission its caller lacks --
  the run ends in `startup_failure` before any job starts --
  so requesting it in #830 broke review dispatch in every consumer
  that had not granted it, until the tag moved (#831).
  Callers are still asked to grant it,
  which costs nothing and pre-positions them for the `v3` that will
  request it;
  until then the reviewer's `GET .../commits/{ref}/check-runs` reads
  fail with HTTP 403 and a clean diff can be reported as blocked
  (ucdavis/bcs#964, #829).
