- `check-avoided-words` fails on the word "thing" or "things" on a line a pull request adds
  ([gha#1454](https://github.com/Morrison-Lab/gha/issues/1454); psw `word-choice.qmd`, "Say which thing").
  Name the object, quantity, step, or idea instead.
  The rule fails by default, so a consumer on the `v3` tag sees its check turn red on any added line with the word.
  Existing text is untouched, and the check's allow comment exempts a deliberate use.
