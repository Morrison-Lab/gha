- **`audit_example_concurrency.py` now compares concurrency groups by evaluated
  runtime values across expressions rather than literal text equality** (#822).
  Expressions inside `${{ }}` are evaluated across their ternary
  (`cond && branch1 || branch2`) and fallback (`A || B`) alternatives with
  whitespace normalized.
  This catches expression-valued concurrency collisions that were previously
  missed by literal string comparisons:
  caller review stubs reintroducing PR-scoped group names that deadlock against
  reusable review workflows' internal groups (`claude-review-${{ ... }}` and
  siblings, #437), and `altdoc-multiversion-docs.yml`'s `build` job group
  whose conditional evaluates to `github.ref` outside pull requests.
  Malformed expressions with unclosed `${{` or empty `${{ }}` fail closed
  with exit 2.
