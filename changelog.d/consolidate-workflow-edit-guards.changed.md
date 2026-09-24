- **Consolidated inline workflow-edit dispatch guards onto `detect-pr-workflow-edits.sh`**.
  Six dispatch sites across `claude-review.yml`, `gemini.yml`, `claude.yml`, `examples/claude-code-review.yml`, and `examples/antigravity-code-review.yml` previously inlined matching logic.
  These callers now install `detect-pr-workflow-edits.sh` via `.github/actions/install-gha-scripts@v3` and invoke it directly, eliminating duplicated regex matching logic across review and agent workflows.
  Updated `run-workflow-edit-guard-tests.sh` to enforce that all dispatch sites install and invoke the canonical detection script and that no inlined workflow greps remain (#920).
