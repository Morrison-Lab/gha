- `check-informal-definitions`:
  add a new composite action and reusable workflow that flags technical concepts
  or terms defined in running prose rather than inside formal Quarto definition
  divs (`::: {#def-...}`), supporting both whole-tree and diff-scoped scans,
  Markdown and JSON reports, opt-out comments, and section exemptions
  ([#970](https://github.com/Morrison-Lab/gha/issues/970)).
- `check-quarto-website`, `check-quarto-book`, `check-quarto-manuscript`:
  integrate `check-informal-definitions@v3` into all three Quarto suites and
  their reusable workflow wrappers with full input forwarding
  ([#970](https://github.com/Morrison-Lab/gha/issues/970)).
- `claude-code-review.yml`:
  add Quarto definitions review checklist to lab-manual review guidance,
  instructing the reviewer to flag definitions written in running prose
  and verify that worked examples accompany formal definitions
  ([#970](https://github.com/Morrison-Lab/gha/issues/970)).
