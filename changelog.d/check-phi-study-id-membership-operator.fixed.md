- **`check-phi`'s `study_id` detector now reaches SAS's `in (...)` membership
  form** (#453).
  The operator alternation covered assignment, symbolic comparison, and SAS's
  word-form `eq`/`ne`, but not `where StudyID_c in ("...");`,
  so a real participant identifier written that way passed the check silently
  -- the failure #445 was built to fix, one operator over.
  The new branch takes a leading space like `eq`/`ne`,
  without which an ordinary `patient_idin(...)` call would match,
  and accepts `in (`, `in(`, and the upper-case `IN` that SAS is usually
  written in.
  A list is read at its first element,
  a limit now stated beside the pattern alongside the three already there.
