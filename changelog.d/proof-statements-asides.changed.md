- **`check-proof-statements`**
  ([psw#422](https://github.com/Morrison-Lab/psw/issues/422)):
  also flag "without loss of generality", "moreover" and "furthermore" on a line a pull request adds
  inside a `#thm-`, `#lem-`, `#cor-` or `#prp-` statement, outside its proof.
  Halmos says these asides "do not belong in the statement of a theorem"
  ("How to Write Mathematics", 1970, section 10).
  The check stays warn-only and diff-scoped, so a statement a pull request does not change is never reported.
