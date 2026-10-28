- `lint-changed-lines` takes two new inputs.
  `file-pattern` widens the linted files beyond R sources, for example to Quarto documents, whose R chunks lintr lints.
  `lms-ref` installs the `lms` package from `Morrison-Lab/psc` at that commit and lints the changed lines with `lms::default_linters(nested_calls = TRUE)`.
  Together they enforce the lab's no-nested-calls rule on the lines a pull request adds, without a sweep of existing code.
