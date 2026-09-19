- `examples`: remove duplicate commented `# with:` lines from caller stubs (#885, closes #839).
  Five stubs under `examples/` (`claude-code-review.yml`, `cursor-code-review.yml`, `gemini-code-review.yml`, `opencode-code-review.yml`, `small-model-agent.yml`) and dogfood caller `.github/workflows/opencode-review.yml` carried a second `# with:` key directly beneath an active `with:` block.
  Consumers uncommenting the commented block created duplicate `with:` mapping keys, which GitHub Actions and PyYAML silently collapsed by keeping the last occurrence and dropping earlier inputs like `pr-number`.
  Adds `audit_example_stubs.py` and unit tests to `_selftest.yml` to verify that all stubs and caller workflows parse cleanly under a strict duplicate-rejecting loader and when uncommented.
