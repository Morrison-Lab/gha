- `check-fform-paren.yml` and `check-local-macros.yml`: new `submodule-paths` input.
  It initializes only the named submodules (for example `latex-macros`), so a
  repository with a private submodule beside the public macros one can call
  these checks.
  Without it, `submodules: true` failed on the private submodule and
  `submodules: false` left the macros file missing, which skipped the check
  ([#1160](https://github.com/Morrison-Lab/gha/issues/1160)).
