- **The built-in `ai-config` plugin ref now names the `Morrison-Lab`
  marketplace**, fixing a hard failure that broke `claude-code-review.yml` and
  `claude.yml` for every consumer.
  `ai-config` renamed the marketplace declared in its own
  `.claude-plugin/marketplace.json` from `d-morrison` to `Morrison-Lab`
  (ai-config#802), and a plugin ref resolves by that declared name.
  Both workflows still asked for `ai-config@d-morrison`, which no longer
  matched anything, so plugin installation aborted the run before it reviewed
  or answered anything:

  ```text
  Failed to install plugin 'ai-config@d-morrison' (exit code: 1)
  ```

  The clone URL was not the problem, which is what made this confusing to
  diagnose: git and `gh` both follow GitHub's transfer redirect, so
  `d-morrison/ai-config.git` still cloned fine, and checking whether the old
  path resolved reported success.
  Only the name lookup failed.
  Both are retargeted here anyway, along with the input descriptions,
  `examples/` stubs, and `website/reference/` tables that quote them.

  This supersedes the reasoning in the earlier documentation-URL retarget,
  which deliberately left these two identifiers alone on the grounds that they
  were names rather than URLs and still matched.
  That was correct when written; ai-config#802 landed afterwards and
  invalidated it.

  Consumers that pinned a workaround (opting out with `use-ai-config: false`
  and re-adding the marketplace through `plugin-marketplaces` / `plugins`) can
  drop it once they pick up this release.
