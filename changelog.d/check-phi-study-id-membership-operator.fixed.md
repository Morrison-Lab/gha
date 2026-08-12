- **`check-phi`'s `study_id` detector now reaches SAS's `in (...)` membership
  form, negated or not** (#453).
  The operator alternation covered assignment, symbolic comparison, and SAS's
  word-form `eq`/`ne`, but not `where StudyID_c in ("...");`,
  so a real participant identifier written that way passed the check silently
  -- the failure #445 was built to fix, one operator over.
  `not in (...)` is covered alongside it,
  since the other operator families each carry both polarities,
  and excluding a named participant is as ordinary a place for a hard-coded id
  as selecting one.
  The branch takes a leading space like `eq`/`ne`,
  without which an ordinary `patient_idin(...)` call would match,
  and accepts `in (`, `in(`, and the upper-case `IN` that SAS is usually
  written in.
  Because the scan is line-based,
  a list is reached only when its first element sits on the same line as the
  name and the operator,
  a limit now stated beside the pattern alongside the three already there.
