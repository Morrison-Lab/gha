- `claude-code-review.yml`: the review prompt now asks for a single
  `### Verdict` section and keeps merge-gate results, such as
  `check-pr-fully-clean.py` output, out of it, so a quoted gate result
  no longer reads as a retraction and flips a clean verdict
  (ai-config#5259).
