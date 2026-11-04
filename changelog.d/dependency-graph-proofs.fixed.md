- **`build-dependency-graph` counts a result's proof**
  ([#1451](https://github.com/Morrison-Lab/gha/issues/1451)).
  A `::: proof` div written right after a `#def-`, `#thm-`, `#lem-`, `#prp-` or `#cor-` div now counts as part of that div.
  Before, every reference in a proof was dropped, so most results had no edges and no "Dependencies" foldout.
