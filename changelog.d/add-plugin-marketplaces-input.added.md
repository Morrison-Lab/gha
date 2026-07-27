- **`claude.yml` and `claude-code-review.yml` gain `plugin-marketplaces` /
  `plugins` inputs** (#319). Passed through to `claude-code-action`'s own
  plugin-installation mechanism, so a consumer can opt a repo's `@claude`
  agent and/or reviewer into an additional Claude Code plugin marketplace
  (e.g. `https://github.com/d-morrison/ai-config.git`, installable as
  `ai-config@d-morrison`) beyond the built-in `code-review@claude-code-plugins`
  the reviewer already ships with. Both inputs are empty by default and purely
  additive — `claude-code-review.yml`'s built-in marketplace/plugin are never
  replaced, only appended to.
