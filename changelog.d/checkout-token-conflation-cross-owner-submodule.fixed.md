- **`antigravity-code-review.yml`, `gemini-code-review.yml`, and `gemini.yml`
  no longer fail to check out the CALLER's own repo when `SUBMODULES_TOKEN`
  is set for a cross-owner submodule** (#442). All three passed
  `${{ secrets.SUBMODULES_TOKEN || github.token }}` as the top-level
  `actions/checkout` `token:` input --- the same input `claude-code-review.yml`
  leaves at the runner's default `github.token`. `SUBMODULES_TOKEN` exists
  precisely because a submodule lives under a different owner than the
  consumer, so a token scoped to read the submodule has no reason to be able
  to read the caller's own repo, and in `ucdavis/bcs` it could not: the main
  checkout failed with `fatal: could not read Username for
  'https://github.com': terminal prompts disabled` on every run, so a repo
  that configured `SUBMODULES_TOKEN` correctly for its submodule got a red
  check and zero automated review from two of its three configured agents.
  All three now check out the caller with the runner's own token and
  authenticate the submodule fetch (when `checkout-submodules` is set)
  through the shared `checkout-submodules` composite action, matching
  `claude-code-review.yml`. A new `lint-checkout-tokens` selftest job asserts
  no workflow in this repo passes `SUBMODULES_TOKEN` to a top-level
  `actions/checkout` `token:` input, so the conflation can't recur silently.
