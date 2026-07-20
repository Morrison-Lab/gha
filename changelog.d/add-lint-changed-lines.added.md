- **New `lint-changed-lines` capability** (composite action +
  `lint-changed-lines.yml` reusable workflow) (#275). Runs `lintr` over the R
  files a PR changes but reports only the lints on lines the PR actually added
  or modified, so lint rules can be adopted or tightened incrementally instead
  of forcing a whole-file or repo-wide reformat. Checks out the PR head (not
  the merge ref) so on-disk line numbers match the PR patch's line numbers.
