- `check-diff-scoped.sh` (and so the opt-in `.githooks/pre-push`) also runs `check-literal-math-letters` and `check-serial-comma` over committed content.
  Before, a changelog fragment's literal math letter and a dropped serial comma only surfaced in CI (gha#1785).
