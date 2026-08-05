- Add `gemini.yml` and `gemini-code-review.yml` reusable workflows for Gemini CLI,
and `ai-code-review.yml`, which picks one configured AI agent at random and
dispatches that agent's own review workflow.
Both Gemini workflows wire `run-gemini-cli` to the GitHub MCP server following
upstream's own PR-review reference config: `run-gemini-cli` has no
`github_token` input and writes `.gemini/settings.json` only when `settings:` is
non-empty, so without both the run bills the API and posts nothing.
`gemini.yml` answers `@gemini` mentions and does not edit files, push, or open
PRs; its permissions are `contents: read` to match, and agent parity is tracked
in [#367](https://github.com/Morrison-Lab/gha/issues/367).
`ai-code-review.yml`'s fallback covers an agent that cannot be dispatched (no
API key secret configured, or a missing or disabled review workflow file); an
agent that dispatches and then fails mid-run is not failed over, tracked in
[#362](https://github.com/Morrison-Lab/gha/issues/362).
The three reusable workflows ship at `@v2`; this repo's own dogfood callers for
them follow in [#363](https://github.com/Morrison-Lab/gha/issues/363), once
`@v2` has slid past this change.
`detect-bot-mention` and `detect-review-request` gain a `bot-name` input so the
same matchers can gate another bot's mention; both default to `@claude`, so
existing callers are unaffected.
`detect-review-request` validates each token as a plain `@mention` before
splicing it into its regex, since a metacharacter would silently widen matching
and an unbalanced bracket would disable dispatch with no failure signal.
