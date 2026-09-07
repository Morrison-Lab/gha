- `claude-code-review`: the `claude-review` job no longer requests
  `checks: read`.
  A called workflow cannot request a permission its caller lacks --
  the run ends in `startup_failure` before any job starts --
  so requesting it in #830 broke review dispatch in 17 of the 18
  repositories pinning `@v2`, 16 of them still broken (#831).
  **Consumers recover only once `v2` is slid onto this merge**;
  the tag was never rolled back, so merging alone changes nothing
  for them.
  Callers are still asked to grant it,
  which costs nothing and pre-positions them for the `v3` tracked in
  #833;
  until then the reviewer's `GET .../commits/{ref}/check-runs` reads
  fail with HTTP 403 and a clean diff can be reported as blocked
  (ucdavis/bcs#964, #829).
