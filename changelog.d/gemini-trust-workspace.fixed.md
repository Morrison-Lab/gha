- `gemini-code-review.yml` and `gemini.yml` now set
  `GEMINI_CLI_TRUST_WORKSPACE: 'true'` on their Gemini CLI steps
  ([#458](https://github.com/Morrison-Lab/gha/issues/458)).
  Without it the CLI refuses to start on a runner checkout, which is never a
  trusted folder, so `gemini-code-review` had **0 successes in 9 runs** on
  `ucdavis/bcs` and every one was reported through the catch-all
  "failed for a reason other than quota/auth/suspension" branch.
  The same gate was also downgrading the CLI's approval mode from YOLO back to
  `default`, so a run that got past it would still have prompted for tool
  approval rather than running unattended.
