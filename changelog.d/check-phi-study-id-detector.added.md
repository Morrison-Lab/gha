- **New `study_id` detector in `check-phi`**, on by default, catching a
  study or participant identifier assigned a quoted literal --- the one-off
  `if StudyID_c="...";` debugging spot-check that survives into committed
  analysis code.
  It keys on the **variable name** rather than on the value's shape, which is
  the whole point: a study's own id format is arbitrary, so a rule keyed on a
  shape gets it wrong quietly.
  In the exposure it was built from (`ucdavis/bcs#609`), seven distinct values
  were each ten characters and only two were all digits, so a rule keyed on a
  run of ten digits would have reported twelve of forty-five sites and passed
  over the rest.
  Verified against that repository's own pre-redaction files rather than
  against fixtures alone: the detector reports all 45 sites across 7 files,
  reproducing the count the issue derived independently.
  Precision comes from requiring an id-suggestive variable name, an assignment
  or comparison operator, and a quoted literal of at least eight alphanumerics
  containing at least one digit --- so an unquoted right-hand side (almost
  always another variable), a category label, and an ordinary token like
  `config1` are all rejected.
  Two limits are documented beside the pattern rather than papered over.
  A redacted placeholder such as `STUDYID20` satisfies it, so a repository
  that pseudonymizes in place needs an `allowlist-file` entry for its own
  placeholder shape.
  And nothing here reaches an identifier with no variable name beside it, so a
  pasted `proc print` block listing bare ids still passes through, exactly as
  `csv_phi_header` cannot see an unlabeled column.
  Consumers get this without opting in; one that trips it either has a real
  finding or adds an allowlist entry, which is the mechanism already designed
  for that.
