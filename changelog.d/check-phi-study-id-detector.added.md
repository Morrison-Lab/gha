- **New `study_id` detector in `check-phi`**, on by default, catching a
  study or participant identifier assigned a quoted literal --- the one-off
  `if StudyID_c="...";` debugging spot-check that survives into committed
  analysis code.
  It keys on the **variable name** rather than on the value's shape, which is
  the whole point: a study's own id format is arbitrary, so a rule keyed on a
  shape gets it wrong quietly.
  In the exposure it was built from (`ucdavis/bcs#609`), nine distinct values
  were each ten characters and only three were all digits, so a rule keyed on a
  run of ten digits would have reported thirteen of forty-nine sites and passed
  over the rest.
  Verified against that repository's own pre-redaction files rather than
  against fixtures alone.
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
- The detector reaches R's `<-` and `<<-` assignment, underscore-prefixed
  names (`base_patient_id`), and subscripted column access
  (`df[["patient_id"]] <- ...`).
  The first matters most: R and Quarto are this org's target ecosystem, where
  `<-` is the dominant assignment form, so a rule seeing only `=` would have
  been narrower than its own documentation claimed.
  The underscore case was a `\b` that finds no boundary after `_`, which is a
  word character.
- `_selftest.yml`'s `phi` job now lists `study_id` in its `detectors:` input.
  That input **replaces** the default set rather than extending it, so a
  detector added to `DEFAULT_DETECTORS` and not added there gets no end-to-end
  coverage through the real composite action, and the job's own "run every
  detector" comment quietly stops being true.
- The detector also reaches SAS's word-form comparisons, `StudyID_c ne "..."`
  and `eq`, which need surrounding whitespace and so are a separate
  alternative rather than another symbol.
  A real site written that way escaped every `=`-keyed search during the
  exposure this was built from.
- The doc comment now records the limit that matters most for how this should
  be read: an identifier passed to a generically-named parameter
  (`get_IDs(IDs = "...")`) is out of reach, because a bare `IDs` cannot be
  keyed on without drowning the check.
  It is a tripwire for identifiers nobody was looking for, not proof that a
  tree is clean --- for that, search for the values.
