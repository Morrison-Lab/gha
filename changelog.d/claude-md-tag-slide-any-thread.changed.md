- **`CLAUDE.md` lets any agent that finishes a gha PR slide `v3` without asking**
  ([Morrison-Lab/ai-config#6052](https://github.com/Morrison-Lab/ai-config/issues/6052)).
  The slide is no longer reserved to the runner thread,
  and no thread asks Ezra or the coordinator before sliding.
  The readiness gates and `expected_sha` are unchanged.
