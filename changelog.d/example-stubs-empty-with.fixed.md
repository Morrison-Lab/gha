- **`examples/bump-dev-version.yml` and `examples/version-check.yml` no longer
  carry an empty `with:` section** (#823).
  Each stub had a `with:` key whose body was entirely commented out,
  so YAML parsed it as an empty mapping
  and `actionlint` reported `"with" section should not be empty` on it.
  A consumer copying either stub got a workflow
  their own `actionlint` (or `lint-workflows.yml`) flagged on the first run,
  which reads as a defect in their copy rather than in the template.
  The `with:` key is gone from both,
  and the `with:` line now sits inside the comment block alongside its inputs.
  The block is staggered so that deleting the leading `#` and one space
  from the `with:` line and from any subset of the input lines
  leaves both at their correct indentation.
  Every such combination was checked to parse
  with the uncommented inputs nested under `with:`.
