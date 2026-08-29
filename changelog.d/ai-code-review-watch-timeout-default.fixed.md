- **`ai-code-review.yml`'s `watch-timeout` default raised from `15m` to
  `30m`, and a timed-out watch is re-checked before being treated as a
  failure** (#729).
  A 21-file diff measured a genuine 23-minute, $8.03 single-turn review, so
  the old `15m` default was falling through to try (and exhaust) other
  candidates -- failing the required check -- on reviews that went on to
  succeed and post a verdict minutes later.
  On a timeout, the selector now asks GitHub directly whether the run has
  since reached a terminal status before writing that candidate off,
  closing the race where the run finishes moments after the watch gives up.
