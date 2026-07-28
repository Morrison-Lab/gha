- **`claude.yml` and `claude-code-review.yml` gain `use-ai-config`,
  `plugin-marketplaces`, and `plugins` inputs** (#319).
  `use-ai-config` (boolean, on by default) installs the
  [`Morrison-Lab/ai-config`](https://github.com/Morrison-Lab/ai-config) plugin;
  `plugin-marketplaces` / `plugins` (both empty by default) pass any further
  newline-separated marketplace URLs and plugin refs through to
  `claude-code-action`'s own plugin-installation mechanism.
  All three are purely additive:
  `claude-code-review.yml`'s built-in `code-review@claude-code-plugins`
  is never replaced, only added to.
