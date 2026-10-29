- `lint-changed-lines` takes two new inputs.
  `file-pattern` extends the check beyond R sources, for example to the R chunks of Quarto documents.
  `lms-ref` installs the `lms` package from `Morrison-Lab/psc` at that commit and lints the changed lines with `lms::default_linters(nested_calls = TRUE)`.
  Together they enforce the lab's no-nested-calls rule on the lines a pull request adds, without a sweep of existing code.
