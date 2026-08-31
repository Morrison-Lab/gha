# Implementation Plan: claude-code-review sidecar failure comment bug (#764)

## Phase 1: Fix Heredoc Termination in Sidecar

- [x] Task: Write failing test (Red Phase) [bb938ad]
  - [x] Identify how the sidecar script is tested in this repository.
  - [x] Write a test case that triggers a denied-tools violation and specifically checks for proper heredoc termination (e.g., a trailing newline).
- [~] Task: Implement fix (Green Phase)
  - [ ] Modify the sidecar script to append an explicit trailing newline when writing to `$GITHUB_OUTPUT`.
- [ ] Task: Refactor and verify coverage
  - [ ] Ensure all existing tests pass and code quality is maintained.
- [ ] Task: Phase Verification & Checkpoint (Refer to workflow.md)
