- **`claude-code-review.yml`: new opt-in `check-latex-macros` input.** When
  enabled (and paired with `checkout-submodules: true` for a repo that vendors
  the `d-morrison/macros` submodule), the reviewer also flags PR-diff LaTeX
  math that could be simplified using an existing macro, and nontrivial math
  expressions repeated 3+ times that are candidates for a new one. Off by
  default (#203).
