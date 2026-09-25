- **Hardened `list-pr-changed-files.sh` to fail closed when reaching the 3000-file endpoint cap**.
  The files endpoint is capped by GitHub at 3000 files per pull request.
  Previously, detecting a truncated listing depended entirely on `changed_files` being scalar and exceeding 3000.
  If `changed_files` were ever clamped or capped by GitHub, a truncated 3000-file listing would have passed as complete.
  The script now independently fails closed whenever the file listing reaches or exceeds `GITHUB_PR_FILES_CAP` (default 3000) or is strictly less than `changed_files` (#917).
  Updated callers across `claude-review.yml`, `ai-code-review.yml`, `claude.yml`, `gemini.yml`, `examples/claude-code-review.yml`, and `examples/antigravity-code-review.yml` to match.
