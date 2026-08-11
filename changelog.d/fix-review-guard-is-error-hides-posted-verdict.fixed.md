- **`claude-code-review`'s review guard no longer fails a check that already
  posted a complete verdict** (#391).
  A run can report `is_error: true` alongside `subtype: "success"` -- a
  self-contradictory result whose cause is still unestablished -- even after
  posting a genuine, finished review.
  The guard previously failed the check on `is_error` alone, before ever
  looking at the transcript, which hid two real, already-delivered verdicts
  from every reader and let both PRs merge with unaddressed findings.
  It now checks for a posted verdict first when `subtype` is `"success"`,
  and only falls back to failing the check when no verdict was found -- a
  genuine SDK error subtype (`error_during_execution`, `error_max_turns`,
  ...) still fails unconditionally, as before.
