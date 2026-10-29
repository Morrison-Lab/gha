- **`check-restated-results`**, **`check-definition-equations`**, **`check-redundant-citations`** and **`check-macro-expansions`**
  ([gha#1357](https://github.com/Morrison-Lab/gha/issues/1357)):
  read the diff through `check-write-idiom`'s engine instead of private copies of `git diff` and `parse_diff`.
  The copies had the same silent skip under `diff.mnemonicPrefix=true` and the same dropped C-quoted paths as the engine (gha#1355).
  The engine now exports `GIT_DIFF_ARGS`, and a test fails if a check carries its own `"diff", "-U0"` call or hunk parser.
