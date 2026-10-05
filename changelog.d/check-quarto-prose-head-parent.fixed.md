- **`check-quarto-prose.yml` diffs a pull request from `HEAD^1`, not the
  payload's `pull_request.base.sha`** (#1007).
  The payload's base SHA can lag the base tip GitHub built the merge ref on,
  so a diff from it counted the base branch's newer commits as added by the
  PR and reported findings on lines the PR never touched.
  The workflow arrived after #1008 moved the other diff-scoped checks to
  `HEAD^1`, and `lint-checkout-tokens`' `audit_pr_diff_base.py` failed on
  `main` because of it.
