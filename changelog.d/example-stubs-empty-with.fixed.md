- **`examples/bump-dev-version.yml` and `examples/version-check.yml` no longer
  carry an empty `with:` section** (#823).
  Each stub had a `with:` key whose body was entirely commented out,
  so YAML parsed it as an empty mapping
  and `actionlint` reported `"with" section should not be empty` on it.
  A consumer copying either stub got a workflow
  their own `actionlint` (or `lint-workflows.yml`) flagged on the first run,
  which reads as a defect in their copy rather than in the template.
  The `with:` key is gone from both.
  The commented input documentation stays,
  now shown as a `with:` block the consumer uncomments as a unit,
  so every default is still discoverable.
