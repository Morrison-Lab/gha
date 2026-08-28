- **Caller permission contracts documented** --
  the required caller `permissions:` grant for every consumer-facing
  reusable workflow that was missing from the Permissions docs
  (`ai-code-review`, `gemini`, `gemini-code-review`,
  `antigravity-code-review`, `small-model-agent`, `claude-manage-project`,
  `altdoc-multiversion-docs`), plus the convention that widening a
  reusable workflow job's `permissions:` is a breaking change: prefer a
  major-version bump, or sweep registered consumers before the tag slides
  ([#685](https://github.com/Morrison-Lab/gha/issues/685),
  [#696](https://github.com/Morrison-Lab/gha/pull/696)).
