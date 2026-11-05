- **The `preview` composite skips two steps a preview does not need**
  ([gha#1529](https://github.com/Morrison-Lab/gha/issues/1529)).
  The TinyTeX package install no longer runs when `skip-formats` names `pdf` and the PR is not labelled `preview:pdf`,
  even if `formats` or `tinytex` names pdf, since the render drops pdf anyway.
  The Quarto freeze cache is saved only when the render changed `_freeze`
  (compared by `preview/freeze-fingerprint.sh`) or no cache was restored.
