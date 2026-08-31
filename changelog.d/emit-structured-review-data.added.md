- Instruct AI review workflows (`claude-code-review.yml`,
  `opencode-code-review.yml`,
  `gemini-code-review.yml`,
  and `antigravity-review`) to emit machine-readable structured JSON review payloads
  (`<!-- review-data: { ... } -->`) immediately following their human-readable Markdown verdicts.
  This allows automated verdict parsers (such as `Morrison-Lab/ai-config`'s `check-pr-fully-clean.py`)
  to ingest structured findings and verdicts directly
  while maintaining full backward compatibility with Markdown reports and human reviewers.
