- `_selftest.yml`: distinguish real check findings from wrapper setup failures
  in the `diff-scoped-guard` job (#752).
  When `check-diff-scoped.sh` exits 1 on a PR carrying a real violation,
  the error message now attributes the failure to the check findings printed above
  rather than reporting an unexpected exit status.
