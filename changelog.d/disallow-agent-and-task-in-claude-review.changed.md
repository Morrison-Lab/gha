- **`claude-code-review`: disallow `Agent` and `Task` subagent tools outright**
  ([#756](https://github.com/Morrison-Lab/gha/issues/756)).
  Denies `Agent` and `Task` in `--disallowedTools` to prevent background agent stub failures
  caused by omitted `run_in_background` parameters during headless CI review runs.
