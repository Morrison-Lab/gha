- **`check-term-links` no longer learns an ordinary English word from a link alone**:
  a one-word term such as `linear`, `sum` or `memory` that is known only from a link
  to a `#def-` anchor is not flagged in ordinary use
  unless a def-div title or bold term also names it.
  On lds with the `allow` pragmas stripped, this removes 29% of whole-tree findings
  and 42% of those on lines that carried a pragma
  ([gha#1773](https://github.com/Morrison-Lab/gha/issues/1773)).
